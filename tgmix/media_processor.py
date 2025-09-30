# tgmix/media_processor.py
import multiprocessing
from pathlib import Path
from shutil import copyfile

from faster_whisper import WhisperModel
from markmymedia import mark_audio, mark_image, mark_video
from markmymedia.errors import (
    AudioMarkingError, FFmpegProcessError, ImageMarkingError,
    InvalidMediaError, VideoMarkingError)
from tqdm import tqdm

from tgmix.consts import MEDIA_KEYS


worker_model = None
worker_config = {}


def init_worker(config: dict):
    global worker_model, worker_config
    worker_config = config
    worker_model = None


def transcribe_worker(file_path: Path) -> tuple[Path, str | None]:
    global worker_model, worker_config

    if worker_model is None:
        model_name = worker_config.get("transcription_model", "tiny")
        device = worker_config.get("transcription_device", "auto")
        compute_type = worker_config.get("transcription_compute_type",
                                         "float32")
        worker_model = WhisperModel(model_name,
                                    device=device,
                                    compute_type=compute_type)

    segments, _ = worker_model.transcribe(
        str(file_path),
        without_timestamps=True,
        beam_size=1,
        best_of=2,
        vad_filter=True)
    return file_path, "".join(
        segment.text for segment in segments).strip()


class Media:
    def __init__(self, base_dir: Path, media_dir: Path, mark_media: bool,
                 config: dict):
        self.base_dir = base_dir
        self.media_dir = media_dir
        self.do_mark_media = mark_media
        self.config = config

    def batch_transcribe(self,
                         source_paths_with_duration: dict[Path, int]
                         ) -> dict[Path, str | None]:
        if not source_paths_with_duration:
            return {}

        num_processes = max(1, multiprocessing.cpu_count() - 1)
        print("[*] Starting batch transcription source_paths for "
              f"{len(source_paths_with_duration)} files using "
              f"{num_processes} processes...")

        with multiprocessing.Pool(processes=num_processes,
                                  initializer=init_worker,
                                  initargs=(self.config,)) as pool:
            results = {}
            pbar = tqdm(total=len(source_paths_with_duration),
                        desc="Transcribing files")
            for file_path, text in pool.imap_unordered(
                    transcribe_worker, source_paths_with_duration.keys()):
                results[file_path] = text
                pbar.update()
            pbar.close()

        return results

    @staticmethod
    def detect(message: dict) -> str:
        for key in MEDIA_KEYS:
            if key in message:
                return key
        return ""

    def check_path(self, filename: str):
        try:
            source_path = self.base_dir / filename
            resolved_source = source_path.resolve(strict=True)
            resolved_base = self.base_dir.resolve()
        except FileNotFoundError:
            print(f"[!] Skipped: File not found: {filename}")
            return "NF", ""  # Not found
        except Exception as e:
            print(f"[!] Skipped (error resolving path for '{filename}'):\n"
                  f"{e}")
            return "NF", ""

        if not resolved_source.is_relative_to(resolved_base):
            print("[!] Security Warning: Blocked attempt to access a file "
                  f"outside the base directory: {filename}")
            return "OOB", resolved_source  # Out Of Bounds
        if resolved_source.is_dir():
            print(f"[!] Skipped: Path points to a directory: {filename}")
            return "isdir", resolved_source

        return "", resolved_source

    def process(self, message: dict,
                transcription_cache: dict[Path, str] = None) -> tuple[
        str | None, str | None]:
        """
        Detects media in a message, processes it, and returns
        structured information.
        """
        if transcription_cache is None:
            transcription_cache = {}

        if not (media_type := self.detect(message)):
            return None, None

        filename = message.get(media_type)
        if not isinstance(filename, str) or not filename:
            return None, None

        if filename in ("(File not included. "
                        "Change data exporting settings to download.)",
                        "(File exceeds maximum size. "
                        "Change data exporting settings to download.)",
                        "(File unavailable, please try again later)"):
            return "B", None

        output_code, resolved_source = self.check_path(filename)
        if output_code:
            return output_code, None

        prepared_path = self.media_dir / resolved_source.name

        file_type = resolved_source.parent.name
        can_be_transcribed = file_type in (
            "voice_messages", "round_video_messages", "video_files")

        if self.config.get("transcribe_media") and can_be_transcribed:
            if resolved_source in transcription_cache:
                if transcribed_text := transcription_cache[resolved_source]:
                    return (file_type.removesuffix("s").removesuffix(
                        "_file").removeprefix("round_"), transcribed_text)

        if self.do_mark_media:
            self.mark_media(resolved_source, prepared_path)
        else:
            self.copy_media_file(resolved_source, prepared_path)
        return filename, None

    def _mark_media(self, func, source_path: Path,
                    prepared_path: Path) -> None:
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
