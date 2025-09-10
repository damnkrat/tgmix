# tgmix/media_processor.py
from pathlib import Path
from shutil import copyfile

from markmymedia import mark_audio, mark_image, mark_video
from markmymedia.errors import (
    AudioMarkingError, FFmpegProcessError, ImageMarkingError,
    InvalidMediaError, VideoMarkingError)

from tgmix.consts import MEDIA_KEYS


class Media:
    def __init__(self, base_dir: Path, media_dir: Path, mark_media: bool):
        self.base_dir = base_dir
        self.media_dir = media_dir
        self.do_mark_media = mark_media

    @staticmethod
    def detect(message: dict) -> str:
        for key in MEDIA_KEYS:
            if key in message:
                return key
        return ""

    def process(self, message: dict) -> str | None:
        """
        Detects media in a message, processes it, and returns
        structured information. (beta)
        """
        if not (media_type := self.detect(message)):
            return None

        source_path = self.base_dir / message[media_type]
        prepared_path = self.media_dir / source_path.name

        filename = message[media_type]
        if filename in ("(File not included. "
                        "Change data exporting settings to download.)",
                        "(File exceeds maximum size. "
                        "Change data exporting settings to download.)",
                        "(File unavailable, please try again later)"):
            return "B"

        if not self.do_mark_media:
            return filename

        self.mark_media(source_path, prepared_path)
        return filename

    def _mark_media(self, func, source_path: Path, prepared_path: Path) -> None:
        try:
            func(source_path, prepared_path)
        except (AudioMarkingError, VideoMarkingError, ImageMarkingError):
            print(f"[!] Failed to mark media: {source_path.name}")
            self.copy_media_file(source_path, prepared_path)
        except InvalidMediaError:
            print(f"[!] Invalid media: {source_path.name}")
            self.copy_media_file(source_path, prepared_path)
        except FFmpegProcessError:
            print("[!] Ffmpeg not found, disabling media marking.")
            self.do_mark_media = False
            self.copy_media_file(source_path, prepared_path)

    def mark_media(self, source_path: Path,
                   prepared_path: Path) -> None:
        file_type = source_path.parent.name

        if file_type == "voice_messages":
            self._mark_media(mark_audio, source_path,
                             prepared_path.with_suffix(".mp4"))
        elif file_type in ("round_video_messages", "video_files"):
            self._mark_media(mark_video, source_path, prepared_path)
        elif file_type == "photos":
            self._mark_media(mark_image, source_path, prepared_path)
        else:
            self.copy_media_file(source_path, prepared_path)

    @staticmethod
    def copy_media_file(source_path: Path, output_path: Path) -> None:
        """Simply copies a file if it exists."""
        if not source_path.exists():
            print(f"[!] Skipped (not found): {source_path}")
            return

        copyfile(source_path, output_path)
