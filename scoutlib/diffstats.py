"""Parse `git diff --shortstat` output."""

import re

_SHORTSTAT_RE = re.compile(
    r"\s*(\d+)\s+files?\s+changed"
    r"(?:,\s*(\d+)\s+insertions?\(\+\))?"
    r"(?:,\s*(\d+)\s+deletions?\(-\))?"
)


def parse_shortstat(line: str) -> dict:
    """Return a dict with keys files, insertions, deletions.

    Unrecognised or empty input yields all zeroes.
    """
    line = line.strip()
    if not line:
        return {"files": 0, "insertions": 0, "deletions": 0}

    m = _SHORTSTAT_RE.fullmatch(line)
    if not m:
        return {"files": 0, "insertions": 0, "deletions": 0}

    return {
        "files": int(m.group(1)),
        "insertions": int(m.group(2)) if m.group(2) else 0,
        "deletions": int(m.group(3)) if m.group(3) else 0,
    }
