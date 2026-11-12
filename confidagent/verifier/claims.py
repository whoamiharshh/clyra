"""Claim extraction and time-sensitivity classification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Tuple

from rich.console import Console
from rich.table import Table


@dataclass
class Claim:
    id: int
    text: str
    category: str
    time_sensitivity: float
    entities: List[str] = field(default_factory=list)
    span: Tuple[int, int] = (0, 0)


_BASE_SCORES = {
    "pricing": 0.95,
    "api_version": 0.90,
    "leadership": 0.85,
    "law": 0.75,
    "product_spec": 0.70,
    "other": 0.30,
}

_CATEGORIES = {"pricing", "api_version", "law", "leadership", "product_spec", "other"}

_REGEX_FALLBACK = [
    ("pricing", re.compile(r"\$\d|per month|per user|free tier|pricing", re.I)),
    ("api_version", re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b|\bversion\b|\bdeprecat|\bAPI\b")),
    ("law", re.compile(r"\bGDPR\b|\bCCPA\b|\bregulation|\bcompliance|\bAct\b")),
    ("leadership", re.compile(r"\bCEO\b|\bCTO\b|\bfounder\b|\bappointed\b|\bstepped down\b", re.I)),
    ("product_spec", re.compile(r"\bsupports\b|\bmaximum\b|\blimit\b|\bup to\b", re.I)),
]

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|do|does|did|"
    r"will|can|could|should|would|may|might|must|supports?|includes?|"
    r"announced?|released?|provides?|offers?|allows?|enables?|requires?|"
    r"limits?|costs?|charges?|deprecated?|appointed|stepped)\b",
    re.I,
)
_YEAR_OR_VERSION_RE = re.compile(r"\b(?:19|20)\d{2}\b|\bv?\d+\.\d+(?:\.\d+)?\b")


def _split_sentences(text: str) -> List[Tuple[str, Tuple[int, int]]]:
    parts: List[Tuple[str, Tuple[int, int]]] = []
    pos = 0
    raw_parts = _SENT_SPLIT_RE.split(text.strip())
    # If no sentence punctuation splits, try line breaks; else treat as single sentence.
    if len(raw_parts) == 1 and raw_parts[0] == text.strip():
        lines = [ln for ln in re.split(r"[\r\n]+", text.strip()) if ln.strip()]
        raw_parts = lines if len(lines) > 1 else raw_parts
    for raw in raw_parts:
        if not raw:
            continue
        start = text.find(raw, pos)
        if start == -1:
            start = pos
        end = start + len(raw)
        pos = end
        s = raw.strip()
        tokens = re.findall(r"\w[\w.+-]*", s)
        if len(tokens) < 6 and not _YEAR_OR_VERSION_RE.search(s):
            continue
        if not _VERB_RE.search(s):
            continue
        parts.append((s, (start, end)))
    return parts


def _compute_time_sensitivity(category: str, text: str) -> float:
    score = _BASE_SCORES.get(category, _BASE_SCORES["other"])
    if _YEAR_OR_VERSION_RE.search(text):
        score += 0.05
    return min(1.0, score)


def _regex_classify(sentence: str) -> Tuple[str, List[str]]:
    matches = [cat for cat, pat in _REGEX_FALLBACK if pat.search(sentence)]
    if not matches:
        category = "other"
    elif "law" in matches and ("compliance" in sentence.lower() or "gdpr" in sentence or "ccpa" in sentence or "regulation" in sentence.lower()):
        category = "law"
    elif "pricing" in matches:
        category = "pricing"
    elif "api_version" in matches:
        category = "api_version"
    elif "leadership" in matches:
        category = "leadership"
    elif "law" in matches:
        category = "law"
    elif "product_spec" in matches:
        category = "product_spec"
    else:
        category = "other"

    entities = re.findall(r"\b[A-Z][A-Za-z0-9.+-]*(?:\s+\d+(?:\.\d+)*)?\b", sentence)
    seen = set()
    uniq: List[str] = []
    for e in entities:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return category, uniq[:8]


def _extract_json_array(text: str):
    text = text.strip()
    # try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            return data["items"]
    except Exception:
        pass
    # try fenced/embedded array
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            return None
    return None


def _classify_with_local(sentences: List[str]) -> List[dict]:
    try:
        from kernel.gateway import Gateway, LocalModelUnavailable, GatewayUnavailable
        gw = Gateway()
        if not gw.is_local_available():
            return []
    except Exception:
        return []

    results: List[dict] = []
    prompt_tpl = (
        'Classify each sentence as a verifiable claim. Return JSON array, one object per sentence in order: '
        '{"is_claim":bool,"category":"pricing|api_version|law|leadership|product_spec|other","entities":[str],"why_time_sensitive":str}. '
        "Sentences:\n"
    )
    for i in range(0, len(sentences), 20):
        batch = sentences[i:i + 20]
        body = "\n".join(f"{idx+1}. {s}" for idx, s in enumerate(batch))
        prompt = prompt_tpl + body
        try:
            resp = gw.complete(
                messages=[{"role": "user", "content": prompt}],
                tier="local",
                temperature=0.0,
                max_tokens=1200,
            )
            arr = _extract_json_array(resp.text)
            if not arr or len(arr) != len(batch):
                return []
            for item in arr:
                if not isinstance(item, dict):
                    return []
                results.append(item)
        except Exception:
            return []
    return results


def extract_claims(answer: str) -> List[Claim]:
    """Extract and classify verifiable claims from an answer."""
    sentences = _split_sentences(answer)
    if not sentences:
        return []

    texts = [s for s, _ in sentences]
    model_items = _classify_with_local(texts)

    claims: List[Claim] = []
    claim_id = 1
    for idx, (text, span) in enumerate(sentences):
        if model_items:
            item = model_items[idx]
            if not item.get("is_claim", False):
                continue
            category = str(item.get("category", "other"))
            if category not in _CATEGORIES:
                category = "other"
            entities = item.get("entities") or []
            if not isinstance(entities, list):
                entities = []
            entities = [str(e) for e in entities]
        else:
            category, entities = _regex_classify(text)

        claims.append(
            Claim(
                id=claim_id,
                text=text,
                category=category,
                time_sensitivity=_compute_time_sensitivity(category, text),
                entities=entities,
                span=span,
            )
        )
        claim_id += 1
    return claims


def is_time_sensitive(claim: str, threshold: float = 0.5) -> bool:
    """Compatibility helper: classify a single claim string."""
    claims = extract_claims(claim)
    if not claims:
        return False
    return claims[0].time_sensitivity >= threshold


def select_verifiable(claims: List[Claim], threshold: float = 0.5) -> List[Claim]:
    """Return claims above threshold, sorted desc by sensitivity, capped at 12."""
    selected = [c for c in claims if c.time_sensitivity >= threshold]
    selected.sort(key=lambda c: c.time_sensitivity, reverse=True)
    return selected[:12]


def print_claims_table(claims: List[Claim]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("id", justify="right")
    table.add_column("category")
    table.add_column("sensitivity", justify="right")
    table.add_column("text")
    for c in claims:
        text = c.text if len(c.text) <= 80 else c.text[:77] + "..."
        table.add_row(str(c.id), c.category, f"{c.time_sensitivity:.2f}", text)
    Console().print(table)


if __name__ == "__main__":
    demo = (
        "PyMongo 3.12 supports Python 3.7+. "
        "The free tier includes 1,000 requests per month. "
        "In 2024 the CEO announced GDPR compliance."
    )
    claims = extract_claims(demo)
    print_claims_table(claims)
