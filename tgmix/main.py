# tgmix/main.py
import argparse
import re
import shutil
from pathlib import Path

from ujson import JSONDecodeError, dump, loads

from tgmix import __version__
from tgmix.message_processor import fix_reply_ids, handle_init, stitch_messages
from tgmix.stats_processor import compute_chat_stats, print_stats

PACKAGE_DIR = Path(__file__).parent.resolve()


def load_config(target_dir: Path) -> dict:
    """
    Loads the configuration.
    Priority:
    1. tgmix_config.json in the target directory.
    2. Built-in config.json from the package (default).
    """
    local_config_path = target_dir / "tgmix_config.json"
    default_config_path = PACKAGE_DIR / "config.json"

    # First, try to load the local config if it exists
    if local_config_path.exists():
        try:
            print("[*] Local tgmix_config.json found. Using its settings.")
            return loads(open(local_config_path, encoding='utf-8').read())
        except JSONDecodeError as e:
            print(f"[!] Error: Invalid JSON format in {local_config_path}'.")
            raise e

    # If no local config, load the built-in one
    try:
        return loads(open(default_config_path, encoding='utf-8').read())
    except FileNotFoundError as e:
        print("[!] Critical Error: "
              "Built-in config.json not found in the package.")
        raise e


def create_summary_block(is_transcribed: bool = False,
                         has_large_files: bool = False) -> dict:
    """Creates an informational block for the AI model."""
    if is_transcribed:
        special_media_handling = ("Voice messages (.ogg) and video messages "
                                  "are transcribed to text")
    else:
        special_media_handling = (
            "Voice messages (.ogg) and video messages "
            "are wrapped in .mp4 files. The frame shows the original filename;"
            " the original audio is kept"
        )

    summary_block = {
        "tgmix_summary": {
            "purpose":
                "This file contains a structured representation of a "
                "Telegram chat export, prepared for AI analysis by TGMix",
            "format_description":
                "JSON object containing chat metadata and a list of messages. "
                "Each message uses an `author_id` to "
                "reference an author in the map, timestamp, Markdown text, "
                "and media data",
            "usage_guidelines": {
                "main_principle":
                    "Process this JSON together with any attached media "
                    "when such media exists.",
                "author_references":
                    "Authors are listed in the top-level `author_map`. Each "
                    "message refers to an author using a compact `author_id` "
                    "(e.g. 'U1'). Use this map to resolve the author's full "
                    "name. In your responses, always use the full name",
                "special_media_handling": special_media_handling,
                "paid_reactions": "⭐️ cost around $0.02",
            }
        }
    }

    if has_large_files:
        summary_block["tgmix_summary"]["usage_guidelines"][
            "large_media_handling"] = (
            "Large files are skipped, and their `source_file` "
            "is marked as 'B'. The size limit is user-configurable."
        )

    return summary_block


def parse_cli_dict(rules_list: list[str] | None) -> dict:
    """Parses 'key:value' strings from CLI into a single dictionary."""
    if not rules_list:
        return {}

    parsed = {}
    for item in rules_list:
        if ':' not in item:
            print(f"[!] Warning: Skipping invalid rule '{item}'. "
                  f"Format must be 'key:value'.")
            continue

        key, value = item.split(':', 1)
        parsed[key] = value
    return parsed


def run_processing(target_dir: Path, config: dict,
                   masking_rules: dict | None,
                   do_anonymise: bool) -> tuple[dict, dict]:
    """Main processing logic for the export."""
    export_json_path = target_dir / config['export_json_file']
    if not export_json_path.exists():
        print(f"[!] Error: '{config['export_json_file']}' not found"
              f" in {target_dir}")
        return {}, {}

    media_dir = target_dir / config['media_output_dir']
    if media_dir.exists():
        print(f"[*] Cleaning up '{config['media_output_dir']}'...")
        shutil.rmtree(media_dir)

    media_dir.mkdir(exist_ok=True)
    raw_chat = loads(open(export_json_path, encoding="utf-8").read())

    # Stitch messages together
    stitched_messages, id_alias_map, author_map = stitch_messages(
        raw_chat["messages"], target_dir, media_dir, config, masking_rules,
        do_anonymise
    )

    fix_reply_ids(stitched_messages, id_alias_map)

    chat_name = raw_chat.get("name")
    if masking_rules and ("authors" in masking_rules.get("presets", {})):
        template = masking_rules["presets"]["authors"]
        print("[*] Anonymizing author names...")

        for compact_id in author_map.keys():
            numeric_id_match = re.search(r'\d+', compact_id)
            if not numeric_id_match:
                continue

            unique_placeholder = template.replace(
                ']', f'_{numeric_id_match.group(0)}]'
            )
            author_map[compact_id] = unique_placeholder

        chat_name = "[ANONYMIZED CHAT]"

    # Format and save the final result
    processed_chat = create_summary_block(
        False,
        "(File not included. "
        "Change data exporting settings to download.)" in str(raw_chat)
    )
    processed_chat["chat_name"] = chat_name
    processed_chat["author_map"] = author_map
    processed_chat["messages"] = stitched_messages

    return processed_chat, raw_chat


def main():
    """Main entry point for the CLI application."""
    parser = argparse.ArgumentParser(
        description="Process a Telegram chat export for AI analysis.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to the directory with the Telegram export.\n"
             "If not provided, processes the current directory."
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create a default 'tgmix_config.json' in the current directory."
    )
    parser.add_argument(
        "--version",
        "-v",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the version number and exit."
    )
    parser.add_argument(
        "-a",
        "--anonymize",
        action="store_true",
        help="Enable anonymization of message content. "
             "Rules are taken from config or overridden by CLI flags."
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Disable statistics computation and printing."
    )
    parser.add_argument(
        '--mask-preset',
        nargs='+',
        metavar='PRESET',
        help='A list of built-in presets to use (e.g., phone email authors). '
             'Overrides presets in config.'
    )
    parser.add_argument(
        '--mask-literal',
        nargs='+',
        metavar='"LITERAL:REPLACEMENT"',
        help="A list of exact phrases to mask, with their replacements. "
             "Overrides literals in config."
    )
    parser.add_argument(
        '--mask-regex',
        nargs='+',
        metavar='"REGEX:REPLACEMENT"',
        help="A list of regex patterns to mask, with their replacements. "
             "Overrides regex rules in config."
    )

    args = parser.parse_args()

    if args.init:
        handle_init(PACKAGE_DIR)
        return

    target_directory = Path(args.path).resolve() if args.path else Path.cwd()
    if target_directory.is_file():
        if target_directory.suffix != ".json":
            print("[!] Error: Path must be a directory, not a file.")
            return

        target_directory = target_directory.parent

    config = load_config(target_directory)
    masking_rules: dict | None = dict()

    if args.anonymize or config.get("anonymize", False):
        print("[*] Anonymization enabled.")
        masking_rules = {
            "default_phone_region": config.get("default_phone_region", "RU")
        }

        default_presets = config.get("mask_presets", {})

        active_presets = (
            args.mask_preset if args.mask_preset else
            default_presets.keys()
        )
        masking_rules["presets"] = {
            preset: default_presets.get(
                preset, f"[{preset.upper()}]") for preset in active_presets
        }
        masking_rules["literals"] = (
            parse_cli_dict(args.mask_literal) if args.mask_literal else
            config.get("mask_literals", {})
        )
        masking_rules["regex"] = (
            parse_cli_dict(args.mask_regex) if args.mask_regex else
            config.get("mask_regex", {})
        )

    print(f"--- Starting TGMix on directory: {target_directory} ---")
    processed_chat, raw_chat = run_processing(
        target_directory, config, masking_rules, args.anonymize)

    if not processed_chat:
        return

    output_path = target_directory / config['final_output_json']
    with open(output_path, "w", encoding="utf-8") as file:
        dump(processed_chat, file, ensure_ascii=False, indent=2)

    if args.no_stats:
        return
    if not config.get("enable_stats", True):
        return

    if not (stats := compute_chat_stats(processed_chat, raw_chat)):
        print("[!] Error: Failed to compute statistics.")
        return
    print_stats(stats, config, args.anonymize)


if __name__ == "__main__":
    main()
