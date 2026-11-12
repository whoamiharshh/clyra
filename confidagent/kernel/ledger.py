"""Kernel Ledger - append-only cost/token ledger and budget enforcement.

One JSONL line per LLM call at .confidagent/ledger.jsonl. Also owns the
run-id lifecycle (.confidagent/current_run) and budget checking helpers.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LEDGER_DIR = os.path.join(os.getcwd(), ".confidagent")
LEDGER_FILE = os.path.join(LEDGER_DIR, "ledger.jsonl")
CURRENT_RUN_FILE = os.path.join(LEDGER_DIR, "current_run")


def start_run(app: str = "agent") -> str:
    """Begin a new run: mint a run_id, persist it, create the ledger dir."""
    os.makedirs(LEDGER_DIR, exist_ok=True)
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    with open(CURRENT_RUN_FILE, "w", encoding="utf-8") as f:
        f.write(run_id)
    return run_id


def get_current_run() -> str:
    """Return the current run_id, or 'unknown' if no run was started."""
    try:
        with open(CURRENT_RUN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "unknown"
    except OSError:
        return "unknown"


def record(**fields: Any) -> None:
    """Append one JSONL line to the ledger.

    Safe no-op if .confidagent/ does not exist (e.g. called before start_run).
    Fills in ts/run_id and normalizes known fields.
    """
    if not os.path.isdir(LEDGER_DIR):
        return

    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": fields.get("run_id", get_current_run()),
        "app": fields.get("app", "agent"),
        "stage": fields.get("stage", ""),
        "tier": fields.get("tier", ""),
        "model": fields.get("model", ""),
        "provider": fields.get("provider", ""),
        "prompt_tokens": int(fields.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(fields.get("completion_tokens", 0) or 0),
        "total_tokens": int(fields.get("total_tokens", 0) or 0),
        "cost_usd": float(fields.get("cost_usd", 0.0) or 0.0),
        "cache_hit": bool(fields.get("cache_hit", False)),
        "failover": bool(fields.get("failover", False)),
        "latency_ms": int(fields.get("latency_ms", 0) or 0),
    }
    # Preserve any extra caller-supplied fields beyond the schema.
    for key, value in fields.items():
        if key not in entry:
            entry[key] = value

    try:
        with open(LEDGER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass  # ledger must never break an LLM call


def _read_lines(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def run_total(run_id: str) -> Dict[str, Any]:
    """Aggregate ledger stats for one run."""
    totals = {"tokens": 0, "cost_usd": 0.0, "calls": 0, "cache_hits": 0, "failovers": 0}
    for row in _read_lines(LEDGER_FILE):
        if row.get("run_id") != run_id:
            continue
        totals["calls"] += 1
        totals["tokens"] += int(row.get("total_tokens", 0) or 0)
        totals["cost_usd"] += float(row.get("cost_usd", 0.0) or 0.0)
        if row.get("cache_hit"):
            totals["cache_hits"] += 1
        if row.get("failover"):
            totals["failovers"] += 1
    totals["cost_usd"] = round(totals["cost_usd"], 10)
    return totals


def check_budget(run_id: str, projected_cost: float, limit_usd: float) -> tuple:
    """Return (allowed, reason). Disallowed when spent + projected > limit."""
    spent = run_total(run_id)["cost_usd"]
    total = spent + max(0.0, projected_cost)
    if total > limit_usd:
        return False, (
            f"Budget exceeded: ${spent:.4f} spent + ${projected_cost:.4f} projected "
            f"> ${limit_usd:.4f} limit for run {run_id}"
        )
    return True, (
        f"Budget OK: ${spent:.4f} spent + ${projected_cost:.4f} projected "
        f"<= ${limit_usd:.4f} limit"
    )


def downgrade_tier(requested_tier: str, remaining_usd: float) -> Optional[str]:
    """Return the most capable tier that still fits the remaining budget."""
    if remaining_usd > 0.50:
        return requested_tier
    if remaining_usd > 0.10:
        if requested_tier == "powerful":
            return "cheap"
        return requested_tier
    if remaining_usd > 0.00:
        return "local"
    return None


# Projected per-call cost used for pre-flight budget checks (conservative caps).
PROJECTED_COSTS = {"powerful": 0.002, "cheap": 0.0005, "local": 0.0}
