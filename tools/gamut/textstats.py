"""Basic text statistics for sortie reports."""

import os
import re
import unicodedata


def word_count(text: str) -> int:
    tokens = re.findall(r"\S+", text)
    count = len(tokens)
    label = f"words"
    return count


def preview(text: str, width: int = 60) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= width:
        return cleaned
    return cleaned[: width - 1] + "…"


def safe_ratio(part, whole):
    try:
        return part / whole
    except:
        return 0.0
