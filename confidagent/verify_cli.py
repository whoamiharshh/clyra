#!/usr/bin/env python3
"""Stale-Answer Detector CLI (PS06)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.status import Status

import kernel.ledger as ledger
from verifier.claims import extract_claims, select_verifiable, print_claims_table
from verifier.live_check import verify, verify_claims, VerificationResult

DEMO_ANSWER = (
    "PyMongo 3.12.0 is the current stable version for production use. "
    "Flask 1.1 is the latest stable release recommended for new web applications. "
    "The free tier includes 1,000 requests per month for standard API access. "
    "In 2024 the CEO announced GDPR compliance for all European customers."
)


def _result_to_dict(r: Any) -> Dict[str, Any]:
    if is_dataclass(r):
        return asdict(r)
    if isinstance(r, dict):
        return r
    return {
        "claim_id": getattr(r, "claim_id", None),
        "status": getattr(r, "status", "UNVERIFIABLE"),
        "freshness": getattr(r, "freshness", 0.0),
        "current_value": getattr(r, "current_value", None),
        "correction": getattr(r, "correction", None),
        "sources": getattr(r, "sources", []),
        "evidence_quality": getattr(r, "evidence_quality", 0.0),
        "checked_at": getattr(r, "checked_at", ""),
        "from_cache": getattr(r, "from_cache", False),
    }


def _print_result_line(console: Console, claim_text: str, rd: Dict[str, Any]) -> None:
    status = str(rd.get("status", "UNVERIFIABLE")).upper()
    freshness = float(rd.get("freshness", 0.0) or 0.0)
    correction = rd.get("correction")
    sources = rd.get("sources") or []
    source_url = ""
    if sources and isinstance(sources[0], dict):
        source_url = sources[0].get("url") or ""

    if status == "CURRENT":
        line = f"[green]✓ CURRENT ({freshness:.2f})[/green] — {claim_text}"
        if source_url:
            line += f" — source: {source_url}"
        console.print(line)
    elif status == "STALE":
        line = f"[red]✗ STALE   ({freshness:.2f})[/red] — {claim_text}"
        if correction:
            line += f' — correction: "{correction}"'
        console.print(line)
    else:
        console.print(f"[yellow]? UNVERIFIABLE[/yellow]    — {claim_text}")


def _weighted_freshness(claims, results: List[Dict[str, Any]]) -> float:
    # weight by time_sensitivity of the verifiable claim matched by claim_id
    sens_by_id = {c.id: float(getattr(c, "time_sensitivity", 1.0) or 1.0) for c in claims}
    num = 0.0
    den = 0.0
    for rd in results:
        cid = rd.get("claim_id")
        w = sens_by_id.get(cid, 1.0)
        f = float(rd.get("freshness", 0.0) or 0.0)
        num += w * f
        den += w
    return (num / den) if den > 0 else 0.0


def run(answer: str, as_json: bool = False) -> int:
    console = Console()

    if not as_json:
        console.print("STALE-ANSWER DETECTOR — PS06")

    claims = extract_claims(answer)
    verifiable = select_verifiable(claims)

    if not as_json:
        print_claims_table(claims)

    # Start a ledger run so we can report Bifrost calls/cost for corrections.
    prev_run = ledger.get_current_run()
    run_id = ledger.start_run("verify_cli")

    tavily_before = getattr(sys.modules.get("verifier.live_check"), "_TAVILY_CALL_COUNT", 0)

    try:
        if as_json:
            results_obj = verify_claims(verifiable)
        else:
            with console.status("[bold cyan]Verifying claims...", spinner="dots"):
                results_obj = verify_claims(verifiable)
    finally:
        tavily_after = getattr(sys.modules.get("verifier.live_check"), "_TAVILY_CALL_COUNT", tavily_before)

    results = [_result_to_dict(r) for r in results_obj]
    # attach claim text for convenience in output
    claim_text_by_id = {c.id: c.text for c in verifiable}
    for rd in results:
        rd["claim_text"] = claim_text_by_id.get(rd.get("claim_id"), "")

    run_totals = ledger.run_total(run_id)
    bifrost_calls = int(run_totals.get("calls", 0) or 0)
    cost = float(run_totals.get("cost_usd", 0.0) or 0.0)

    verified_current = sum(1 for r in results if r.get("status") == "CURRENT")
    stale = sum(1 for r in results if r.get("status") == "STALE")
    unverifiable = sum(1 for r in results if r.get("status") == "UNVERIFIABLE")
    cache_hits = sum(1 for r in results if r.get("from_cache"))
    tavily_calls = max(0, int(tavily_after) - int(tavily_before))
    overall = _weighted_freshness(verifiable, results)

    summary = {
        "claims_analyzed": len(verifiable),
        "verified_current": verified_current,
        "stale": stale,
        "unverifiable": unverifiable,
        "overall_answer_freshness": round(overall, 4),
        "tavily_calls": tavily_calls,
        "cache_hits": cache_hits,
        "bifrost_calls": bifrost_calls,
        "cost_usd": round(cost, 6),
        "run_id": run_id,
        "previous_run_id": prev_run,
    }

    if as_json:
        out = {"results": results, "summary": summary, "claims": [asdict(c) for c in claims]}
        print(json.dumps(out, ensure_ascii=False))
        return 0

    for rd in results:
        _print_result_line(console, rd.get("claim_text", ""), rd)

    panel_text = (
        f"Claims analyzed: {summary['claims_analyzed']}\n"
        f"Verified current: {summary['verified_current']}\n"
        f"Stale: {summary['stale']}\n"
        f"Unverifiable: {summary['unverifiable']}\n"
        f"Overall answer freshness: {summary['overall_answer_freshness']:.4f}\n"
        f"Tavily calls: {summary['tavily_calls']} | Cache hits: {summary['cache_hits']} | "
        f"Bifrost calls: {summary['bifrost_calls']} | Cost: ${summary['cost_usd']:.4f}"
    )
    console.print(Panel(panel_text, title="Summary", border_style="blue"))
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="STALE-ANSWER DETECTOR — PS06")
    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--answer", type=str, help="Answer text to verify")
    src.add_argument("--file", type=str, help="Path to file containing answer text")
    src.add_argument("--demo", action="store_true", help="Run with built-in demo answer")
    parser.add_argument("--json", action="store_true", help="Emit JSON only to stdout")
    args = parser.parse_args(argv)

    if args.demo:
        answer = DEMO_ANSWER
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            answer = f.read()
    elif args.answer is not None:
        answer = args.answer
    else:
        parser.error("one of --answer, --file, or --demo is required")

    return run(answer, as_json=bool(args.json))


if __name__ == "__main__":
    sys.exit(main())
