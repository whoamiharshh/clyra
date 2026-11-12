"""Tests for verifier/claims.py - claim extraction and sensitivity."""

from verifier.claims import Claim, extract_claims, is_time_sensitive, select_verifiable


def test_three_claim_example():
    text = (
        "PyMongo 3.12 supports Python 3.7+. "
        "The free tier includes 1,000 requests per month. "
        "In 2024 the CEO announced GDPR compliance."
    )
    claims = extract_claims(text)
    assert len(claims) == 3
    assert all(isinstance(c, Claim) for c in claims)


def test_pricing_sensitivity_ge_0_95():
    claims = extract_claims("The price is $50 per month per user.")
    pricing = [c for c in claims if c.category == "pricing"]
    assert len(pricing) >= 1
    assert pricing[0].time_sensitivity >= 0.95


def test_select_verifiable_caps_at_12():
    # Generate many claims; select_verifiable should cap at 12.
    text = " ".join(f"Sentence {i} costs $10 per month." for i in range(30))
    claims = extract_claims(text)
    selected = select_verifiable(claims, threshold=0.0)
    assert len(selected) <= 12


def test_empty_answer_returns_empty():
    assert extract_claims("") == []
    assert extract_claims("   ") == []
