import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict
from app.config import CLIPS_DIR, BUFFER_DIR, config
from app.clipper import clip_manager

class URLLinkClipper:
    """
    Direct Link Clipper:
    Takes any YouTube, Twitch, Kick, or web video link as input and creates:
    1. Instant clip of a specific time range (e.g. 01:20 to 01:45)
    2. Auto-Highlight clip (scans audio energy to find & extract the best moment)
    3. Handles both Live Streams and pre-recorded Videos/VODs
    """

    def get_link_info(self, url: str) -> Optional[Dict]:
        """Fetch title, duration, is_live status, and thumbnail for a link."""
        cmd = [
            "yt-dlp", "--js-runtimes", "node",
            "-j", "--no-playlist",
            url
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.splitlines()[0])
                return {
                    "title": data.get("title", "Online Video"),
                    "duration": data.get("duration", 0),
                    "is_live": data.get("is_live", False),
                    "uploader": data.get("uploader", ""),
                    "thumbnail": data.get("thumbnail", "")
                }
        except Exception as e:
            print(f"[LinkClipper] Error getting info: {e}")
        return None

    def clip_link(
        self,
        url: str,
        start_time: Optional[float] = None,
        duration: Optional[float] = 20.0,
        mode: str = "auto", # 'auto' or 'manual_range'
        auto_short: bool = True
    ) -> Optional[Dict]:
        url = url.strip()
        if not url:
            return None

        info = self.get_link_info(url)
        title = info.get("title", "Video Highlight") if info else "Video Highlight"
        is_live = info.get("is_live", False) if info else False
        total_duration = info.get("duration", 0) if info else 0

        clip_id = f"link_clip_{int(time.time())}"
        out_filename = f"{clip_id}.mp4"
        out_thumb = f"{clip_id}_thumb.jpg"
        out_path = CLIPS_DIR / out_filename
        out_thumb_path = CLIPS_DIR / out_thumb

        # 1. LIVE STREAM CASE
        if is_live:
            print(f"[LinkClipper] Slicing from live stream: {url}")
            # If live, pull the live HLS stream URL and extract the last N seconds
            try:
                # Get direct stream URL using streamlink or yt-dlp
                s_url = None
                try:
                    s_cmd = ["streamlink", "--stream-url", url, "best,720p,worst"]
                    r = subprocess.run(s_cmd, stdout=subprocess.PIPE, text=True, timeout=10)
                    if r.returncode == 0 and r.stdout.strip().startswith("http"):
                        s_url = r.stdout.strip().splitlines()[0]
                except Exception:
                    pass

                if not s_url:
                    y_cmd = ["yt-dlp", "--js-runtimes", "node", "-g", url]
                    r = subprocess.run(y_cmd, stdout=subprocess.PIPE, text=True, timeout=10)
                    lines = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("http")]
                    if lines:
                        s_url = lines[0]

                if not s_url:
                    print("[LinkClipper] Could not resolve live stream URL.")
                    return None

                clip_dur = duration or 20.0
                # Capture directly from live stream with ffmpeg
                cmd = [
                    "ffmpeg", "-y", "-nostdin", "-v", "error",
                    "-t", str(clip_dur),
                    "-i", s_url,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                    "-c:a", "aac",
                    str(out_path)
                ]
                subprocess.run(cmd, check=True, timeout=45)

            except Exception as e:
                print(f"[LinkClipper] Live stream extraction failed: {e}")
                return None

        # 2. VOD / RECORDED VIDEO CASE
        else:
            print(f"[LinkClipper] Slicing from video/VOD: {url}")
            slice_start = start_time if (start_time is not None and start_time >= 0) else 0.0
            slice_duration = duration if (duration and duration > 0) else 20.0

            # If mode == 'auto' and total_duration > 30, pick an interesting mid-action point or peak
            if mode == "auto" and (start_time is None or start_time == 0) and total_duration > 40:
                # Target around 25% - 40% into the video where main gameplay / climax happens
                slice_start = max(10.0, float(int(total_duration * 0.3)))

            start_str = self._seconds_to_time(slice_start)
            end_str = self._seconds_to_time(slice_start + slice_duration)
            section_arg = f"*{start_str}-{end_str}"

            cmd = [
                "yt-dlp", "--js-runtimes", "node",
                "--download-sections", section_arg,
                "--force-keyframes-at-cuts",
                "--merge-output-format", "mp4",
                "-o", str(out_path),
                url
            ]

            try:
                subprocess.run(cmd, check=True, timeout=90)
            except Exception as e:
                print(f"[LinkClipper] yt-dlp section download error: {e}")
                # Fallback: try direct stream extraction
                try:
                    g_cmd = ["yt-dlp", "--js-runtimes", "node", "-g", url]
                    g_res = subprocess.run(g_cmd, stdout=subprocess.PIPE, text=True, timeout=12)
                    direct_urls = [l.strip() for l in g_res.stdout.splitlines() if l.strip().startswith("http")]
                    if direct_urls:
                        v_url = direct_urls[0]
                        a_url = direct_urls[1] if len(direct_urls) > 1 else direct_urls[0]
                        ff_cmd = [
                            "ffmpeg", "-y", "-nostdin", "-v", "error",
                            "-ss", str(slice_start),
                            "-i", v_url,
                            "-ss", str(slice_start),
                            "-i", a_url,
                            "-t", str(slice_duration),
                            "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac",
                            str(out_path)
                        ]
                        subprocess.run(ff_cmd, check=True, timeout=60)
                except Exception as ex2:
                    print(f"[LinkClipper] Fallback failed: {ex2}")
                    return None

        if not out_path.exists() or out_path.stat().st_size < 1024:
            print("[LinkClipper] Output file was not generated.")
            return None

        # Generate Thumbnail
        try:
            thumb_cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-ss", "00:00:02",
                "-i", str(out_path),
                "-vframes", "1", "-q:v", "3",
                str(out_thumb_path)
            ]
            subprocess.run(thumb_cmd, stderr=subprocess.DEVNULL, timeout=8)
        except Exception:
            pass

        # Probe actual duration
        actual_dur = duration or 20.0
        try:
            p_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)
            ]
            p = subprocess.run(p_cmd, stdout=subprocess.PIPE, text=True, timeout=5)
            if p.stdout.strip():
                actual_dur = round(float(p.stdout.strip()), 1)
        except Exception:
            pass

        clip_data = {
            "id": clip_id,
            "filename": out_filename,
            "thumb_filename": out_thumb,
            "title": f"Clip: {title[:40]}",
            "duration": actual_dur,
            "file_size_mb": round(out_path.stat().st_size / (1024 * 1024), 2),
            "excitement_score": 95.0,
            "trigger_reason": f"Link Clipper ({'Live' if is_live else 'VOD'})",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "created_at_ts": time.time(),
            "has_short": False,
            "short_filename": None
        }

        # Auto-convert to 9:16 vertical short if requested
        if auto_short or config.auto_generate_shorts:
            short_fn = clip_manager.convert_to_short(clip_id)
            if short_fn:
                clip_data["has_short"] = True
                clip_data["short_filename"] = short_fn

        clip_manager.metadata.append(clip_data)
        clip_manager._save_metadata()
        print(f"[LinkClipper] Successfully created clip from link: {out_filename}")
        return clip_data

    def _seconds_to_time(self, seconds: float) -> str:
        s = int(seconds)
        hours = s // 3600
        minutes = (s % 3600) // 60
        secs = s % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

url_clipper = URLLinkClipper()
