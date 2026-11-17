import os
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from app.config import CLIPS_DIR

class AutoTranscriber:
    """
    Generates word-level transcripts and subtitles for clips using faster-whisper.
    """
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            # cpu or cuda with int8 for maximum speed
            print(f"[Transcriber] Loading faster-whisper ({self.model_size})...")
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe_clip(self, clip_filename: str) -> Optional[str]:
        """
        Transcribes the clip and generates an .srt subtitle file.
        Returns the path to the .srt file.
        """
        clip_path = CLIPS_DIR / clip_filename
        if not clip_path.exists():
            return None

        srt_path = CLIPS_DIR / f"{clip_path.stem}.srt"

        try:
            model = self._get_model()
            segments, info = model.transcribe(str(clip_path), beam_size=3)

            lines = []
            idx = 1
            for seg in segments:
                start_str = self._format_timestamp(seg.start)
                end_str = self._format_timestamp(seg.end)
                text = seg.text.strip()
                if text:
                    lines.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n\n")
                    idx += 1

            if lines:
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                print(f"[Transcriber] Subtitles generated: {srt_path.name}")
                return srt_path.name
        except Exception as e:
            print(f"[Transcriber] Error transcribing clip: {e}")
        return None

    def _format_timestamp(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

transcriber = AutoTranscriber()
