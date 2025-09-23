from base64 import b64decode


def b64decode_forgiving(data_str: str) -> str:
    return b64decode(f"{data_str}{'=' * (4 - len(data_str) % 4)}").decode()
