"""Parse `git diff --shortstat` output."""

import re

_SHORTSTAT_RE = re.compile(
    r"(\d+)\s+files?\s+changed"
    r"(?:,\s*(\d+)\s+insertions?\(\+\))?"
    r"(?:,\s*(\d+)\s+deletions?\(-\))?"
)


def parse_shortstat(line: str) -> dict:
    """Return a dict with keys files, insertions, deletions.

    Unrecognised or empty input yields all zeroes.
    """
    m = _SHORTSTAT_RE.fullmatch(line.strip())
    if not m:
        return {"files": 0, "insertions": 0, "deletions": 0}
    return {
        "files": int(m.group(1)),
        "insertions": int(m.group(2) or 0),
        "deletions": int(m.group(3) or 0),
    }
