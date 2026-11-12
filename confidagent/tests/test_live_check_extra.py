"""Tests for verifier/live_check.py - pure helpers, mocked Tavily."""

from datetime import datetime, timezone

from verifier.claims import Claim
from verifier import live_check


def test_primary_entity_from_entities():
    c = Claim(id=1, text="PyMongo 3.12 supports Python 3.7+", category="api_version", time_sensitivity=0.9, entities=["PyMongo", "Python"])
    assert live_check._primary_entity(c) == "PyMongo"


def test_primary_entity_fallback():
    c = Claim(id=1, text="HelloWorld is great", category="other", time_sensitivity=0.3, entities=[])
    assert live_check._primary_entity(c) == "HelloWorld"


def test_build_query_api_version():
    c = Claim(id=1, text="x", category="api_version", time_sensitivity=0.9, entities=["PyMongo"])
    assert live_check.build_query(c) == "PyMongo latest version changelog release notes"


def test_build_query_pricing():
    c = Claim(id=1, text="x", category="pricing", time_sensitivity=0.95, entities=["Stripe"])
    assert live_check.build_query(c) == "Stripe current pricing official site"


def test_build_query_law():
    c = Claim(id=1, text="x", category="law", time_sensitivity=0.75, entities=["GDPR"])
    assert live_check.build_query(c) == "GDPR current regulation status official"


def test_build_query_leadership():
    c = Claim(id=1, text="x", category="leadership", time_sensitivity=0.85, entities=["CEO"])
    assert live_check.build_query(c) == "CEO current CEO official announcement"


def test_build_query_product_spec():
    c = Claim(id=1, text="x", category="product_spec", time_sensitivity=0.7, entities=["FastAPI"])
    assert live_check.build_query(c) == "FastAPI current specifications official documentation"


def test_build_query_other():
    c = Claim(id=1, text="x", category="other", time_sensitivity=0.3, entities=["Foo"])
    assert live_check.build_query(c) == "Foo official documentation current"


def test_official_domains_pymongo():
    c = Claim(id=1, text="PyMongo", category="other", time_sensitivity=0.5, entities=["PyMongo"])
    domains = live_check._official_domains(c)
    assert "pymongo.readthedocs.io" in domains
    assert "mongodb.com" in domains


def test_domain_of():
    assert live_check._domain_of("https://pymongo.readthedocs.io/en/stable/") == "pymongo.readthedocs.io"
    assert live_check._domain_of("not a url") == ""


def test_is_official_true():
    assert live_check._is_official("https://pymongo.readthedocs.io/", ["pymongo.readthedocs.io"]) is True
    assert live_check._is_official("https://docs.pymongo.readthedocs.io/", ["pymongo.readthedocs.io"]) is True


def test_is_official_false():
    assert live_check._is_official("https://evil.com/", ["pymongo.readthedocs.io"]) is False
    assert live_check._is_official("", ["pymongo.readthedocs.io"]) is False


def test_parse_date_datetime():
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert live_check._parse_date(dt) == dt


def test_parse_date_none():
    assert live_check._parse_date(None) is None
    assert live_check._parse_date("") is None


def test_parse_date_iso_string():
    result = live_check._parse_date("2024-01-15T10:30:00Z")
    assert isinstance(result, datetime)
    assert result.year == 2024


def test_is_official_subdomain():
    assert live_check._is_official("https://docs.pymongo.readthedocs.io/", ["pymongo.readthedocs.io"]) is True


def test_is_official_empty_host():
    assert live_check._is_official("", ["example.com"]) is False


def test_verification_result_creation():
    vr = live_check.VerificationResult(
        claim_id=1,
        status="CURRENT",
        freshness=0.95,
        current_value=None,
        correction=None,
        sources=[],
        evidence_quality=1.0,
        checked_at="2024-01-01",
        from_cache=False,
    )
    assert vr.claim_id == 1
    assert vr.status == "CURRENT"


def test_parse_date_timestamp():
    result = live_check._parse_date(1705305600)
    assert isinstance(result, datetime)


def test_parse_date_iso_with_tz():
    result = live_check._parse_date("2024-01-15T10:30:00+05:00")
    assert isinstance(result, datetime)


def test_parse_date_loose_iso():
    result = live_check._parse_date("2024-01-15 some text")
    assert isinstance(result, datetime)


def test_claim_version_patterns():
    c = Claim(id=1, text="PyMongo 3.12.0 supports Python 3.7+", category="api_version", time_sensitivity=0.9, entities=[])
    pats = live_check._claim_version_patterns(c.text)
    assert "3.12.0" in pats
    assert "3.7" in pats


def test_source_text():
    src = {"title": "Hello", "content": "World", "snippet": "", "raw_content": None}
    result = live_check._source_text(src)
    assert "Hello" in result
    assert "World" in result


def test_score_freshness_no_sources():
    c = Claim(id=1, text="PyMongo 3.12.0", category="api_version", time_sensitivity=0.9, entities=[])
    freshness, contradiction, details = live_check._score_freshness(c, [], [])
    assert freshness == 0.5
    assert contradiction is False


def test_score_freshness_with_deprecation():
    c = Claim(id=1, text="PyMongo 3.12.0", category="api_version", time_sensitivity=0.9, entities=[])
    sources = [{"title": "x", "content": "This API is deprecated", "snippet": "", "raw_content": ""}]
    freshness, contradiction, details = live_check._score_freshness(c, sources, [])
    assert contradiction is True
    assert freshness < 0.5


def test_evidence_quality_no_sources():
    assert live_check._evidence_quality([], []) == 0.0

