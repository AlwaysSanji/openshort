import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import config, CLIPS_DIR, BUFFER_DIR
from app.buffer_manager import buffer_manager
from app.detector import detector
from app.clipper import clip_manager

def test_full_pipeline():
    print("[TEST 1/5] Verifying Configuration...")
    assert config.excitement_threshold >= 40
    print("  -> Config OK.")

    print("[TEST 2/5] Generating Synthetic Live Video Chunks for Buffer...")
    buffer_manager.cleanup_old_files_on_disk()

    now = time.time()
    chunk_paths = []
    # Create 3 synthetic 3-second chunks (total 9s of video)
    for i in range(3):
        chunk_file = BUFFER_DIR / f"test_seg_{i}.mp4"
        ts = now - (3 - i) * 3.0
        # High frequency sine wave on chunk 1 to simulate audio excitement
        freq = 2500 if i == 1 else 300
        vol = 0.95 if i == 1 else 0.1
        cmd = [
            "ffmpeg", "-y", "-nostdin", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=640x360:rate=30",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=3",
            "-af", f"volume={vol}",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac",
            str(chunk_file)
        ]
        subprocess.run(cmd, check=True)
        buffer_manager.add_segment(chunk_file, ts + 3.0, 3.0)
        chunk_paths.append(chunk_file)

    stats = buffer_manager.get_buffer_stats()
    print(f"  -> Buffer stats: {stats['chunk_count']} chunks, {stats['buffered_seconds']}s buffered.")
    assert stats["chunk_count"] == 3

    print("[TEST 3/5] Testing Excitement Detector...")
    # Evaluate chunk 1 (the hype chunk)
    eval_result = detector.evaluate_chunk(chunk_paths[1])
    print(f"  -> Excitement evaluation: Score={eval_result['composite_score']}%, Audio={eval_result['audio_score']}%, Motion={eval_result['motion_score']}%")
    assert "composite_score" in eval_result

    print("[TEST 4/5] Testing Clip Extraction & Thumbnail Generation...")
    trigger_ts = now - 3.0
    clip = clip_manager.extract_clip(
        trigger_time=trigger_ts,
        pre_roll=4,
        post_roll=3,
        trigger_reason="Test Excitement Spike",
        excitement_score=92.5
    )
    assert clip is not None
    print(f"  -> Successfully extracted clip: {clip['filename']} ({clip['duration']}s)")
    assert (CLIPS_DIR / clip["filename"]).exists()
    assert (CLIPS_DIR / clip["thumb_filename"]).exists()

    print("[TEST 5/5] Testing 9:16 Vertical Short Conversion...")
    short_fn = clip_manager.convert_to_short(clip["id"], style="blurred_bg")
    assert short_fn is not None
    assert (CLIPS_DIR / short_fn).exists()
    print(f"  -> 9:16 Short generated: {short_fn}")

    print("\n==================================================")
    print(" ✅ ALL 5 PIPELINE TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")

if __name__ == "__main__":
    test_full_pipeline()
