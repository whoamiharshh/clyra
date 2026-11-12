"""Live claim verification via Tavily with deterministic freshness scoring."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from kernel import cache, ledger

try:
    from verifier.claims import Claim
except Exception:  # pragma: no cover
    @dataclass
    class Claim:  # type: ignore[override]
        id: int
        text: str
        category: str = "other"
        time_sensitivity: float = 0.5
        entities: List[str] = field(default_factory=list)
        span: tuple = (0, 0)


@dataclass
class VerificationResult:
    claim_id: int
    status: str  # "CURRENT"|"STALE"|"UNVERIFIABLE"
    freshness: float
    current_value: Optional[str]
    correction: Optional[str]
    sources: List[Dict[str, Any]]
    evidence_quality: float
    checked_at: str
    from_cache: bool


_DEPRECATION_TERMS = ("deprecated", "no longer", "removed", "end of life", "sunset")
_VERSION_RE = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b", re.I)

# Simple per-process Tavily call counter for observability/acceptance demo.
_TAVILY_CALL_COUNT = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_tavily_client():
    from tavily import TavilyClient
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        try:
            from kernel.settings import settings
            api_key = getattr(settings, "tavily_api_key", "")
        except Exception:
            api_key = ""
    return TavilyClient(api_key=api_key) if api_key else TavilyClient()


def _primary_entity(claim: Claim) -> str:
    if claim.entities:
        return claim.entities[0]
    # fallback: first capitalized token or first word
    m = re.search(r"\b[A-Za-z][A-Za-z0-9_.+-]*\b", claim.text)
    return m.group(0) if m else claim.text[:40]


def build_query(claim: Claim) -> str:
    entity = _primary_entity(claim)
    cat = (claim.category or "other").lower()
    if cat == "api_version":
        return f"{entity} latest version changelog release notes"
    if cat == "pricing":
        return f"{entity} current pricing official site"
    if cat == "law":
        return f"{entity} current regulation status official"
    if cat == "leadership":
        return f"{entity} current CEO official announcement"
    if cat == "product_spec":
        return f"{entity} current specifications official documentation"
    return f"{entity} official documentation current"


def _official_domains(claim: Claim) -> List[str]:
    domains: List[str] = []
    hints = {
        "pymongo": ["pymongo.readthedocs.io", "mongodb.com", "pypi.org"],
        "mongodb": ["mongodb.com"],
        "bcrypt": ["pypi.org", "github.com"],
        "python": ["python.org"],
        "stripe": ["stripe.com"],
        "openai": ["openai.com", "platform.openai.com"],
        "flask": ["flask.palletsprojects.com", "pypi.org"],
        "django": ["djangoproject.com"],
        "fastapi": ["fastapi.tiangolo.com"],
        "gdpr": ["gdpr.eu", "europa.eu"],
        "ccpa": ["oag.ca.gov"],
    }
    for ent in claim.entities or []:
        e = re.sub(r"[^a-z0-9.-]", "", ent.lower())
        if not e:
            continue
        domains.append(f"{e}.com")
        domains.append(f"{e}.org")
        domains.append(f"{e}.io")
        domains.append(f"docs.{e}.com")
        for k, vals in hints.items():
            if k in e:
                domains.extend(vals)
    # from claim text tokens too
    text_l = claim.text.lower()
    for k, vals in hints.items():
        if k in text_l:
            domains.extend(vals)
    # de-dup preserve order
    seen = set()
    out = []
    for d in domains:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _domain_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_official(url: str, official_domains: List[str]) -> bool:
    host = _domain_of(url)
    if not host:
        return False
    for d in official_domains:
        d = d.lower()
        if host == d or host.endswith("." + d):
            return True
    return False


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    # loose ISO-ish prefix
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _claim_version_patterns(claim_text: str) -> List[str]:
    # verbatim version-like tokens mentioned in claim
    pats = []
    for m in _VERSION_RE.finditer(claim_text):
        pats.append(m.group(0))
    # common package+version form like "pymongo 3.12.0"
    m2 = re.findall(r"\b([A-Za-z][A-Za-z0-9_.+-]*\s+v?\d+\.\d+(?:\.\d+)?)\b", claim_text)
    for p in m2:
        pats.append(p.strip())
    # unique
    out = []
    seen = set()
    for p in pats:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def _source_text(src: Dict[str, Any]) -> str:
    return " ".join(
        str(src.get(k, "") or "") for k in ("title", "content", "snippet", "raw_content")
    )


def _score_freshness(claim: Claim, sources: List[Dict[str, Any]], official_domains: List[str]):
    base = 0.5
    details: Dict[str, Any] = {"base": base}

    all_text = "\n".join(_source_text(s) for s in sources).lower()
    claim_patterns = _claim_version_patterns(claim.text)
    has_verbatim = False
    for pat in claim_patterns:
        if pat and pat.lower() in all_text:
            has_verbatim = True
            break
    if has_verbatim:
        base += 0.25
    details["verbatim_match"] = has_verbatim

    top_recent = False
    top_official = False
    if sources:
        top = sources[0]
        pub = _parse_date(top.get("published_date") or top.get("published") or top.get("date"))
        if pub and pub >= datetime.now(timezone.utc) - timedelta(days=180):
            top_recent = True
            base += 0.15
        if _is_official(top.get("url", ""), official_domains):
            top_official = True
            base += 0.10
    details["top_recent"] = top_recent
    details["top_official"] = top_official

    contradiction = False
    for s in sources:
        txt = _source_text(s).lower()
        if any(term in txt for term in _DEPRECATION_TERMS):
            contradiction = True
            break
    if contradiction:
        base -= 0.35
    details["contradiction"] = contradiction

    freshness = max(0.0, min(1.0, base))
    return freshness, contradiction, details


def _evidence_quality(sources: List[Dict[str, Any]], official_domains: List[str]) -> float:
    if not sources:
        return 0.0
    n = len(sources)
    off = sum(1 for s in sources if _is_official(s.get("url", ""), official_domains))
    # weight official sources higher: base on coverage + official ratio
    coverage = min(1.0, n / 5.0)
    official_ratio = off / n
    quality = 0.4 * coverage + 0.6 * (0.3 + 0.7 * official_ratio)
    return max(0.0, min(1.0, round(quality, 4)))


def _extract_correction(claim: Claim, sources: List[Dict[str, Any]]) -> Optional[str]:
    top_snippets = []
    for s in sources[:3]:
        snip = (s.get("content") or s.get("snippet") or "")[:500]
        title = s.get("title") or ""
        url = s.get("url") or ""
        if snip or title:
            top_snippets.append(f"- {title} | {url}\n{snip}")
    if not top_snippets:
        return None

    prompt = (
        "Given a claim and web snippets, return ONLY the corrected fact (max 20 words), or the word NONE. "
        "Do not explain.\n\n"
        f"Claim: {claim.text}\n\nSnippets:\n" + "\n\n".join(top_snippets)
    )

    try:
        from kernel.gateway import Gateway
        gw = Gateway()
        resp = gw.complete(
            messages=[{"role": "user", "content": prompt}],
            tier="cheap",
            temperature=0.0,
            max_tokens=60,
        )
        try:
            ledger.record(
                app="verifier",
                stage="claim_correction",
                tier="cheap",
                model=getattr(resp, "model_used", ""),
                provider=getattr(resp, "provider_used", ""),
                prompt_tokens=getattr(resp, "prompt_tokens", 0),
                completion_tokens=getattr(resp, "completion_tokens", 0),
                total_tokens=getattr(resp, "total_tokens", 0),
                cost_usd=getattr(resp, "cost_usd", 0.0),
                cache_hit=getattr(resp, "cache_hit", False),
                failover=getattr(resp, "failover_occurred", False),
                latency_ms=getattr(resp, "latency_ms", 0),
            )
        except Exception:
            pass

        text = (resp.text or "").strip().strip('"').strip("'")
        if not text:
            return None
        if text.upper() == "NONE" or text.upper().startswith("NONE"):
            return None
        # enforce max 20 words
        words = text.split()
        if len(words) > 20:
            text = " ".join(words[:20])
        return text
    except Exception:
        return None


def _tavily_search(query: str) -> List[Dict[str, Any]]:
    global _TAVILY_CALL_COUNT
    client = _get_tavily_client()
    _TAVILY_CALL_COUNT += 1
    print(f"[live_check] tavily_calls={_TAVILY_CALL_COUNT} query={query!r}", file=sys.stderr)
    resp = client.search(query=query, search_depth="advanced", max_results=5, include_raw_content=False)
    results = resp.get("results", []) if isinstance(resp, dict) else []
    sources = []
    for r in results:
        if not isinstance(r, dict):
            continue
        sources.append(
            {
                "url": r.get("url"),
                "title": r.get("title"),
                "snippet": r.get("content") or r.get("snippet"),
                "published_date": r.get("published_date") or r.get("published_time") or r.get("date"),
                "score": r.get("score"),
            }
        )
    return sources


def _cache_key_for_claim(claim: Claim) -> str:
    # stable normalized key; cache layer hashes normalize_task internally
    return (claim.text or "").strip()


def _verify_uncached(claim: Claim) -> VerificationResult:
    checked_at = _now_iso()
    try:
        query = build_query(claim)
        sources = _tavily_search(query)
    except Exception:
        return VerificationResult(
            claim_id=claim.id,
            status="UNVERIFIABLE",
            freshness=0.0,
            current_value=None,
            correction=None,
            sources=[],
            evidence_quality=0.0,
            checked_at=checked_at,
            from_cache=False,
        )

    official_domains = _official_domains(claim)
    # prefer official sources: stable sort so official come first (keeping relative order)
    sources.sort(key=lambda s: (0 if _is_official(s.get("url", ""), official_domains) else 1))

    freshness, contradiction, _details = _score_freshness(claim, sources, official_domains)
    evq = _evidence_quality(sources, official_domains)

    status = "UNVERIFIABLE"
    correction: Optional[str] = None
    current_value: Optional[str] = None

    if freshness >= 0.65:
        status = "CURRENT"
        # best-effort current value extraction
        m = _VERSION_RE.search(" ".join(_source_text(s) for s in sources[:2]))
        current_value = m.group(0) if m else None
    elif freshness <= 0.35 and contradiction:
        status = "STALE"
        correction = _extract_correction(claim, sources)
        if correction is None:
            status = "UNVERIFIABLE"
    else:
        status = "UNVERIFIABLE"

    return VerificationResult(
        claim_id=claim.id,
        status=status,
        freshness=round(float(freshness), 4),
        current_value=current_value,
        correction=correction,
        sources=sources,
        evidence_quality=evq,
        checked_at=checked_at,
        from_cache=False,
    )


def verify(claim: Claim) -> VerificationResult:
    """Verify a claim against live web sources, with cache wrapping."""
    key = _cache_key_for_claim(claim)
    try:
        cached = cache.get_verification(key)
    except Exception:
        cached = None
    if cached:
        # normalize cached payload to current dataclass shape
        cached = dict(cached)
        cached["claim_id"] = claim.id
        cached["from_cache"] = True
        # ensure all fields exist
        cached.setdefault("status", "UNVERIFIABLE")
        cached.setdefault("freshness", 0.0)
        cached.setdefault("current_value", None)
        cached.setdefault("correction", None)
        cached.setdefault("sources", [])
        cached.setdefault("evidence_quality", 0.0)
        cached.setdefault("checked_at", _now_iso())
        return VerificationResult(**cached)

    result = _verify_uncached(claim)
    try:
        payload = asdict(result)
        payload["from_cache"] = False
        cache.put_verification(key, payload)
    except Exception:
        pass
    return result


def verify_claim(claim: str) -> Dict[str, Any]:
    """Compatibility wrapper for legacy callers."""
    c = Claim(id=0, text=claim, category="other", time_sensitivity=0.5, entities=[], span=(0, len(claim)))
    r = verify(c)
    return asdict(r)


def verify_claims(claims: List[Claim], max_workers: int = 5, timeout_s: float = 15.0) -> List[VerificationResult]:
    """Verify up to 5 claims concurrently; per-claim timeout -> UNVERIFIABLE, evidence_quality 0."""
    if not claims:
        return []
    results: List[Optional[VerificationResult]] = [None] * len(claims)
    max_workers = min(max_workers, 5, len(claims))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(verify, c): i for i, c in enumerate(claims)}
        try:
            for fut in as_completed(future_to_idx, timeout=timeout_s):
                idx = future_to_idx[fut]
                c = claims[idx]
                try:
                    results[idx] = fut.result(timeout=0)
                except Exception:
                    results[idx] = VerificationResult(
                        claim_id=c.id, status="UNVERIFIABLE", freshness=0.0,
                        current_value=None, correction=None, sources=[],
                        evidence_quality=0.0, checked_at=_now_iso(), from_cache=False,
                    )
        except TimeoutError:
            pass
    # fill timed-out/missing
    for i, c in enumerate(claims):
        if results[i] is None:
            results[i] = VerificationResult(
                claim_id=c.id, status="UNVERIFIABLE", freshness=0.0,
                current_value=None, correction=None, sources=[],
                evidence_quality=0.0, checked_at=_now_iso(), from_cache=False,
            )
    return [r for r in results if r is not None]


if __name__ == "__main__":
    # Acceptance/demo: run from confidagent dir: python -m verifier.live_check
    demo_claims = [
        Claim(id=1, text="pymongo 3.12.0 is the current version", category="api_version",
              time_sensitivity=0.95, entities=["pymongo"], span=(0, 0)),
        Claim(id=2, text="bcrypt 4.0.1 is current", category="api_version",
              time_sensitivity=0.95, entities=["bcrypt"], span=(0, 0)),
    ]
    for c in demo_claims:
        r = verify(c)
        print(json.dumps({
            "claim_id": r.claim_id, "claim": c.text, "status": r.status,
            "freshness": r.freshness, "evidence_quality": r.evidence_quality,
            "from_cache": r.from_cache, "current_value": r.current_value,
            "correction": r.correction, "sources_count": len(r.sources),
        }, indent=2))
    # second run of first claim to demonstrate cache hit / zero Tavily calls
    print("--- repeat first claim ---")
    r2 = verify(demo_claims[0])
    print(json.dumps({
        "claim_id": r2.claim_id, "claim": demo_claims[0].text, "status": r2.status,
        "freshness": r2.freshness, "from_cache": r2.from_cache,
        "tavily_calls_total": _TAVILY_CALL_COUNT,
    }, indent=2))
