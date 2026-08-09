"""Tests for scoutlib.diffstats — parse `git diff --shortstat` output."""

from scoutlib.diffstats import parse_shortstat


def test_full_line():
    line = " 3 files changed, 41 insertions(+), 7 deletions(-)"
    assert parse_shortstat(line) == {"files": 3, "insertions": 41, "deletions": 7}


def test_singular_forms():
    line = " 1 file changed, 1 insertion(+), 1 deletion(-)"
    assert parse_shortstat(line) == {"files": 1, "insertions": 1, "deletions": 1}


def test_insertions_only():
    line = " 2 files changed, 15 insertions(+)"
    assert parse_shortstat(line) == {"files": 2, "insertions": 15, "deletions": 0}


def test_deletions_only():
    line = " 1 file changed, 9 deletions(-)"
    assert parse_shortstat(line) == {"files": 1, "insertions": 0, "deletions": 9}


def test_empty_input():
    assert parse_shortstat("") == {"files": 0, "insertions": 0, "deletions": 0}


def test_whitespace_and_trailing_newline():
    line = " 5 files changed, 100 insertions(+), 20 deletions(-)\n"
    assert parse_shortstat(line) == {"files": 5, "insertions": 100, "deletions": 20}


def test_garbage_input_is_all_zeroes():
    assert parse_shortstat("not a shortstat line") == {
        "files": 0, "insertions": 0, "deletions": 0}
