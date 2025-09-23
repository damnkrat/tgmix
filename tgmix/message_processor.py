# tgmix/message_processor.py
import re
from pathlib import Path

import phonenumbers
from tqdm import tqdm

from tgmix.media_processor import Media
from tgmix.utils import b64decode_forgiving


class Masking:
    def __init__(self, rules: dict | None, enabled: bool):
        self.rules = rules
        self.email_re = re.compile(
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}'
            r'[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}'
            r'[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}\b')
        self.name_to_authors_map: dict[str, list] = {}
        self.enabled = enabled

        if not rules.get("regex"):
            return

        rules_regex = {}
        for rule, placeholder in rules["regex"].items():
            try:
                rules_regex.update({re.compile(rule): placeholder})
            except re.error as e:
                print(f"[!] Warning: Invalid regex '{rule}'. {e}")
        self.rules["regex"] = rules_regex

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
        if not isinstance(text, str):
            return text

        # Order of application: Literals -> Presets -> Regex
        # This is to prevent a generic regex
        # from masking a more specific literal.

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
            region = self.rules.get("default_phone_region", "RU")

            text = self._replace_phone_numbers(text, placeholder, region)
            text = self._replace_phone_numbers(text, placeholder, None)

        # Custom Regex
        for pattern_re, placeholder in self.rules.get("regex", {}).items():
            try:
                text = pattern_re.sub(placeholder, text)
            except re.error as e:
                print(f"[!] Warning: Invalid regex '{pattern_re.pattern}'. "
                      f"{e}")

        return text

    def author(self, text: str):
        if not self.enabled:
            return text

        author = self.name_to_authors_map.get(text, text)

        if not author:
            return text
        if len(author) == 1:
            return author[0]
        return author


class MessageProcessor:
    def __init__(self, target_dir: Path, media_dir: Path, mark_media: bool,
                 masking_rules: dict, do_anonymise: bool) -> None:
        self.media = Media(target_dir, media_dir, mark_media)
        self.pbar = None
        self.id_to_author_map = {}
        self.masking = Masking(masking_rules, do_anonymise)
        self.id_alias_map = {}

    def format_text_entities_to_markdown(self, entities: list) -> str:
        """
        Converts text_entities to Markdown.
        """
        if not entities:
            return ""
        if isinstance(entities, str):
            return entities

        masking_presets = self.masking.rules.get("presets")

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
                case "email":
                    if self.masking.enabled and (
                            mask := masking_presets.get("email")):
                        markdown_parts.append(mask)
                        continue
                    markdown_parts.append(text)
                case "phone":
                    if self.masking.enabled and (
                            mask := masking_presets.get("phone")):
                        markdown_parts.append(mask)
                        continue
                    markdown_parts.append(text)
                case "mention" | "mention_name":
                    if self.masking.enabled and (
                            mask := masking_presets.get("authors")):
                        if author_id := self.id_to_author_map.get(
                                f"user{text}"):
                            markdown_parts.append(f"[{author_id}]")
                            continue
                        markdown_parts.append(mask)
                        continue
                    markdown_parts.append(text)
                case "underline":
                    markdown_parts.append(f"<u>{text}</u>")
                case "spoiler":
                    markdown_parts.append(f"||{text}||")
                case "custom_emoji":
                    markdown_parts.append(f"[emoji_{entity['document_id']}]")
                case "bank_card":
                    if self.masking.enabled and (
                            mask := masking_presets.get("bank_card")):
                        markdown_parts.append(mask)
                        continue
                    markdown_parts.append(text)
                case "blockquote":
                    markdown_parts.append(f"> {text}")
                case "link":
                    if self.masking.enabled and (
                            mask := masking_presets.get("link")):
                        markdown_parts.append(mask)
                        continue
                    markdown_parts.append(text)
                case "text_link":
                    if self.masking.enabled and (
                            mask := masking_presets.get("link")):
                        markdown_parts.append(f"[{entity.get('text')}]"
                                              f"({mask})")
                        continue
                    markdown_parts.append(f"[{entity.get('text')}]"
                                          f"({entity.get('href', '#')})")
                case "bot_command" | "hashtag" | "cashtag":
                    markdown_parts.append(text)
                case _:  # plain and others
                    print(f"[!] Warning: Unknown entity type '{entity_type}'")
                    markdown_parts.append(text)

        return "".join(markdown_parts)

    def stitch_messages(
            self, source_messages: list) -> tuple[list, dict, bool]:
        """
        Step 1: Iterates through messages, gathers "raw" parts,
        and then parses them at once. Returns processed messages and maps.
        """
        author_map = {}
        author_counter = 1

        for next_message in source_messages:
            author_id = next_message.get("from_id")
            if not author_id or author_id in self.id_to_author_map:
                continue

            compact_id = f"U{author_counter}"
            self.id_to_author_map[author_id] = compact_id
            author_map[compact_id] = {
                "name": next_message.get("from"),
                "id": author_id
            }
            self.masking.name_to_authors_map.setdefault(
                next_message.get("from"), []).append(compact_id)
            author_counter += 1

        stitched_messages = []

        next_id = 0
        self.pbar = tqdm(total=len(source_messages),
                    desc="Step 1/2: Stitching messages")
        while next_id < len(source_messages):
            next_message = source_messages[next_id]
            self.pbar.update()

            if next_message.get("type") != "message":
                if next_message.get("type") != "service":
                    next_id += 1
                    continue

                stitched_messages.append(
                    self.parse_service_message(next_message))
                next_id += 1
                continue

            parsed_msg = self.parse_message_data(next_message)

            next_id = self.combine_messages(
                next_message, next_id, parsed_msg,
                source_messages
            )
            stitched_messages.append(parsed_msg)

        self.pbar.close()
        return stitched_messages, author_map, self.masking.enabled

    @staticmethod
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

    def combine_messages(self, message: dict,
                         message_id: int, parsed_message: dict,
                         source_messages: list) -> int:
        next_id = message_id + 1
        if not len(source_messages) > next_id:
            return next_id

        next_message = source_messages[next_id]
        while self.check_attributes(
                message, next_message,
                ("from_id", "forwarded_from", "date_unixtime")):

            self.pbar.update()

            next_text = self.masking.apply(
                self.format_text_entities_to_markdown(
                    next_message.get("text")))

            if next_text:
                if not parsed_message.get("text"):
                    parsed_message["text"] = next_text
                else:
                    parsed_message["text"] += f"\n\n{next_text}"

            if file_name := self.media.process(next_message):
                if isinstance(parsed_message.get("media"), str):
                    parsed_message["media"] = [
                        parsed_message["media"]]
                elif not parsed_message.get("media"):
                    parsed_message["media"] = []

                parsed_message["media"].append(file_name)

            self.combine_reactions(next_message, parsed_message)

            self.id_alias_map[next_message["id"]] = message["id"]
            next_id += 1

            if not len(source_messages) > next_id:
                return next_id
            next_message = source_messages[next_id]

        return next_id

    def combine_reactions(self, next_message: dict,
                          parsed_message: dict) -> None:
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
                if not parsed_message["reactions"][reaction_id].get(
                        next_shape):
                    continue

                parsed_message["reactions"][reaction_id].setdefault(
                    "recent", []).extend(self.minimise_recent_reactions(
                    next_reaction))

    def minimise_recent_reactions(self, reactions: dict) -> list[dict]:
        recent = []
        for reaction in reactions["recent"]:
            if author_id := self.id_to_author_map.get(reaction["from_id"]):
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

    def parse_message_data(self, message: dict) -> dict:
        """Parses a single message using the author map."""
        parsed_message = {
            "id": message["id"],
            "time": message["date"],
            "author_id": self.id_to_author_map.get(message.get("from_id"))
        }

        if message.get("text"):
            parsed_message["text"] = self.masking.apply(
                self.format_text_entities_to_markdown(message["text"]))
        if "reply_to_message_id" in message:
            parsed_message["reply_to_message_id"] = message[
                "reply_to_message_id"]
        if file_name := self.media.process(message):
            parsed_message["media"] = file_name
        if "forwarded_from" in message:
            parsed_message["forwarded_from"] = self.masking.author(
                message["forwarded_from"])
        if "edited" in message:
            parsed_message["edited_time"] = message["edited"]
        if "author" in message:
            parsed_message["post_author"] = self.masking.author(
                message["author"])
        if "paid_stars_amount" in message:
            parsed_message["media_unlock_stars"] = message[
                "paid_stars_amount"]
        if "poll" in message:
            parsed_message["poll"] = {
                "question": self.masking.apply(
                    self.format_text_entities_to_markdown(
                        message["poll"]["question"])),
                "closed": message["poll"]["closed"],
                "answers": [
                    self.masking.apply(
                        self.format_text_entities_to_markdown(answer["text"]))
                    for answer in message["poll"]["answers"]],
            }
            # sometimes text is messed up like this:
            # ['What? ', {'type': 'custom_emoji', 'text': '🤔',
            #             'document_id': '5443115090486246051'}, '']
        if "contact_information" in message:
            if self.masking.enabled and (
                    self.masking.rules["presets"].get("phone")):
                parsed_message["contact_information"] = "[CONTACT]"
            else:
                parsed_message["contact_information"] = message[
                    "contact_information"]
        if "via_bot" in message:
            parsed_message["via_bot"] = message["via_bot"]
        if "inline_bot_buttons" in message:
            parsed_message["inline_buttons"] = []
            for button_group in message["inline_bot_buttons"]:
                for button in button_group:
                    parsed_message["inline_buttons"].append(
                        self.parse_inline_button(button))
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
                        "recent"] = self.minimise_recent_reactions(reaction)

        return parsed_message

    def parse_inline_button(self, button) -> dict:
        text = self.masking.apply(button["text"] or "")

        has_encoded_data = "dataBase64" in button
        has_data = "data" in button
        if has_data or has_encoded_data:
            if has_encoded_data and not has_data:
                button_data = b64decode_forgiving(button["dataBase64"])
            elif has_encoded_data and has_data:
                button_data = [
                    b64decode_forgiving(button["dataBase64"]),
                    button["data"]]
            else:
                button_data = button["data"]
        else:
            button_data = ""

        if button["type"] == "callback":
            return {
                "type": button["type"],
                "text": text,
                "callback": button_data,
            }
        elif button["type"] == "auth":
            return {
                    "text": text,
                    "data": button_data,
                }
        elif button["type"] == "url":
                return {
                    "text": text,
                    "url": button_data,
                }
        elif button["type"] == "switch_inline_same":
            return {
                "type": button["type"],
                "text": text,
            }
        elif button["type"] == "switch_inline":
            data = {
                "type": button["type"],
                "text": text,
            }
            if button_data:
                data["data"] = button_data

            return data
        elif button["type"] == "game":
            return {
                "type": button["type"],
                "text": text,
            }
        else:
            button["text"] = text
            print("[!] Warning: Unknown inline button type "
                  f"'{button['type']}'")
            return button

    def parse_service_message(self, message: dict) -> dict:
        action_from = self.id_to_author_map.get(message.get("actor_id"))
        if members := message.get("members", []):
            members = [
                self.masking.author(member) for member in message["members"]]

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
            case "group_call":
                data = {
                    "id": message["id"],
                    "type": "group_call",
                    "time": message["date"],
                    "from": action_from,
                }

                if "duration" in message:
                    data["duration"] = message["duration"]
                return data
            case "invite_to_group_call":
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
                    "inviter": self.masking.author(message["inviter"])
                }
            case "invite_members":
                return {
                    "id": message["id"],
                    "type": "invite_members",
                    "time": message["date"],
                    "from": action_from,
                    "members": members,
                }
            case "remove_members":
                return {
                    "id": message["id"],
                    "type": "remove_members",
                    "time": message["date"],
                    "from": action_from,
                    "members": members,
                }
            case "create_channel":
                return {
                    "id": message["id"],
                    "type": "create_channel",
                    "time": message["date"],
                    "from": action_from,
                    "title": message["title"],
                }
            case "edit_group_title":
                return {
                    "id": message["id"],
                    "type": "edit_group_title",
                    "time": message["date"],
                    "from": action_from,
                    "title": message["title"],
                }
            case "edit_group_photo":
                return {
                    "id": message["id"],
                    "type": "edit_group_photo",
                    "time": message["date"],
                    "from": action_from,
                    "photo": message["photo"],
                }
            case "score_in_game":
                return {
                    "id": message["id"],
                    "type": "score_in_game",
                    "time": message["date"],
                    "from": action_from,
                    "score": message["score"],
                }
            case "topic_created":
                return {
                    "id": message["id"],
                    "type": "topic_created",
                    "time": message["date"],
                    "from": action_from,
                    "title": message["title"]
                }
            case "topic_edit":
                return {
                    "id": message["id"],
                    "type": "topic_edit",
                    "time": message["date"],
                    "from": action_from,
                    "title": message["new_title"],
                    "icon_emoji_id": message["new_icon_emoji_id"],
                }
            case "boost_apply":
                return {
                    "id": message["id"],
                    "type": "boost_apply",
                    "time": message["date"],
                    "from": action_from,
                    "boosts": message["boosts"],
                }

        print(f"[!] Unhandled service message({message['id']}): "
              f"{message['action']}")
        if self.masking.enabled:
            data = {
                "id": message["id"],
                "type": message.get("action"),
                "time": message["date"],
                "from": action_from,
                "notice":
                    "Not included due to unknown action "
                    "and anonymization enabled."
            }

            if "members" in message:
                data["members"] = members
            return data
        return message

    def fix_reply_ids(self, messages: list) -> None:
        """
        Goes through the stitched messages and fixes reply IDs
        using the alias map.
        """
        for message in tqdm(messages, desc="Step 2/2: Fixing replies"):
            if "reply_to_message_id" not in message:
                continue

            reply_id = message["reply_to_message_id"]
            if reply_id not in self.id_alias_map:
                continue

            message["reply_to_message_id"] = self.id_alias_map[reply_id]
