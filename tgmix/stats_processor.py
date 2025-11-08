# tgmix/stats_processor.py
from rs_bpe.bpe import openai
# Currently, official toon_format lib has not implemented encode() function
from tqdm import tqdm


def compute_chat_stats(chat: dict, raw_chat: dict,
                       raw_export: str, encoded_output) -> dict:
    """Computes token, char, and other stats for the chat."""
    messages = chat.get("messages", [])

    stats: dict[str, int] = {
        "raw_total_messages": len(raw_chat.get("messages", [])),
        "total_messages": len(messages),
        "raw_total_tokens": 0,
        "total_tokens": 0,
        "raw_total_chars": 0,
        "total_chars": 0,
        "media_count": 0,
    }

    encoding = openai.o200k_base()

    for message in tqdm(messages, desc="Counting media in messages"):
        if "media" not in message:
            continue

        if isinstance(message["media"], str):
            stats["media_count"] += 1
        else:
            stats["media_count"] += len(message["media"])

    # Map author IDs to names for the final stats report
    stats["raw_total_tokens"] = encoding.count(raw_export)
    stats["total_tokens_toon"] = encoding.count(encoded_output)
    stats["raw_total_chars"] = len(raw_export)
    stats["total_chars_toon"] = len(encoded_output)

    return stats


def print_stats(stats: dict, config: dict, anonymised: bool) -> None:
    """Prints a formatted summary of the processing stats."""
    print("\n📊 Process Summary:\n"
          "─────────────────────\n"
          f"Total messages: {stats['raw_total_messages']:,} "
          f"-> {stats['total_messages']:,}\n"
          f"Output file tokens (OpenAI o200k): {stats['raw_total_tokens']:,}"
          f" -> {stats['total_tokens_toon']:,}\n"
          f"Total chars: {stats['raw_total_chars']:,}"
          f" -> {stats['total_chars_toon']:,}\n"
          f"Media tokens: unaccounted\n"
          f"Output file: {config['final_output_file']}\n"
          f"Anonymization: {'ON' if anonymised else 'OFF'}\n"
          "\n"
          "🎉 All Done!\n"
          "Your chat has been successfully packed.")
