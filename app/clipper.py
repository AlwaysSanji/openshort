import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import List, Optional, Dict
from app.config import CLIPS_DIR, BUFFER_DIR, config
from app.buffer_manager import buffer_manager, Segment

METADATA_FILE = CLIPS_DIR / "metadata.json"

class ClipManager:
    """
    Handles lossless slicing, concatenating, thumbnail generation,
    metadata tracking, 9:16 Shorts conversion, audio/visual enhancements,
    and Windows Explorer interaction.
    """
    def __init__(self, clips_dir: Path = CLIPS_DIR):
        self.clips_dir = clips_dir
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.metadata: List[Dict] = self._load_metadata()

    def _load_metadata(self) -> List[Dict]:
        if METADATA_FILE.exists():
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Clipper] Error reading metadata: {e}")
        return []

    def _save_metadata(self):
        try:
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            print(f"[Clipper] Error saving metadata: {e}")

    def get_all_clips(self) -> List[Dict]:
        valid_clips = []
        for c in self.metadata:
            filepath = self.clips_dir / c.get("filename", "")
            if filepath.exists():
                c["file_size_mb"] = round(filepath.stat().st_size / (1024 * 1024), 2)
                valid_clips.append(c)
        if len(valid_clips) != len(self.metadata):
            self.metadata = valid_clips
            self._save_metadata()
        return sorted(self.metadata, key=lambda x: x.get("created_at_ts", 0), reverse=True)

    def extract_clip(
        self,
        trigger_time: float,
        pre_roll: Optional[int] = None,
        post_roll: Optional[int] = None,
        trigger_reason: str = "Highlight Spike",
        excitement_score: float = 85.0,
        title: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Extracts a clip around trigger_time from the rolling buffer.
        """
        pre = pre_roll if pre_roll is not None else config.pre_roll
        post = post_roll if post_roll is not None else config.post_roll

        start_ts = trigger_time - pre
        end_ts = trigger_time + post

        segments = buffer_manager.get_segments_in_range(start_ts, end_ts)
        if not segments:
            print(f"[Clipper] No segments found in range {start_ts} to {end_ts}")
            return None

        clip_id = f"clip_{int(trigger_time)}_{int(time.time()*1000)%1000}"
        clip_filename = f"{clip_id}.mp4"
        thumb_filename = f"{clip_id}_thumb.jpg"
        out_clip_path = self.clips_dir / clip_filename
        out_thumb_path = self.clips_dir / thumb_filename

        # Write ffmpeg concat script
        concat_file = BUFFER_DIR / f"concat_{clip_id}.txt"
        try:
            with open(concat_file, "w", encoding="utf-8") as f:
                for seg in segments:
                    p_str = str(seg.filepath.resolve()).replace("\\", "/")
                    f.write(f"file '{p_str}'\n")

            first_seg_start = segments[0].timestamp - segments[0].duration
            start_offset = max(0.0, start_ts - first_seg_start)
            target_duration = end_ts - start_ts

            # Concat with audio loudnorm & smooth fades
            cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-ss", f"{start_offset:.2f}",
                "-t", f"{target_duration:.2f}",
                "-vf", "eq=contrast=1.05:saturation=1.12",
                "-af", f"afade=t=in:st=0:d=0.2,afade=t=out:st={max(0.5, target_duration - 0.25):.2f}:d=0.25,loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                "-c:a", "aac", "-b:a", "192k",
                str(out_clip_path)
            ]
            subprocess.run(cmd, check=True, timeout=60)

            # Generate Thumbnail
            thumb_time = max(0.5, target_duration / 2.0)
            thumb_cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-ss", f"{thumb_time:.2f}",
                "-i", str(out_clip_path),
                "-vframes", "1", "-q:v", "3",
                str(out_thumb_path)
            ]
            subprocess.run(thumb_cmd, stderr=subprocess.DEVNULL, timeout=10)

        except Exception as e:
            print(f"[Clipper] Error extracting clip: {e}")
            if out_clip_path.exists():
                out_clip_path.unlink()
            return None
        finally:
            if concat_file.exists():
                try:
                    concat_file.unlink()
                except Exception:
                    pass

        duration = target_duration
        try:
            probe_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(out_clip_path)
            ]
            p = subprocess.run(probe_cmd, stdout=subprocess.PIPE, text=True, timeout=5)
            if p.stdout.strip():
                duration = round(float(p.stdout.strip()), 1)
        except Exception:
            pass

        clip_title = title or f"Highlight - {trigger_reason}"
        clip_data = {
            "id": clip_id,
            "filename": clip_filename,
            "thumb_filename": thumb_filename,
            "title": clip_title,
            "duration": duration,
            "file_size_mb": round(out_clip_path.stat().st_size / (1024 * 1024), 2),
            "excitement_score": round(float(excitement_score), 1),
            "trigger_reason": trigger_reason,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "created_at_ts": time.time(),
            "has_short": False,
            "short_filename": None
        }

        # Auto-convert to 9:16 Shorts if enabled in config
        if config.auto_generate_shorts:
            short_fn = self.convert_to_short(clip_id, style=config.shorts_style)
            if short_fn:
                clip_data["has_short"] = True
                clip_data["short_filename"] = short_fn

        self.metadata.append(clip_data)
        self._save_metadata()
        print(f"[Clipper] Saved polished clip: {clip_filename} ({duration}s, Excitement: {excitement_score}%)")
        return clip_data

    def convert_to_short(
        self,
        clip_id: str,
        style: str = "studio_glow",
        burn_captions: bool = False,
        color_pop: bool = True,
        audio_enhance: bool = True
    ) -> Optional[str]:
        """
        Transforms any 16:9 clip into a studio-grade viral 9:16 vertical short (1080x1920).
        Styles:
          - 'studio_glow': Ambient blurred & dimmed background + centered sharp foreground
          - 'stacked_split': Zoomed top facecam + bottom gameplay split
          - 'action_zoom': Full 1080x1920 center-action crop (zero letterbox)
        """
        clip = next((c for c in self.metadata if c["id"] == clip_id), None)
        if not clip:
            return None

        src_path = self.clips_dir / clip["filename"]
        if not src_path.exists():
            return None

        short_filename = f"{clip_id}_9x16.mp4"
        out_path = self.clips_dir / short_filename

        # If burn captions requested, ensure SRT exists or generate it
        srt_sub_filter = ""
        if burn_captions:
            srt_path = self.clips_dir / f"{clip_id}.srt"
            if not srt_path.exists():
                try:
                    from app.transcriber import transcriber
                    transcriber.transcribe_clip(clip["filename"])
                except Exception as ex:
                    print(f"[Clipper] Auto-transcribe note: {ex}")

            if srt_path.exists():
                rel_srt = f"clips/{clip_id}.srt".replace("\\", "/")
                # TikTok / MrBeast style bold yellow text with thick black outline
                srt_sub_filter = f",subtitles='{rel_srt}':force_style='FontSize=22,FontName=Arial,Bold=1,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2.8,Shadow=1.2,Alignment=2,MarginV=65'"

        try:
            color_grade = "eq=contrast=1.07:saturation=1.18:brightness=0.01" if color_pop else "null"

            if style == "stacked_split":
                # Streamer Top (Zoomed) + Gameplay Bottom
                filter_complex = (
                    f"split[v1][v2];"
                    f"[v1]crop=iw*0.6:ih*0.6:(iw-iw*0.6)/2:0,scale=1080:720,{color_grade}[top];"
                    f"[v2]scale=1080:1200:force_original_aspect_ratio=increase,crop=1080:1200,{color_grade}[bot];"
                    f"[top][bot]vstack=inputs=2{srt_sub_filter}[outv]"
                )
            elif style == "action_zoom":
                # Full 9:16 Action Crop
                filter_complex = (
                    f"[0:v]crop=ih*(9/16):ih,scale=1080:1920,{color_grade}{srt_sub_filter}[outv]"
                )
            else:
                # Default: studio_glow (Ambient blurred background + sharp centered foreground)
                filter_complex = (
                    f"split[v1][v2];"
                    f"[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=26:3,eq=brightness=-0.14:saturation=1.25[bg];"
                    f"[v2]scale=1080:-1,{color_grade}[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2{srt_sub_filter}[outv]"
                )

            # Audio filter
            af_filter = "loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.2" if audio_enhance else "anull"

            cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-i", str(src_path),
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "0:a",
                "-af", af_filter,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                str(out_path)
            ]
            subprocess.run(cmd, check=True, timeout=90)

            clip["has_short"] = True
            clip["short_filename"] = short_filename
            self._save_metadata()
            print(f"[Clipper] Studio 9:16 Short rendered: {short_filename} ({style})")
            return short_filename

        except Exception as e:
            print(f"[Clipper] Error converting to short: {e}")
            return None

    def enhance_clip(
        self,
        clip_id: str,
        color_pop: bool = True,
        audio_loudnorm: bool = True,
        burn_captions: bool = False
    ) -> Optional[Dict]:
        """
        Enhances a 16:9 clip with HDR color grade, EBU R128 loudness normalization,
        and optional burned-in viral captions.
        """
        clip = next((c for c in self.metadata if c["id"] == clip_id), None)
        if not clip:
            return None

        src_path = self.clips_dir / clip["filename"]
        if not src_path.exists():
            return None

        new_id = f"{clip_id}_remaster"
        new_filename = f"{new_id}.mp4"
        new_thumb = f"{new_id}_thumb.jpg"
        out_path = self.clips_dir / new_filename
        out_thumb = self.clips_dir / new_thumb

        dur = clip.get("duration", 15.0)

        vf_parts = []
        if color_pop:
            vf_parts.append("eq=contrast=1.08:saturation=1.2:brightness=0.02")
        vf_parts.append(f"fade=t=in:st=0:d=0.25,fade=t=out:st={max(0.5, dur - 0.25):.2f}:d=0.25")

        if burn_captions:
            srt_path = self.clips_dir / f"{clip_id}.srt"
            if not srt_path.exists():
                try:
                    from app.transcriber import transcriber
                    transcriber.transcribe_clip(clip["filename"])
                except Exception:
                    pass
            if srt_path.exists():
                rel_srt = f"clips/{clip_id}.srt".replace("\\", "/")
                vf_parts.append(f"subtitles='{rel_srt}':force_style='FontSize=24,FontName=Arial,Bold=1,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2.8,Shadow=1,Alignment=2,MarginV=50'")

        vf_str = ",".join(vf_parts) if vf_parts else "null"

        af_parts = []
        if audio_loudnorm:
            af_parts.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        af_parts.append(f"afade=t=in:st=0:d=0.2,afade=t=out:st={max(0.5, dur - 0.25):.2f}:d=0.25")
        af_str = ",".join(af_parts) if af_parts else "anull"

        try:
            cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-i", str(src_path),
                "-vf", vf_str,
                "-af", af_str,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                "-c:a", "aac", "-b:a", "192k",
                str(out_path)
            ]
            subprocess.run(cmd, check=True, timeout=60)

            # Thumbnail
            thumb_cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-ss", f"{max(0.5, dur/2):.2f}",
                "-i", str(out_path),
                "-vframes", "1", "-q:v", "3",
                str(out_thumb)
            ]
            subprocess.run(thumb_cmd, stderr=subprocess.DEVNULL, timeout=5)

            new_clip_data = {
                "id": new_id,
                "filename": new_filename,
                "thumb_filename": new_thumb,
                "title": f"✨ Remastered - {clip['title']}",
                "duration": dur,
                "file_size_mb": round(out_path.stat().st_size / (1024 * 1024), 2),
                "excitement_score": min(100.0, clip.get("excitement_score", 90) + 5.0),
                "trigger_reason": "Studio Enhancement Remaster",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "created_at_ts": time.time(),
                "has_short": False,
                "short_filename": None
            }

            self.metadata.append(new_clip_data)
            self._save_metadata()
            return new_clip_data

        except Exception as e:
            print(f"[Clipper] Remaster failed: {e}")
            return None

    def trim_clip(self, clip_id: str, start_time: float, end_time: float) -> Optional[Dict]:
        clip = next((c for c in self.metadata if c["id"] == clip_id), None)
        if not clip:
            return None

        src_path = self.clips_dir / clip["filename"]
        if not src_path.exists():
            return None

        duration = max(1.0, end_time - start_time)
        new_id = f"clip_trim_{int(time.time())}"
        new_filename = f"{new_id}.mp4"
        new_thumb = f"{new_id}_thumb.jpg"
        out_path = self.clips_dir / new_filename
        out_thumb_path = self.clips_dir / new_thumb

        try:
            cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-ss", f"{start_time:.2f}",
                "-i", str(src_path),
                "-t", f"{duration:.2f}",
                "-vf", "eq=contrast=1.05:saturation=1.12",
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.15",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                "-c:a", "aac",
                str(out_path)
            ]
            subprocess.run(cmd, check=True, timeout=30)

            thumb_cmd = [
                "ffmpeg", "-y", "-nostdin", "-v", "error",
                "-ss", f"{max(0.5, duration/2):.2f}",
                "-i", str(out_path),
                "-vframes", "1", "-q:v", "3",
                str(out_thumb_path)
            ]
            subprocess.run(thumb_cmd, stderr=subprocess.DEVNULL, timeout=5)

            new_clip_data = {
                "id": new_id,
                "filename": new_filename,
                "thumb_filename": new_thumb,
                "title": f"Trimmed - {clip['title']}",
                "duration": round(duration, 1),
                "file_size_mb": round(out_path.stat().st_size / (1024 * 1024), 2),
                "excitement_score": clip.get("excitement_score", 80.0),
                "trigger_reason": f"Trimmed from {clip['id']}",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "created_at_ts": time.time(),
                "has_short": False,
                "short_filename": None
            }
            self.metadata.append(new_clip_data)
            self._save_metadata()
            return new_clip_data
        except Exception as e:
            print(f"[Clipper] Trim error: {e}")
            return None

    def delete_clip(self, clip_id: str) -> bool:
        clip = next((c for c in self.metadata if c["id"] == clip_id), None)
        if not clip:
            return False

        for f_key in ["filename", "thumb_filename", "short_filename"]:
            fn = clip.get(f_key)
            if fn:
                p = self.clips_dir / fn
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass

        srt_file = self.clips_dir / f"{clip_id}.srt"
        if srt_file.exists():
            try:
                srt_file.unlink()
            except Exception:
                pass

        self.metadata = [c for c in self.metadata if c["id"] != clip_id]
        self._save_metadata()
        return True

    def open_in_explorer(self, clip_id: str) -> bool:
        clip = next((c for c in self.metadata if c["id"] == clip_id), None)
        target_path = (self.clips_dir / clip.get("filename", "")) if clip else self.clips_dir
        if not target_path.exists():
            target_path = self.clips_dir

        if sys.platform == "win32":
            try:
                if target_path.is_file():
                    subprocess.Popen(["explorer.exe", f"/select,{str(target_path.resolve())}"])
                else:
                    subprocess.Popen(["explorer.exe", str(target_path.resolve())])
                return True
            except Exception as e:
                print(f"[Clipper] Failed to open explorer: {e}")
                return False
        return False

clip_manager = ClipManager()
