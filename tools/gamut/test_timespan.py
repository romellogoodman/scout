"""Tests for scoutlib.timespan — gamut build station spec."""

import pytest

from scoutlib.timespan import parse_timespan


def test_single_units():
    assert parse_timespan("45s") == 45
    assert parse_timespan("30m") == 1800
    assert parse_timespan("2h") == 7200


def test_combined_units():
    assert parse_timespan("1h30m") == 5400
    assert parse_timespan("1h30m15s") == 5415


def test_bare_number_is_seconds():
    assert parse_timespan("90") == 90


def test_whitespace_and_case():
    assert parse_timespan(" 1H 30M ") == 5400


def test_rejects_garbage():
    with pytest.raises(ValueError):
        parse_timespan("")
    with pytest.raises(ValueError):
        parse_timespan("1x")
    with pytest.raises(ValueError):
        parse_timespan("h")
