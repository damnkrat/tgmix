# tgmix/message_processor.py
import shutil
from pathlib import Path

from tqdm import tqdm

from tgmix.media_processor import (convert_to_video_with_filename,
                                   copy_media_file)


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
    media_keys = [
        "photo", "video_file", "voice_message",
        "video_message", "sticker", "file"
    ]
    media_type = next((key for key in media_keys if key in msg), None)

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

    return {"type": media_type, "source_file": msg[media_type]}


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
    and then parses them once. Returns processed messages and maps.
    """
    author_map = {}
    id_to_author_map = {}
    author_counter = 1

    for message in source_messages:
        author_id = message.get("from_id")
        if not author_id or author_id in id_to_author_map:
            continue

        compact_id = f"U{author_counter}"
        id_to_author_map[author_id] = compact_id
        author_map[compact_id] = {
            "name": message.get("from"),
            "id": author_id
        }
        author_counter += 1

    stitched_messages = []
    id_alias_map = {}

    message_id = 0
    pbar = tqdm(source_messages, desc="Step 1/2: Stitching messages")
    while message_id < len(source_messages):
        message = source_messages[message_id]
        pbar.update()

        if message.get("type") != "message":
            message_id += 1
            continue

        parsed_msg = parse_message_data(config, media_dir, message,
                                        target_dir, id_to_author_map)

        next_id = combine_messages(
            config, id_alias_map, media_dir, message, message_id,
            parsed_msg, pbar, source_messages, target_dir, id_to_author_map
        )
        stitched_messages.append(parsed_msg)
        message_id = next_id

    pbar.close()
    return stitched_messages, id_alias_map, author_map


def combine_messages(config, id_alias_map, media_dir, message, message_id,
                     parsed_msg, pbar, source_messages, target_dir,
                     id_to_author_map):
    next_id = message_id + 1
    while (next_id < len(source_messages) and
           source_messages[next_id].get(
               "from_id") == message.get("from_id") and
           source_messages[next_id].get(
               "date_unixtime") == message.get("date_unixtime") and
           source_messages[next_id].get(
               "forwarded_from") == message.get("forwarded_from") and
           source_messages[next_id].get("text") and message.get("text")):

        pbar.update()
        next_msg_data = source_messages[next_id]

        next_text = format_text_entities_to_markdown(
            next_msg_data.get("text"))
        if next_text:
            parsed_msg["content"]["text"] += f"\n\n{next_text}"

        if ("media" not in parsed_msg["content"]
                or not parsed_msg["content"].get("media")):
            if media := process_media(
                    next_msg_data, target_dir, media_dir, config):
                parsed_msg["content"]["media"] = media

        combine_reactions(next_msg_data, parsed_msg, id_to_author_map)

        id_alias_map[next_msg_data["id"]] = message["id"]
        next_id += 1

    return next_id


def combine_reactions(next_msg_data, parsed_message, id_to_author_map):
    """
    Merges raw reactions from next_msg_data with already processed
    reactions in parsed_message, applying minimization.
    """
    if "reactions" not in next_msg_data:
        return

    if "reactions" not in parsed_message:
        parsed_message["reactions"] = []

    for next_reactions in next_msg_data["reactions"]:
        next_shape_value = next_reactions.get("emoji") or next_reactions.get(
            "document_id")

        # Check if this reaction already exists in our list
        existing_reaction = None
        for reaction in parsed_message["reactions"]:
            # What is there is more same reactions?
            if reaction.get(reaction['type']) != next_shape_value:
                continue

            existing_reaction = (
                reaction if reaction['type'] != "paid" else "⭐️")
            break

        if existing_reaction:
            existing_reaction["count"] += next_reactions.get("count", 0)
            existing_reaction["recent"].extend(minimise_recent_reactions(
                next_reactions, id_to_author_map))
            return

        parsed_message["reactions"].append({
            "type": next_reactions["type"],
            "count": next_reactions["count"],
            next_reactions['type']: next_shape_value,
        })

        if last_reaction := next_msg_data["reactions"][-1].get("recent"):
            last_reaction["recent"] = minimise_recent_reactions(
                next_reactions, id_to_author_map)


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
        "message_id": message["id"],
        "timestamp": message["date"],
        "author_id": id_to_author_map.get(message.get("from_id")),
        "content": {}
    }

    if message.get("text"):
        parsed_message["content"]["text"] = format_text_entities_to_markdown(
            message["text"])
    if "reply_to_message_id" in message:
        parsed_message["reply_to_message_id"] = message["reply_to_message_id"]
    if media := process_media(message, target_dir, media_dir, config):
        parsed_message["content"]["media"] = media
    if "forwarded_from" in message:
        parsed_message["forwarded_from"] = message["forwarded_from"]
    if "edited" in message:
        parsed_message["edited_time"] = message["edited"]
    if "author" in message:
        parsed_message["post_author"] = message["author"]
    if "poll" in message:
        parsed_message["poll"] = {
            "question": message["poll"]["question"],
            "closed": message["poll"]["closed"],
            "answers": message["poll"]["answers"],
        }
    if "reactions" in message:
        parsed_message["reactions"] = []
        for reaction in message["reactions"]:
            shape_value = reaction.get("emoji") or reaction.get(
                "document_id") or "⭐️"

            parsed_message["reactions"].append({
                "type": reaction["type"],
                "count": reaction["count"],
                reaction['type']: shape_value
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
