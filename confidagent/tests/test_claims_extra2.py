"""Extra tests for verifier/claims.py - coverage boost."""

from verifier.claims import _split_sentences, _regex_classify, _compute_time_sensitivity


def test_split_sentences_single():
    parts = _split_sentences("The price is $50 per month and it supports Python 3.7+.")
    assert len(parts) == 1


def test_split_sentences_multiple():
    parts = _split_sentences("The price is $50 per month. The API supports version 2.0! The CEO was appointed in 2024?")
    assert len(parts) == 3


def test_split_sentences_empty():
    assert _split_sentences("") == []


def test_regex_classify_deprecation():
    cat, ents = _regex_classify("This API is deprecated and removed.")
    assert cat == "api_version"


def test_compute_time_sensitivity_with_year():
    score = _compute_time_sensitivity("other", "In 2024 something happened.")
    assert score == 0.35  # 0.30 + 0.05


def test_extract_json_array_direct():
    from verifier.claims import _extract_json_array
    assert _extract_json_array('[{"a": 1}]') == [{"a": 1}]
    assert _extract_json_array('{"items": [{"a": 1}]}') == [{"a": 1}]
    assert _extract_json_array('not json') is None
