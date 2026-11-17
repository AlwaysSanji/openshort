import os
import sys
import time
import shutil
import threading
import subprocess
from pathlib import Path
from typing import Optional, Callable, Dict
from app.config import BUFFER_DIR, config
from app.buffer_manager import buffer_manager
from app.detector import detector
from app.clipper import clip_manager
from app.chat_monitor import chat_monitor

class StreamIngestManager:
    """
    Manages live stream ingestion from:
    1. Live URLs (Twitch, YouTube Live, Kick, HLS/RTMP)
    2. PC Screen Capture (desktop / game via FFmpeg gdigrab)
    3. Local Video Files (VOD processing)
    4. Built-in Live Simulator (with automated hype spikes for testing)
    """

    def __init__(self):
        self.is_active = False
        self.source_type: Optional[str] = None # 'url', 'desktop', 'file', 'simulator'
        self.source_target: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None
        self._watcher_thread: Optional[threading.Thread] = None
        self._sim_thread: Optional[threading.Thread] = None
        self.telemetry_callback: Optional[Callable[[Dict], None]] = None
        self.clip_callback: Optional[Callable[[Dict], None]] = None

        # Pending trigger tracker for post-roll wait
        self._pending_triggers = [] # list of dicts: {'trigger_time', 'reason', 'score', 'scheduled_extract_time'}

    def set_callbacks(self, telemetry_cb: Callable[[Dict], None], clip_cb: Callable[[Dict], None]):
        self.telemetry_callback = telemetry_cb
        self.clip_callback = clip_cb

    def start_ingestion(self, source_type: str, source_target: str = "") -> bool:
        self.stop_ingestion()

        self.source_type = source_type
        self.source_target = source_target.strip()
        self.is_active = True
        self._pending_triggers.clear()

        buffer_manager.start()

        if source_type == "simulator":
            self._start_simulator()
            return True
        elif source_type == "url":
            return self._start_url_stream(self.source_target)
        elif source_type == "desktop":
            return self._start_desktop_capture()
        elif source_type == "file":
            return self._start_file_stream(self.source_target)
        else:
            print(f"[Ingest] Unknown source type: {source_type}")
            self.stop_ingestion()
            return False

    def stop_ingestion(self):
        self.is_active = False
        chat_monitor.stop()

        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        buffer_manager.stop()
        self._pending_triggers.clear()
        print("[Ingest] Ingestion stopped.")

    def trigger_manual_clip(self, reason: str = "Manual Hotkey Trigger (F9)"):
        """
        Instantly saves a highlight clip from the rolling buffer.
        """
        now = time.time()
        print(f"[Ingest] Manual clip triggered: {reason}")
        clip = clip_manager.extract_clip(
            trigger_time=now,
            pre_roll=config.pre_roll,
            post_roll=config.post_roll,
            trigger_reason=reason,
            excitement_score=99.0
        )
        if clip and self.clip_callback:
            self.clip_callback(clip)
        return clip

    def _resolve_stream_url(self, url: str) -> Optional[str]:
        """
        Uses streamlink or yt-dlp to extract direct HLS/m3u8 stream.
        """
        print(f"[Ingest] Resolving stream URL for: {url}")
        # Try streamlink first
        try:
            cmd = ["streamlink", "--stream-url", url, "best,720p,480p,worst"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
            if res.returncode == 0 and res.stdout.strip().startswith("http"):
                stream_url = res.stdout.strip().splitlines()[0]
                print(f"[Ingest] Resolved via streamlink: {stream_url[:60]}...")
                return stream_url
        except Exception as e:
            print(f"[Ingest] streamlink lookup note: {e}")

        # Try yt-dlp fallback
        try:
            cmd = ["yt-dlp", "--js-runtimes", "node", "-g", url]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
            if res.returncode == 0 and res.stdout.strip():
                lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip().startswith("http")]
                if lines:
                    stream_url = lines[0]
                    print(f"[Ingest] Resolved via yt-dlp: {stream_url[:60]}...")
                    return stream_url
        except Exception as e:
            print(f"[Ingest] yt-dlp lookup note: {e}")

        return url if url.startswith("http") else None

    def _start_url_stream(self, raw_url: str) -> bool:
        if not raw_url:
            return False

        # If Twitch, start chat monitoring
        if "twitch.tv" in raw_url:
            chat_monitor.start(raw_url)
            detector.set_chat_provider(chat_monitor.get_stats)

        direct_url = self._resolve_stream_url(raw_url)
        if not direct_url:
            print(f"[Ingest] Could not resolve stream URL for: {raw_url}")
            return False

        # Launch FFmpeg to segment live HLS stream into chunk_%04d.mp4
        chunk_pattern = str(BUFFER_DIR / "chunk_%04d.mp4").replace("\\", "/")
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-i", direct_url,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(config.chunk_duration),
            "-segment_list_size", "40",
            "-reset_timestamps", "1",
            chunk_pattern
        ]

        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._watcher_thread = threading.Thread(target=self._buffer_watcher_loop, daemon=True)
            self._watcher_thread.start()
            return True
        except Exception as e:
            print(f"[Ingest] Failed to start FFmpeg for live URL: {e}")
            return False

    def _start_desktop_capture(self) -> bool:
        """
        Captures PC Desktop using FFmpeg gdigrab.
        """
        chunk_pattern = str(BUFFER_DIR / "chunk_%04d.mp4").replace("\\", "/")
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-f", "gdigrab", "-framerate", "30", "-i", "desktop",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-an", # audio can be added via dshow audio if configured
            "-f", "segment",
            "-segment_time", str(config.chunk_duration),
            "-segment_list_size", "40",
            "-reset_timestamps", "1",
            chunk_pattern
        ]

        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._watcher_thread = threading.Thread(target=self._buffer_watcher_loop, daemon=True)
            self._watcher_thread.start()
            return True
        except Exception as e:
            print(f"[Ingest] Failed to start screen capture: {e}")
            return False

    def _start_file_stream(self, file_path: str) -> bool:
        """
        Streams a local video file in real-time for highlight testing.
        """
        p = Path(file_path)
        if not p.exists():
            return False

        chunk_pattern = str(BUFFER_DIR / "chunk_%04d.mp4").replace("\\", "/")
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-re", "-i", str(p),
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac",
            "-f", "segment",
            "-segment_time", str(config.chunk_duration),
            "-segment_list_size", "40",
            "-reset_timestamps", "1",
            chunk_pattern
        ]

        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._watcher_thread = threading.Thread(target=self._buffer_watcher_loop, daemon=True)
            self._watcher_thread.start()
            return True
        except Exception as e:
            print(f"[Ingest] Failed to stream file: {e}")
            return False

    def _start_simulator(self):
        """
        Generates simulated live video chunks with periodic hype events.
        """
        self._sim_thread = threading.Thread(target=self._simulator_worker, daemon=True)
        self._sim_thread.start()

    def _simulator_worker(self):
        print("[Ingest] Built-in Simulator started.")
        chunk_idx = 0
        last_hype_time = time.time()

        while self.is_active and self.source_type == "simulator":
            chunk_start = time.time()
            chunk_file = BUFFER_DIR / f"sim_chunk_{chunk_idx:04d}.mp4"

            # Check if this chunk should have a hype moment (every ~25-35s)
            now = time.time()
            is_hype = (now - last_hype_time) > 28.0
            if is_hype:
                last_hype_time = now

            # Generate synthetic 3-second segment using FFmpeg testsrc and sine wave
            freq = 2400 if is_hype else 440
            volume = 0.95 if is_hype else 0.2
            rate = 30
            # Draw live timecode on the video so it looks like an authentic stream
            time_str = time.strftime("%H:%M:%S")

            cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-f", "lavfi", "-i", f"testsrc=duration={config.chunk_duration}:size=1280x720:rate={rate}",
                "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={config.chunk_duration}",
                "-vf", f"drawtext=text='LIVE DEMO {time_str}':fontsize=36:fontcolor=white:x=40:y=40:box=1:boxcolor=black@0.6",
                "-af", f"volume={volume}",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac",
                str(chunk_file)
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            except Exception:
                pass

            if chunk_file.exists():
                seg_ts = time.time()
                buffer_manager.add_segment(chunk_file, seg_ts, float(config.chunk_duration))

                # Telemetry
                stats = detector.simulate_tick(is_hype=is_hype)
                self._handle_telemetry(stats, seg_ts)

            chunk_idx += 1
            # Sleep remainder of chunk duration to simulate real-time
            elapsed = time.time() - chunk_start
            sleep_time = max(0.1, config.chunk_duration - elapsed)
            time.sleep(sleep_time)

    def _buffer_watcher_loop(self):
        """
        Monitors BUFFER_DIR for new finished chunks and feeds them to detector.
        """
        processed = set()
        while self.is_active:
            chunks = sorted(list(BUFFER_DIR.glob("chunk_*.mp4")))
            # Only consider chunks that are not currently being written (e.g. at least 2 exist)
            if len(chunks) > 1:
                for chunk in chunks[:-1]: # exclude newest in-progress chunk
                    if chunk not in processed:
                        processed.add(chunk)
                        seg_ts = time.time()
                        buffer_manager.add_segment(chunk, seg_ts, float(config.chunk_duration))

                        # Evaluate with Detector
                        stats = detector.evaluate_chunk(chunk)
                        self._handle_telemetry(stats, seg_ts)

            # Check if FFmpeg exited
            if self._proc and self._proc.poll() is not None:
                print(f"[Ingest] FFmpeg process exited with code {self._proc.returncode}")
                break

            time.sleep(1.0)

    def _handle_telemetry(self, stats: Dict, current_ts: float):
        # 1. Check if trigger fired
        if stats.get("is_triggered"):
            print(f"[Ingest] 🔥 HIGHLIGHT TRIGGERED: {stats.get('trigger_reason')} (Score: {stats.get('composite_score')}%)")
            # Schedule extraction after post-roll has accumulated
            scheduled_time = current_ts + config.post_roll + 2.0
            self._pending_triggers.append({
                "trigger_time": current_ts,
                "reason": stats.get("trigger_reason"),
                "score": stats.get("composite_score"),
                "scheduled_time": scheduled_time
            })

        # 2. Check pending triggers whose post-roll window has now passed
        now = time.time()
        remaining = []
        for pt in self._pending_triggers:
            if now >= pt["scheduled_time"]:
                # Time to extract the clip!
                clip = clip_manager.extract_clip(
                    trigger_time=pt["trigger_time"],
                    pre_roll=config.pre_roll,
                    post_roll=config.post_roll,
                    trigger_reason=pt["reason"],
                    excitement_score=pt["score"]
                )
                if clip and self.clip_callback:
                    self.clip_callback(clip)
            else:
                remaining.append(pt)
        self._pending_triggers = remaining

        # 3. Send telemetry update
        if self.telemetry_callback:
            buf_stats = buffer_manager.get_buffer_stats()
            payload = {
                "is_active": self.is_active,
                "source_type": self.source_type,
                "source_target": self.source_target,
                "buffer": buf_stats,
                "metrics": stats,
                "pending_clips_count": len(self._pending_triggers)
            }
            self.telemetry_callback(payload)

stream_ingest = StreamIngestManager()
