"""Slugify text into URL-friendly slugs."""

import re
import unicodedata


def slugify(text: str, max_len: int = 40) -> str:
    """Create a URL-friendly slug from text.

    - Lowercases the text
    - Strips diacritics (café → cafe)
    - Replaces non-alphanumeric chars with hyphens
    - Collapses multiple hyphens into one
    - Strips leading/trailing hyphens
    - Truncates at word boundary if max_len is exceeded
    - Falls back to 'sortie' if result is empty
    """
    # Strip diacritics: normalize to NFD, then remove combining characters
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # Lowercase
    text = text.lower()

    # Replace any non-alphanumeric character with a hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)

    # Strip leading/trailing hyphens
    text = text.strip("-")

    # Truncate at word boundary if too long
    if max_len and len(text) > max_len:
        text = text[:max_len]
        # Remove trailing hyphen
        if text.endswith("-"):
            text = text[:-1]
        else:
            # Truncate at the last word boundary (hyphen)
            last_hyphen = text.rfind("-")
            if last_hyphen > 0:
                text = text[:last_hyphen]

    return text or "sortie"
