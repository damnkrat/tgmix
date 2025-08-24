# tgmix/message_processor.py
import re
import shutil
from pathlib import Path

import phonenumbers
from tqdm import tqdm

from tgmix.media_processor import process_media
from tgmix.consts import MEDIA_KEYS

class Masking:
    def __init__(self, rules: dict | None, enabled: bool):
        self.rules = rules
        self.email_re = re.compile(
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}'
            r'[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}'
            r'[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}\b')
        self.enabled = enabled

    @staticmethod
    def _replace_phone_numbers(text: str, placeholder: str,
                               region: str | None) -> str:
        """
        Finds, filters, and replaces phone numbers for a single pass.

        :param text: The text to process.
        :param placeholder: The string to replace numbers with.
        :param region: The region to search for. If None, searches for
                       international numbers only.
        :return: Text with numbers replaced.
        """
        unique_matches = {}

        matcher = phonenumbers.PhoneNumberMatcher(text, region)
        for match in matcher:
            unique_matches[(match.start, match.end)] = match

        if not unique_matches:
            return text

        all_found = list(unique_matches.values())
        non_nested_matches = []

        for current_match in all_found:
            is_nested = False
            for other_match in all_found:
                if current_match is other_match:
                    continue
                if (other_match.start > current_match.start
                        or other_match.end < current_match.end):
                    continue

                is_nested = True
                break

            if not is_nested:
                non_nested_matches.append(current_match)

        sorted_matches = sorted(
            non_nested_matches,
            key=lambda m: m.start,
            reverse=True
        )

        for match in sorted_matches:
            text = f"{text[:match.start]}{placeholder}{text[match.end:]}"
        return text

    def apply(self, text: str) -> str:
        """Applies a set of masking rules to the given text."""
        if (not self.enabled) or (not self.rules) or (not text):
            return text

        # Order of application: Literals -> Presets -> Regex
        # This is to prevent a generic regex from masking a more specific literal.

        # Literals
        for literal, placeholder in self.rules.get("literals", {}).items():
            # Use re.escape to treat a literal as a plain string, not a regex:
            text = re.sub(
                re.escape(literal), placeholder, text, flags=re.IGNORECASE
            )

        # Presets (excluding 'authors', which is handled separately)
        preset_rules = self.rules.get("presets", {})
        if "email" in preset_rules:
            text = self.email_re.sub(preset_rules["email"], text)

        if "phone" in preset_rules:
            placeholder = preset_rules["phone"]
            region = self.rules.get("default_phone_region", "US")

            text = self._replace_phone_numbers(text, placeholder, region)
            text = self._replace_phone_numbers(text, placeholder, None)

        # Custom Regex
        for pattern, placeholder in self.rules.get("regex", {}).items():
            try:
                text = re.sub(pattern, placeholder, text)
            except re.error as e:
                print(f"[!] Warning: Invalid regex '{pattern}'. {e}")

        return text


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
                markdown_parts.append(f"```{entity.get('language', '')}\n"
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


def handle_init(package_dir: Path) -> None:
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


def stitch_messages(source_messages: list, target_dir: Path, media_dir: Path,
                    config: dict, masking_rules: dict,
                    do_anonymise: bool) -> tuple[list, dict, dict]:
    """
    Step 1: Iterates through messages, gathers "raw" parts,
    and then parses them at once. Returns processed messages and maps.
    """
    author_map = {}
    id_to_author_map = {}
    author_counter = 1
    masking = Masking(masking_rules, do_anonymise)

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
    pbar = tqdm(total=len(source_messages),
                desc="Step 1/2: Stitching messages")
    while next_id < len(source_messages):
        next_message = source_messages[next_id]
        pbar.update()

        if next_message.get("type") != "message":
            if next_message.get("type") != "service":
                next_id += 1
                continue

            stitched_messages.append(
                parse_service_message(id_to_author_map, next_message, masking))
            next_id += 1
            continue

        parsed_msg = parse_message_data(config, media_dir, next_message,
                                        target_dir, id_to_author_map, masking)

        next_id = combine_messages(
            config, id_alias_map, media_dir, next_message, next_id,
            parsed_msg, pbar, source_messages, target_dir, id_to_author_map,
            masking
        )
        stitched_messages.append(parsed_msg)

    pbar.close()
    return stitched_messages, id_alias_map, author_map


def check_attributes(message1: dict, message2: dict,
                     same: tuple = None, has: tuple = None) -> bool:
    if not same:
        same = ()
    if not has:
        has = ()

    for attribute in same:
        if message1.get(attribute) != message2.get(attribute):
            return False
    for attribute in has:
        if (attribute not in message1) or (attribute not in message2):
            return False
    return True


def combine_messages(config: dict, id_alias_map: dict, media_dir: Path,
                     message: dict, message_id: int, parsed_message: dict,
                     pbar: tqdm, source_messages: list, target_dir: Path,
                     id_to_author_map: dict, masking: Masking) -> int:
    next_id = message_id + 1
    if not len(source_messages) > next_id:
        return next_id

    next_message = source_messages[next_id]
    while (check_attributes(message, next_message,
                            ("from_id", "forwarded_from", "date_unixtime"))
           and (check_attributes(message, next_message, ("type",))
                and message.get("type") == "message")
           and ((check_attributes(message, next_message, has=("text",))
                 or (parsed_message["content"].get("media")
               and detect_media(next_message))))):
        pbar.update()

        next_text = masking.apply(
            format_text_entities_to_markdown(next_message.get("text")))

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

        if not len(source_messages) > next_id:
            return next_id
        next_message = source_messages[next_id]

    return next_id


def combine_reactions(next_message: dict, parsed_message: dict,
                      id_to_author_map: dict) -> None:
    """
    Merges raw reactions from next_msg_data with already processed
    reactions in parsed_message, applying minimization.
    """
    if "reactions" not in next_message:
        return

    if "reactions" not in parsed_message:
        parsed_message["reactions"] = []

    for next_reaction in next_message["reactions"]:
        next_shape, next_count = (
            next_reaction.get("emoji") or next_reaction.get("document_id")
            or "⭐️", next_reaction["count"])
        if next_reaction["type"] == "paid":
            next_shape = "⭐️"

        # Check if this reaction already exists in our list
        found = False
        for reaction_id in range(len(parsed_message["reactions"])):
            reaction = parsed_message["reactions"][reaction_id]
            if reaction.get(next_shape) is not None:
                parsed_message["reactions"][reaction_id][
                    next_shape] += next_count
                found = True
                break

        if not found:
            parsed_message["reactions"].append({
                next_shape: next_count
            })

        if not next_reaction.get("recent"):
            continue

        for reaction_id in range(len(parsed_message["reactions"])):
            if not parsed_message["reactions"][reaction_id].get(next_shape):
                continue

            parsed_message["reactions"][reaction_id].setdefault(
                "recent", []).extend(minimise_recent_reactions(
                next_reaction, id_to_author_map))


def minimise_recent_reactions(reactions: dict,
                              id_to_author_map: dict) -> list[dict]:
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
                       id_to_author_map: dict,
                       masking: Masking) -> dict:
    """Parses a single message using the author map."""
    parsed_message = {
        "id": message["id"],
        "time": message["date"],
        "author_id": id_to_author_map.get(message.get("from_id")),
        "content": {}
    }

    if message.get("text"):
        parsed_message["content"]["text"] = masking.apply(
            format_text_entities_to_markdown(message["text"]))
    if "reply_to_message_id" in message:
        parsed_message["reply_to_message_id"] = message["reply_to_message_id"]
    if media := process_media(message, target_dir, media_dir, config):
        parsed_message["content"]["media"] = media["source_file"]
    if "forwarded_from" in message:
        parsed_message["forwarded_from"] = masking.apply(
            message["forwarded_from"])
    if "edited" in message:
        parsed_message["edited_time"] = message["edited"]
    if "author" in message:
        parsed_message["post_author"] = masking.apply(
            message["author"])
    if "paid_stars_amount" in message:
        parsed_message["media_unlock_stars"] = message["paid_stars_amount"]
    if "poll" in message:
        answers = [
            masking.apply(answer) for answer in message["poll"]["answers"]
        ]
        parsed_message["poll"] = {
            "question": masking.apply(
                message["poll"]["question"]),
            "closed": message["poll"]["closed"],
            "answers": answers,
        }
    if "inline_bot_buttons" in message:
        parsed_message["inline_buttons"] = []

        for button_group in message["inline_bot_buttons"]:
            for button in button_group:
                if button["type"] == "callback":
                    parsed_message["inline_buttons"].append(button)
                elif button["type"] == "auth":
                    parsed_message["inline_buttons"].append(
                        {
                            "type": "auth",
                            "text": masking.apply(button["text"]),
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


def parse_service_message(id_to_author_map: dict, message: dict,
                          masking: Masking) -> dict:
    action_from = id_to_author_map.get(message.get("actor_id"))

    match message.get("action"):
        case "phone_call":
            data = {
                "id": message["id"],
                "type": "phone_call",
                "time": message["date"],
                "from": action_from,
                "discard_reason": message["discard_reason"],
            }

            if "duration_seconds" in message:
                data["duration"] = message["duration_seconds"]
            return data
        case "invite_to_group_call":
            members = [
                masking.apply(member) for member in message["members"]]
            return {
                "id": message["id"],
                "type": "invite_to_group_call",
                "time": message["date"],
                "from": action_from,
                "members": members,
            }
        case "pin_message":
            return {
                "id": message["id"],
                "type": "pin_message",
                "time": message["date"],
                "from": action_from,
                "message_id": message["message_id"],
            }
        case "send_star_gift":
            data = {
                "id": message["id"],
                "type": "send_star_gift",
                "time": message["date"],
                "from": action_from,
                "gift_id": message["gift_id"],
                "stars": message["stars"],
                "is_limited": message["is_limited"],
                "is_anonymous": message["is_anonymous"],
            }

            if message.get("gift_text"):
                data["text"] = message["gift_text"]
            return data
        case "paid_messages_price_change":
            return {
                "id": message["id"],
                "type": "paid_pm_price_change",
                "time": message["date"],
                "from": action_from,
                "price_stars": message["price_stars"],
                "is_broadcast_messages_allowed":
                    message["is_broadcast_messages_allowed"],
            }
        case "join_group_by_request":
            return {
                "id": message["id"],
                "type": "join_group_by_request",
                "time": message["date"],
                "from": action_from
            }
        case "join_group_by_link":
            return {
                "id": message["id"],
                "type": "join_group_by_link",
                "time": message["date"],
                "from": action_from,
                "inviter": message["inviter"]
            }
        case "invite_members":
            members = [
                masking.apply(member) for member in message["members"]]
            return {
                "id": message["id"],
                "type": "invite_members",
                "time": message["date"],
                "from": action_from,
                "members": members,
            }
        case "remove_members":
            members = [
                masking.apply(member) for member in message["members"]]
            return {
                "id": message["id"],
                "type": "remove_members",
                "time": message["date"],
                "from": action_from,
                "members": members,
            }

    print(f"[!] Unhandled service message({message['id']}): "
          f"{message['action']}")
    if masking.enabled:
        return {
            "id": message["id"],
            "type": message.get("action"),
            "time": message["date"],
            "from": action_from,
            "notice":
                "Not included due to unknown action and anonymization enabled."
        }
    return message


def fix_reply_ids(messages: list, alias_map: dict) -> None:
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
