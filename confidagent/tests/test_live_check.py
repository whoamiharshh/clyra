"""Tests for verifier/live_check.py - pure helpers, no network."""

from verifier import live_check


def test_deprecation_terms_nonempty():
    assert len(live_check._DEPRECATION_TERMS) > 0
    assert "deprecated" in live_check._DEPRECATION_TERMS


def test_version_re_matches():
    assert live_check._VERSION_RE.search("v2.0") is not None
    assert live_check._VERSION_RE.search("version 1.2.3") is not None
    assert live_check._VERSION_RE.search("no version here") is None


def test_now_iso_returns_string():
    result = live_check._now_iso()
    assert isinstance(result, str)
    assert "T" in result  # ISO format


def test_tavily_call_count_starts_zero():
    assert live_check._TAVILY_CALL_COUNT == 0
