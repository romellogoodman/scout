"""Planted failing tests — sortie #1's objective.

scoutlib.slugify does not exist yet. A scout is dispatched to make these pass.
The harness's crude_slug stays dumb on purpose; this is the real one.
"""

from scoutlib.slugify import slugify


def test_lowercases_and_hyphenates():
    assert slugify("Make The Failing Test Pass") == "make-the-failing-test-pass"


def test_strips_punctuation_to_single_separators():
    assert slugify("fix: retry/backoff (v2)!") == "fix-retry-backoff-v2"


def test_collapses_whitespace_and_trims_junk():
    assert slugify("  --Weird   spacing--  ") == "weird-spacing"


def test_strips_diacritics():
    assert slugify("café ünïcode") == "cafe-unicode"


def test_truncates_at_word_boundary():
    s = slugify("implement the manifest schema and writer for sortie archives",
                max_len=32)
    assert len(s) <= 32
    assert not s.endswith("-")
    assert s == "implement-the-manifest-schema"


def test_empty_or_symbol_only_falls_back():
    assert slugify("") == "sortie"
    assert slugify("!!!") == "sortie"
