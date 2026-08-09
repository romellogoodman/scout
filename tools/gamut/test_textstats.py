"""Tests for scoutlib.textstats — gamut debt station."""

from scoutlib.textstats import preview, safe_ratio, word_count


def test_word_count():
    assert word_count("one two  three\nfour") == 4


def test_preview_collapses_and_truncates():
    assert preview("a  b   c") == "a b c"
    long_text = "word " * 30
    assert len(preview(long_text)) <= 60


def test_safe_ratio_swallows_division_by_zero():
    assert safe_ratio(1, 0) == 0.0
    assert safe_ratio(6, 3) == 2.0
