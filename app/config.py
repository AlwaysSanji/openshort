import os
import json
from pathlib import Path
from dataclasses import dataclass, asdict

BASE_DIR = Path(__file__).resolve().parent.parent
CLIPS_DIR = BASE_DIR / "clips"
BUFFER_DIR = BASE_DIR / "temp_buffer"
SETTINGS_FILE = BASE_DIR / "settings.json"

CLIPS_DIR.mkdir(parents=True, exist_ok=True)
BUFFER_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class ClipperConfig:
    buffer_duration: int = 120        # Maximum rolling buffer history in seconds
    chunk_duration: int = 3           # Duration per segment chunk in seconds
    pre_roll: int = 15                # Seconds to keep before the excitement trigger
    post_roll: int = 10               # Seconds to keep after the excitement trigger
    excitement_threshold: int = 70    # Excitement percentage threshold (0-100) to auto-clip
    audio_sensitivity: float = 1.0    # Audio spike sensitivity multiplier (0.2 - 2.5)
    motion_sensitivity: float = 1.0   # Motion/visual action sensitivity multiplier (0.2 - 2.5)
    audio_weight: float = 0.50        # Importance of audio in composite excitement (0 - 1)
    motion_weight: float = 0.30       # Importance of motion in composite excitement (0 - 1)
    chat_weight: float = 0.20         # Importance of chat buzz in composite excitement (0 - 1)
    cooldown_seconds: int = 15        # Minimum cooldown between auto-clips
    hotkey: str = "f9"                # Global hotkey for manual instant clip
    auto_generate_shorts: bool = False # Automatically produce 9:16 vertical short alongside 16:9
    shorts_style: str = "blurred_bg"  # "blurred_bg" or "center_crop"
    port: int = 8000

    @classmethod
    def load(cls) -> "ClipperConfig":
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception as e:
                print(f"[Config] Error loading settings.json: {e}, using defaults.")
        config = cls()
        config.save()
        return config

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving settings: {e}")

config = ClipperConfig.load()
