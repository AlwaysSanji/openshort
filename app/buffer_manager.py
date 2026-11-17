import os
import time
import shutil
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from app.config import BUFFER_DIR, config

@dataclass
class Segment:
    filepath: Path
    timestamp: float  # Unix timestamp when segment completed
    duration: float

class BufferManager:
    """
    Thread-safe Rolling Ring Buffer Manager.
    Maintains a rolling window of video segments on disk.
    Automatically removes segments older than buffer_duration.
    """
    def __init__(self, buffer_dir: Path = BUFFER_DIR):
        self.buffer_dir = buffer_dir
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.segments: List[Segment] = []
        self.lock = threading.Lock()
        self._running = False
        self._cleanup_thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self.cleanup_old_files_on_disk()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def stop(self):
        self._running = False
        self.clear()

    def add_segment(self, filepath: Path, timestamp: float, duration: float):
        """Register a newly completed chunk in the rolling buffer."""
        with self.lock:
            if filepath.exists() and filepath.stat().st_size > 1024:
                seg = Segment(filepath=filepath, timestamp=timestamp, duration=duration)
                self.segments.append(seg)
                self.segments.sort(key=lambda s: s.timestamp)

    def get_segments_in_range(self, start_ts: float, end_ts: float) -> List[Segment]:
        """
        Return all segments that overlap with the window [start_ts, end_ts].
        """
        with self.lock:
            overlapping = []
            for seg in self.segments:
                seg_start = seg.timestamp - seg.duration
                seg_end = seg.timestamp
                # Overlap test:
                if seg_end >= start_ts and seg_start <= end_ts:
                    if seg.filepath.exists():
                        overlapping.append(seg)
            return list(overlapping)

    def get_latest_segment(self) -> Optional[Segment]:
        with self.lock:
            for seg in reversed(self.segments):
                if seg.filepath.exists():
                    return seg
            return None

    def get_buffer_stats(self) -> dict:
        with self.lock:
            total_duration = sum(s.duration for s in self.segments if s.filepath.exists())
            count = len([s for s in self.segments if s.filepath.exists()])
            return {
                "chunk_count": count,
                "buffered_seconds": round(total_duration, 1),
                "max_seconds": config.buffer_duration
            }

    def _cleanup_loop(self):
        while self._running:
            time.sleep(2)
            now = time.time()
            cutoff = now - config.buffer_duration - 15  # 15s grace margin
            with self.lock:
                kept = []
                for seg in self.segments:
                    if seg.timestamp < cutoff:
                        try:
                            if seg.filepath.exists():
                                seg.filepath.unlink()
                        except Exception:
                            pass
                    else:
                        kept.append(seg)
                self.segments = kept

    def cleanup_old_files_on_disk(self):
        """Purge any stale chunks remaining in the buffer directory."""
        with self.lock:
            self.segments.clear()
            for p in self.buffer_dir.glob("*.*"):
                try:
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass

    def clear(self):
        self.cleanup_old_files_on_disk()

buffer_manager = BufferManager()
