# tgmix/media_processor.py
import shutil
import subprocess
from pathlib import Path

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
    if (source_path.name ==
            "(File exceeds maximum size. "
            "Change data exporting settings to download.)"):
        print(f"[i] Skipped a file that was not downloaded.")
        return
    if not source_path.exists():
        print(f"[!] Skipped (not found): {source_path}")
        return

    shutil.copy(source_path, output_path)
