"""Extra tests for verifier/claims.py - coverage boost."""

from verifier.claims import Claim, _compute_time_sensitivity, _regex_classify, is_time_sensitive, select_verifiable


def test_compute_time_sensitivity_pricing():
    score = _compute_time_sensitivity("pricing", "$50 per month")
    assert score >= 0.95


def test_compute_time_sensitivity_other_low():
    score = _compute_time_sensitivity("other", "random text")
    assert score == 0.30


def test_regex_classify_pricing():
    cat, ents = _regex_classify("The price is $10 per month per user.")
    assert cat == "pricing"


def test_regex_classify_api_version():
    cat, ents = _regex_classify("The API version v2.0 is deprecated.")
    assert cat == "api_version"


def test_regex_classify_law():
    cat, ents = _regex_classify("GDPR compliance is required by regulation.")
    assert cat == "law"


def test_regex_classify_leadership():
    cat, ents = _regex_classify("The CEO was appointed in 2024.")
    assert cat == "leadership"


def test_regex_classify_product_spec():
    cat, ents = _regex_classify("The system supports up to 1000 users.")
    assert cat == "product_spec"


def test_regex_classify_other():
    cat, ents = _regex_classify("This is just a random sentence with nothing special.")
    assert cat == "other"


def test_is_time_sensitive_true():
    assert is_time_sensitive("The price is $50 per month.", threshold=0.5) is True


def test_is_time_sensitive_false():
    assert is_time_sensitive("hello world", threshold=0.5) is False


def test_select_verifiable_sorts_and_caps():
    claims = [
        Claim(id=1, text="a", category="pricing", time_sensitivity=0.9),
        Claim(id=2, text="b", category="other", time_sensitivity=0.3),
        Claim(id=3, text="c", category="api_version", time_sensitivity=0.95),
    ]
    sel = select_verifiable(claims, threshold=0.5)
    assert len(sel) == 2
    assert sel[0].time_sensitivity >= sel[1].time_sensitivity
