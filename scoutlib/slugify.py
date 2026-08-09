"""Slugify text into URL-friendly slugs."""

import re
import unicodedata


def slugify(text: str, max_len: int = 40) -> str:
    """Lowercase ASCII words joined by single hyphens, truncated at a word
    boundary to `max_len`; "sortie" if nothing survives."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

    if max_len and len(text) > max_len:
        text = text[:max_len]
        if text.endswith("-"):
            text = text[:-1]
        elif "-" in text:  # cut landed mid-word: drop the partial word
            text = text[: text.rfind("-")]

    return text or "sortie"
