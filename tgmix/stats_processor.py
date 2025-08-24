# tgmix/stats_processor.py
from rs_bpe.bpe import openai
from tqdm import tqdm
from ujson import dumps


def compute_chat_stats(chat: dict, raw_chat: dict) -> dict:
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
        if "media" not in message.get("content", {}):
            continue

        if isinstance(message["content"]["media"], str):
            stats["media_count"] += 1
        else:
            stats["media_count"] += len(message["content"]["media"])

    # Map author IDs to names for the final stats report
    pbar = tqdm(total=2, desc="Dumping chats for stats")
    chat_json = dumps(chat)
    raw_chat_json = dumps(raw_chat)
    pbar.update()
    pbar.set_description("Counting media files")
    stats["raw_total_tokens"] = encoding.count(raw_chat_json)
    stats["total_tokens"] = encoding.count(chat_json)
    pbar.update()
    pbar.set_description("Counting chars for files")
    stats["raw_total_chars"] = len(raw_chat_json)
    stats["total_chars"] = len(chat_json)
    pbar.close()

    return stats


def print_stats(stats: dict, config: dict, anonymised: bool) -> None:
    """Prints a formatted summary of the processing stats."""
    print("\n📊 Process Summary:\n"
          "─────────────────────\n"
          f"Total messages: {stats['raw_total_messages']:,} "
          f"-> {stats['total_messages']:,}\n"
          f"Output file tokens: {stats['raw_total_tokens']:,} "
          f"-> {stats['total_tokens']:,}\n"
          f"Total chars: {stats['raw_total_chars']:,} "
          f"-> {stats['total_chars']:,}\n"
          f"Output file: {config['final_output_json']}\n"
          f"Anonymization: {'ON' if anonymised else 'OFF'}\n"
          "\n"
          "🎉 All Done!\n"
          "Your chat has been successfully packed.")
