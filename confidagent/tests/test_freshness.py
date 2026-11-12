"""Tests for verifier/freshness.py - freshness scoring stub."""

from verifier.freshness import freshness_score


def test_freshness_returns_zero():
    # Stub returns 0.0 for any input.
    assert freshness_score("anything") == 0.0
    assert freshness_score("anything", published_at="2020-01-01") == 0.0
