# tgmix/media_processor.py
import shutil
import subprocess
from pathlib import Path

from tgmix.consts import MEDIA_KEYS


def process_media(msg: dict, base_dir: Path, media_dir: Path,
                  config: dict) -> dict | None:
    """
    Detects media in a message, processes it, and returns
    structured information. (beta)
    """
    media_type = next((key for key in MEDIA_KEYS if key in msg), None)

    if not media_type:
        return None

    source_path = base_dir / msg[media_type]
    output_filename = source_path.with_suffix(
        ".mp4").name if media_type == "voice_message" else source_path.name

    prepared_path = media_dir / output_filename

    filename = msg[media_type]
    if filename in ("(File not included. "
                    "Change data exporting settings to download.)",
                    "(File exceeds maximum size. "
                    "Change data exporting settings to download.)",
                    "(File unavailable, please try again later)"):
        filename = "B"
    else:
        # Decide how to process the file. Halted for next updates
        # if media_type in ["voice_message", "video_message"]:
        #     convert_to_video_with_filename(
        #         source_path, prepared_path,
        #         config['ffmpeg_drawtext_settings']
        #     )
        # else:
        copy_media_file(source_path, prepared_path)

    return {"type": media_type, "source_file": filename}


def convert_to_video_with_filename(
    input_path: Path, output_path: Path, drawtext_settings: str
):
    """
    Converts a media file to MP4 with the filename overlaid on the frame.
    The drawtext settings are passed as an argument.
    """
    if not input_path.exists():
        print(f"[!] Skipped (not found): {input_path}")
        return False

    filename_text = input_path.name.replace("'", "\\'")
    drawtext_filter = drawtext_settings.format(filename=filename_text)

    command = [
        "ffmpeg", "-y", "-i", str(input_path), "-f", "lavfi",
        "-i", "color=c=black:s=640x360:d=1", "-vf", drawtext_filter,
        "-c:a", "copy", "-shortest", str(output_path),
    ]

    try:
        subprocess.run(
            command, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except FileNotFoundError:
        raise RuntimeError(
            "FFmpeg not found. Make sure it is installed and in your PATH."
        )
    except subprocess.CalledProcessError:
        print(f"\n[!] FFmpeg error while processing file {input_path.name}")
        return False


def copy_media_file(source_path: Path, output_path: Path):
    """Simply copies a file if it exists."""
    if not source_path.exists():
        print(f"[!] Skipped (not found): {source_path}")
        return

    shutil.copy(source_path, output_path)
