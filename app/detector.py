import cv2
import numpy as np
import time
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict
from app.config import config

class ExcitementDetector:
    """
    Multi-Signal Excitement & Highlight Detection Engine.
    Combines:
    1. Audio Energy & Dynamic Z-Score Spike Detection (Screaming, Cheering, Volume Surges)
    2. Computer Vision Motion / Action Dynamics (Explosions, Fast Camera, Combat)
    3. Live Chat Velocity & Sentiment Spikes (POG, LMAO, CLIP IT, W, WTF)
    """

    def __init__(self):
        # Audio baseline tracking (Exponential Moving Average)
        self.audio_ema_mean = -40.0   # Initial baseline in dBFS
        self.audio_ema_var = 16.0     # Initial variance
        self.alpha = 0.05             # Smoothing factor for ambient baseline

        # Current state
        self.last_audio_db = -60.0
        self.last_audio_score = 0.0
        self.last_motion_score = 0.0
        self.last_chat_score = 0.0
        self.composite_score = 0.0
        self.last_trigger_time = 0.0

        # Chat stats provider (injected by ChatMonitor)
        self.chat_stats_provider = None

    def set_chat_provider(self, provider):
        self.chat_stats_provider = provider

    def analyze_audio_segment(self, segment_path: Path) -> Tuple[float, float]:
        """
        Extracts audio PCM samples from video chunk using ffmpeg pipe.
        Returns: (dBFS, audio_score 0-100)
        """
        if not segment_path.exists():
            return -60.0, 0.0

        try:
            # Extract raw 16kHz mono PCM 16-bit
            cmd = [
                "ffmpeg", "-nostdin", "-v", "error",
                "-i", str(segment_path),
                "-vn", "-f", "s16le", "-ac", "1", "-ar", "16000",
                "pipe:1"
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4)
            raw = proc.stdout
            if not raw or len(raw) < 100:
                return -60.0, 0.0

            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

            # Calculate RMS energy
            rms = np.sqrt(np.mean(samples ** 2) + 1e-9)
            dbfs = 20.0 * np.log10(rms + 1e-6)
            dbfs = float(np.clip(dbfs, -80.0, 0.0))

            # Update ambient baseline EMA
            self.audio_ema_mean = (1 - self.alpha) * self.audio_ema_mean + self.alpha * dbfs
            diff = dbfs - self.audio_ema_mean
            self.audio_ema_var = (1 - self.alpha) * self.audio_ema_var + self.alpha * (diff ** 2)
            std = np.sqrt(max(1.0, self.audio_ema_var))

            # Dynamic Z-score spike (how many standard deviations above normal)
            z_score = max(0.0, (dbfs - self.audio_ema_mean) / std)

            # Absolute loudness factor: Screams/shouts are typically > -22 dBFS
            loudness_factor = np.clip((dbfs - (-35.0)) / 25.0, 0.0, 1.0)

            # Combined audio excitement score (0 - 100)
            # A surge 2.5 standard deviations above baseline AND moderately loud = hype!
            z_factor = np.clip(z_score / 3.0, 0.0, 1.0)
            raw_score = (0.6 * z_factor + 0.4 * loudness_factor) * 100.0 * config.audio_sensitivity

            audio_score = float(np.clip(raw_score, 0.0, 100.0))
            self.last_audio_db = round(dbfs, 1)
            self.last_audio_score = round(audio_score, 1)
            return self.last_audio_db, self.last_audio_score

        except Exception as e:
            return -60.0, 0.0

    def analyze_motion_segment(self, segment_path: Path) -> float:
        """
        Samples frames across the chunk using OpenCV.
        Calculates normalized inter-frame motion delta (0 - 100).
        """
        if not segment_path.exists():
            return 0.0

        cap = cv2.VideoCapture(str(segment_path))
        if not cap.isOpened():
            return 0.0

        prev_gray = None
        motion_deltas = []
        frame_count = 0

        # Sample up to 15 frames per segment for fast performance
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step = max(1, total_frames // 12) if total_frames > 0 else 3

        idx = 0
        while cap.isOpened() and frame_count < 12:
            ret, frame = cap.read()
            if not ret:
                break
            idx += 1
            if idx % step != 0:
                continue

            frame_count += 1
            # Resize down to 240x135 for fast motion analysis
            small = cv2.resize(frame, (240, 135))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (7, 7), 0)

            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                # Calculate percentage of pixels that changed significantly
                thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                change_ratio = np.mean(thresh) / 255.0
                motion_deltas.append(change_ratio)

            prev_gray = gray

        cap.release()

        if not motion_deltas:
            return 0.0

        avg_motion = float(np.mean(motion_deltas))
        # 15% frame change represents high action in gaming/streams
        motion_score = np.clip((avg_motion / 0.15) * 100.0 * config.motion_sensitivity, 0.0, 100.0)
        self.last_motion_score = round(float(motion_score), 1)
        return self.last_motion_score

    def evaluate_chunk(self, segment_path: Path) -> Dict[str, any]:
        """
        Full evaluation of the latest chunk.
        Calculates audio, motion, chat, and composite excitement score.
        Checks if trigger threshold is exceeded.
        """
        audio_db, audio_score = self.analyze_audio_segment(segment_path)
        motion_score = self.analyze_motion_segment(segment_path)

        # Chat score from monitor
        chat_score = 0.0
        chat_msg_rate = 0.0
        if self.chat_stats_provider:
            chat_stats = self.chat_stats_provider()
            chat_score = chat_stats.get("chat_score", 0.0)
            chat_msg_rate = chat_stats.get("msg_rate", 0.0)
        self.last_chat_score = round(chat_score, 1)

        # Composite score
        comp = (
            config.audio_weight * audio_score +
            config.motion_weight * motion_score +
            config.chat_weight * chat_score
        )
        self.composite_score = round(float(np.clip(comp, 0.0, 100.0)), 1)

        # Trigger logic
        now = time.time()
        cooldown_elapsed = (now - self.last_trigger_time) >= config.cooldown_seconds
        is_triggered = (self.composite_score >= config.excitement_threshold) and cooldown_elapsed

        primary_reason = "Composite High"
        if audio_score >= config.excitement_threshold:
            primary_reason = f"Audio Spike ({audio_score}%)"
        elif chat_score >= config.excitement_threshold:
            primary_reason = f"Chat Frenzy ({chat_score}%)"
        elif motion_score >= config.excitement_threshold:
            primary_reason = f"Action Peak ({motion_score}%)"

        if is_triggered:
            self.last_trigger_time = now

        return {
            "timestamp": now,
            "composite_score": self.composite_score,
            "audio_score": self.last_audio_score,
            "audio_db": self.last_audio_db,
            "motion_score": self.last_motion_score,
            "chat_score": self.last_chat_score,
            "chat_msg_rate": chat_msg_rate,
            "threshold": config.excitement_threshold,
            "is_triggered": is_triggered,
            "trigger_reason": primary_reason if is_triggered else None
        }

    def simulate_tick(self, is_hype: bool = False) -> Dict[str, any]:
        """
        Generates simulated telemetry for test / demo mode.
        """
        now = time.time()
        if is_hype:
            self.last_audio_db = float(np.random.uniform(-14.0, -8.0))
            self.last_audio_score = float(np.random.uniform(85.0, 99.0))
            self.last_motion_score = float(np.random.uniform(80.0, 96.0))
            self.last_chat_score = float(np.random.uniform(88.0, 100.0))
        else:
            self.last_audio_db = float(np.random.uniform(-38.0, -28.0))
            self.last_audio_score = float(np.random.uniform(10.0, 42.0))
            self.last_motion_score = float(np.random.uniform(15.0, 48.0))
            self.last_chat_score = float(np.random.uniform(5.0, 25.0))

        comp = (
            config.audio_weight * self.last_audio_score +
            config.motion_weight * self.last_motion_score +
            config.chat_weight * self.last_chat_score
        )
        self.composite_score = round(float(np.clip(comp, 0.0, 100.0)), 1)

        cooldown_elapsed = (now - self.last_trigger_time) >= config.cooldown_seconds
        is_triggered = (self.composite_score >= config.excitement_threshold) and cooldown_elapsed

        if is_triggered:
            self.last_trigger_time = now

        return {
            "timestamp": now,
            "composite_score": self.composite_score,
            "audio_score": round(self.last_audio_score, 1),
            "audio_db": round(self.last_audio_db, 1),
            "motion_score": round(self.last_motion_score, 1),
            "chat_score": round(self.last_chat_score, 1),
            "chat_msg_rate": round(self.last_chat_score / 5.0, 1),
            "threshold": config.excitement_threshold,
            "is_triggered": is_triggered,
            "trigger_reason": "Live Hype Surge!" if is_triggered else None
        }

detector = ExcitementDetector()
