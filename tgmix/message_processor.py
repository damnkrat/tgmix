# tgmix/message_processor.py
import shutil
from pathlib import Path

from tqdm import tqdm

from tgmix.media_processor import (convert_to_video_with_filename,
                                   copy_media_file)

MEDIA_KEYS = [
    "photo", "video_file", "voice_message",
    "video_message", "sticker", "file"
]


def detect_media(message: dict) -> str:
    for key in MEDIA_KEYS:
        if key in message:
            return key
    return ""


def format_text_entities_to_markdown(entities: list) -> str:
    """
    Converts text_entities to Markdown.
    """
    if not entities:
        return ""
    if isinstance(entities, str):
        return entities

    markdown_parts = []
    for entity in entities:
        if isinstance(entity, str):
            markdown_parts.append(entity)
            continue

        text = entity.get("text", "")
        entity_type = entity.get("type", "plain")

        # Skip empty elements that might create extra whitespace
        if not text:
            continue

        match entity_type:
            case "bold":
                markdown_parts.append(f"**{text}**")
            case "italic":
                markdown_parts.append(f"*{text}*")
            case "strikethrough":
                markdown_parts.append(f"~~{text}~~")
            case "code":
                markdown_parts.append(f"`{text}`")
            case "pre":
                markdown_parts.append(f"```{entity.get("language", "")}\n"
                                      f"{text}\n```")
            case "link":
                markdown_parts.append(text)
            case "text_link":
                url = entity.get("href", "#")
                markdown_parts.append(f"[{text}]({url})")
            case "mention":
                markdown_parts.append(text)
            case _:  # plain and others
                markdown_parts.append(text)

    return "".join(markdown_parts)


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

    # Decide how to process the file. Halted for next updates
    # if media_type in ["voice_message", "video_message"]:
    #     convert_to_video_with_filename(
    #         source_path, prepared_path, config['ffmpeg_drawtext_settings']
    #     )
    # else:
    copy_media_file(source_path, prepared_path)

    filename = msg[media_type]
    if filename in ("(File not included. "
                    "Change data exporting settings to download.)",
                    "(File exceeds maximum size. "
                    "Change data exporting settings to download.)"):
        filename = "B"

    return {"type": media_type, "source_file": filename}


def handle_init(package_dir):
    """Creates tgmix_config.json in the current directory from a template."""
    config_template_path = package_dir / "config.json"
    target_config_path = Path.cwd() / "tgmix_config.json"

    if not config_template_path.exists():
        print("[!] Critical Error: config.json template not found in package.")
        return

    if target_config_path.exists():
        print(f"[!] File 'tgmix_config.json' already exists here.")
        return

    shutil.copy(config_template_path, target_config_path)
    print(f"[+] Configuration file 'tgmix_config.json' created successfully.")


def stitch_messages(source_messages, target_dir, media_dir, config):
    """
    Step 1: Iterates through messages, gathers "raw" parts,
    and then parses them at once. Returns processed messages and maps.
    """
    author_map = {}
    id_to_author_map = {}
    author_counter = 1

    for next_message in source_messages:
        author_id = next_message.get("from_id")
        if not author_id or author_id in id_to_author_map:
            continue

        compact_id = f"U{author_counter}"
        id_to_author_map[author_id] = compact_id
        author_map[compact_id] = {
            "name": next_message.get("from"),
            "id": author_id
        }
        author_counter += 1

    stitched_messages = []
    id_alias_map = {}

    next_id = 0
    pbar = tqdm(source_messages, desc="Step 1/2: Stitching messages")
    while next_id < len(source_messages):
        next_message = source_messages[next_id]
        pbar.update()

        if next_message.get("type") != "message":
            next_id += 1
            continue

        parsed_msg = parse_message_data(config, media_dir, next_message,
                                        target_dir, id_to_author_map)

        next_id = combine_messages(
            config, id_alias_map, media_dir, next_message, next_id,
            parsed_msg, pbar, source_messages, target_dir, id_to_author_map
        )
        stitched_messages.append(parsed_msg)

    pbar.close()
    return stitched_messages, id_alias_map, author_map


def combine_messages(config, id_alias_map, media_dir, message, message_id,
                     parsed_message, pbar, source_messages, target_dir,
                     id_to_author_map):
    next_id = message_id + 1
    if not len(source_messages) > next_id:
        return next_id

    next_message = source_messages[next_id]
    while (next_id < len(source_messages) and
           next_message.get("from_id") == message.get("from_id") and
           next_message.get("forwarded_from") == message.get(
                "forwarded_from") and next_message.get(
                "date_unixtime") == message.get("date_unixtime") and (
                   next_message.get("text") and message.get("text") or (
                   parsed_message["content"].get("media") and detect_media(next_message)))):
        pbar.update()

        next_text = format_text_entities_to_markdown(
            next_message.get("text"))
        if next_text:
            if not parsed_message["content"].get("text"):
                parsed_message["content"]["text"] = next_text
            else:
                parsed_message["content"]["text"] += f"\n\n{next_text}"

        if media := process_media(next_message, target_dir, media_dir, config):
            if isinstance(parsed_message["content"].get("media"), str):
                parsed_message["content"]["media"] = [
                    parsed_message["content"]["media"]]
            elif not parsed_message["content"].get("media"):
                parsed_message["content"]["media"] = []

            parsed_message["content"]["media"].append(media["source_file"])

        combine_reactions(next_message, parsed_message, id_to_author_map)

        id_alias_map[next_message["id"]] = message["id"]
        next_id += 1
        next_message = source_messages[next_id]

    return next_id


def combine_reactions(next_message, parsed_message, id_to_author_map):
    """
    Merges raw reactions from next_msg_data with already processed
    reactions in parsed_message, applying minimization.
    """
    if "reactions" not in next_message:
        return

    if "reactions" not in parsed_message:
        parsed_message["reactions"] = []

    for next_reaction in next_message["reactions"]:
        next_shape, next_count = (next_reaction[next_reaction["type"]],
                        next_reaction["count"])

        # Check if this reaction already exists in our list
        for reaction_id in range(len(parsed_message["reactions"])):
            reaction = parsed_message["reactions"][reaction_id]
            if reaction != next_shape:
                continue

            parsed_message["reactions"][reaction_id] += next_count
            break

        if next_message["reactions"][-1].get("recent"):
            next_message["reactions"][-1][
                "recent"] = minimise_recent_reactions(
                next_reaction, id_to_author_map)
            continue

        parsed_message["reactions"].append({
            next_shape: next_count
        })

        if next_message["reactions"][-1].get("recent"):
            next_message["reactions"][-1][
                "recent"] = minimise_recent_reactions(
                next_reaction, id_to_author_map)


def minimise_recent_reactions(reactions, id_to_author_map) -> list[dict]:
    recent = []
    for reaction in reactions["recent"]:
        if author_id := id_to_author_map.get(reaction["from_id"]):
            recent.append({
                "author_id": author_id,
                "date": reaction["date"]
            })
            continue

        recent.append({
            "from": reaction["from"],
            "from_id": reaction["from_id"],
            "date": reaction["date"]
        })

    return recent


def parse_message_data(config: dict, media_dir: Path,
                       message: dict, target_dir: Path,
                       id_to_author_map: dict):
    """Parses a single message using the author map."""
    parsed_message = {
        "id": message["id"],
        "time": message["date"],
        "author_id": id_to_author_map.get(message.get("from_id")),
        "content": {}
    }

    if message.get("text"):
        parsed_message["content"]["text"] = format_text_entities_to_markdown(
            message["text"])
    if "reply_to_message_id" in message:
        parsed_message["reply_to_message_id"] = message["reply_to_message_id"]
    if media := process_media(message, target_dir, media_dir, config):
        parsed_message["content"]["media"] = media["source_file"]
    if "forwarded_from" in message:
        parsed_message["forwarded_from"] = message["forwarded_from"]
    if "edited" in message:
        parsed_message["edited_time"] = message["edited"]
    if "author" in message:
        parsed_message["post_author"] = message["author"]
    if "paid_stars_amount" in message:
        parsed_message["media_unlock_stars"] = message["paid_stars_amount"]
    if "poll" in message:
        parsed_message["poll"] = {
            "question": message["poll"]["question"],
            "closed": message["poll"]["closed"],
            "answers": message["poll"]["answers"],
        }
    if "inline_bot_buttons" in message:
        for button_group in message["inline_bot_buttons"]:
            for button in button_group:
                parsed_message["inline_buttons"] = []

                if button["type"] == "callback":
                    parsed_message["inline_buttons"].append(button)
                elif button["type"] == "auth":
                    parsed_message["inline_buttons"].append(
                        {
                            "type": "auth",
                            "text": "Открыть комментарии",
                            "data": button["data"],
                        }
                    )
    if "reactions" in message:
        parsed_message["reactions"] = []
        for reaction in message["reactions"]:
            shape_value = reaction.get("emoji") or reaction.get(
                "document_id") or "⭐️"

            parsed_message["reactions"].append({
                shape_value: reaction["count"]
            })

            if reaction.get("recent"):
                parsed_message["reactions"][-1][
                    "recent"] = minimise_recent_reactions(
                    reaction, id_to_author_map)

    return parsed_message


def fix_reply_ids(messages, alias_map):
    """
    Goes through the stitched messages and fixes reply IDs
    using the alias map.
    """
    for message in tqdm(messages, desc="Step 2/2: Fixing replies"):
        if "reply_to_message_id" not in message:
            continue

        reply_id = message["reply_to_message_id"]
        if reply_id not in alias_map:
            continue

        message["reply_to_message_id"] = alias_map[reply_id]
