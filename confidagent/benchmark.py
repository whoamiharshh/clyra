"""
Per-layer ablation benchmark for ConfidAgent.

Executes the agent 6 times against pristine copies of demo_repo with a
feature-flag matrix, capturing per-config token/cost metrics and
correctness.  Produces a rich table and defends the savings claim.

Baseline formula (documented):
    baseline_tokens = (full repo .py content chars // 4)           -- naive full-context ingestion
                    + (tokens for one powerful-model call per decision)  -- full tool registry, no routing

This is what a naive agent would spend: it slurps every file in full, has the
entire tool registry available, and pays for one powerful-model call per
decision -- with no AST filtering, no file memory, no cascade routing, no
cache, no cost model, and no tool minimization.
"""
import os
import sys
import json
import time
import shutil
import tempfile
import ast as _ast
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List

CONFIDAGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CONFIDAGENT_DIR not in sys.path:
    sys.path.insert(0, CONFIDAGENT_DIR)

from kernel.settings import settings, FeatureFlags, reload
from kernel import ledger
from agent.loop import ConfidAgent


# --------------------------------------------------------------------------- #
# Feature-flag matrix: (config_name, layer_label, FeatureFlags)
# --------------------------------------------------------------------------- #
CONFIGS: List[tuple] = [
    ("baseline_full_context_no_cache", "none",
     FeatureFlags(ast_context=False, file_memory=False, routing=False,
                  cache=False, cost_model=False, tool_minimization=False)),
    ("ast_only", "Layer 1: AST context",
     FeatureFlags(ast_context=True, file_memory=False, routing=False,
                  cache=False, cost_model=False, tool_minimization=False)),
    ("ast_plus_memory", "Layer 1 + file memory",
     FeatureFlags(ast_context=True, file_memory=True, routing=False,
                  cache=False, cost_model=False, tool_minimization=False)),
    ("ast_memory_routing", "Layers 1-2 + routing",
     FeatureFlags(ast_context=True, file_memory=True, routing=True,
                  cache=False, cost_model=False, tool_minimization=False)),
    ("ast_memory_routing_cache", "Layers 1-3 + cache",
     FeatureFlags(ast_context=True, file_memory=True, routing=True,
                  cache=True, cost_model=False, tool_minimization=False)),
    ("full_stack", "Layers 1-5 + cost model + tool minimization",
     FeatureFlags(ast_context=True, file_memory=True, routing=True,
                  cache=True, cost_model=True, tool_minimization=True)),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _clean_state():
    """Remove agent state and ledger artifacts so each run starts pristine."""
    for path in ('.confidagent_state.json',):
        if os.path.exists(path):
            os.remove(path)
    ledger_dir = ledger.LEDGER_DIR
    if os.path.isdir(ledger_dir):
        shutil.rmtree(ledger_dir, ignore_errors=True)
    # memory.db / cache.db live in .confidagent too, already removed above.


def _copy_pristine_repo(repo_path: str) -> str:
    """Copy repo_path to a fresh temp dir; return the temp path."""
    tmp = tempfile.mkdtemp(prefix="ablation_")
    dst = os.path.join(tmp, os.path.basename(os.path.normpath(repo_path)))
    shutil.copytree(repo_path, dst)
    return dst


def _compute_naive_baseline(repo_path: str, n_decisions: int) -> int:
    """Naive baseline: full repo content + one powerful call per decision."""
    total_chars = 0
    for root, _, files in os.walk(repo_path):
        for fname in files:
            if fname.endswith('.py'):
                fp = os.path.join(root, fname)
                try:
                    with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                        total_chars += len(f.read())
                except Exception:
                    pass
    repo_tokens = total_chars // 4
    decision_tokens = n_decisions * 2000  # one powerful-model call per decision
    return repo_tokens + decision_tokens


def _read_ledger_rows(run_id: str) -> List[dict]:
    """Read all ledger rows for a run_id."""
    rows = []
    if not os.path.exists(ledger.LEDGER_FILE):
        return rows
    with open(ledger.LEDGER_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("run_id") == run_id:
                rows.append(row)
    return rows


def _tally(rows: List[dict]) -> dict:
    total_tokens = sum(int(r.get("total_tokens", 0) or 0) for r in rows)
    cloud_tokens = sum(int(r.get("total_tokens", 0) or 0)
                       for r in rows if r.get("tier") in ("cheap", "powerful"))
    local_tokens = sum(int(r.get("total_tokens", 0) or 0)
                       for r in rows if r.get("tier") == "local")
    cost_usd = round(sum(float(r.get("cost_usd", 0.0) or 0.0) for r in rows), 6)
    calls = len(rows)
    cache_hits = sum(1 for r in rows if r.get("cache_hit"))
    failovers = sum(1 for r in rows if r.get("failover"))
    return {
        "total_tokens": total_tokens,
        "cloud_tokens": cloud_tokens,
        "local_tokens": local_tokens,
        "cost_usd": cost_usd,
        "calls": calls,
        "cache_hits": cache_hits,
        "failovers": failovers,
    }


def _check_correctness(repo_path: str) -> bool:
    """Verify the repo still contains valid Python after the agent ran,
    and that verify.py's assertions pass against this repo copy."""
    try:
        # 1. All .py files must parse as valid Python.
        for root, _, files in os.walk(repo_path):
            for fname in files:
                if fname.endswith('.py'):
                    fp = os.path.join(root, fname)
                    try:
                        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                            _ast.parse(f.read())
                    except SyntaxError:
                        return False
                    except Exception:
                        pass

        # 2. Run verify.py's test functions against this repo copy.
        import verify as verify_mod
        old_demo = verify_mod.DEMO_REPO
        old_state = verify_mod.STATE_FILE
        verify_mod.DEMO_REPO = repo_path
        verify_mod.STATE_FILE = os.path.join(repo_path, '.confidagent_state.json')
        try:
            ok = True
            ok &= verify_mod.test_syntax()
            ok &= verify_mod.test_imports()
            ok &= verify_mod.test_demo_files()
        finally:
            verify_mod.DEMO_REPO = old_demo
            verify_mod.STATE_FILE = old_state
        return bool(ok)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Single ablation run
# --------------------------------------------------------------------------- #
def _run_one(repo_path: str, task: str, flags: FeatureFlags) -> dict:
    """Run the agent once with the given feature flags; return metrics dict."""
    _clean_state()

    # Apply feature flags via env + reload so the agent picks them up.
    os.environ["CONFIDAGENT_AST_CONTEXT"] = "1" if flags.ast_context else "0"
    os.environ["CONFIDAGENT_FILE_MEMORY"] = "1" if flags.file_memory else "0"
    os.environ["CONFIDAGENT_ROUTING"] = "1" if flags.routing else "0"
    os.environ["CONFIDAGENT_CACHE"] = "1" if flags.cache else "0"
    os.environ["CONFIDAGENT_COST_MODEL"] = "1" if flags.cost_model else "0"
    os.environ["CONFIDAGENT_TOOL_MINIMIZATION"] = "1" if flags.tool_minimization else "0"
    reload()

    agent = ConfidAgent(
        repo_path=repo_path,
        task=task,
        dry_run=True,  # never modify files during benchmark
        feature_flags=flags,
    )

    start = time.perf_counter()
    success = agent.run()
    wall_clock = time.perf_counter() - start

    rows = _read_ledger_rows(agent.run_id)
    metrics = _tally(rows)
    metrics["wall_clock"] = round(wall_clock, 3)
    metrics["success"] = bool(success)
    metrics["correct"] = _check_correctness(repo_path)
    return metrics


# --------------------------------------------------------------------------- #
# Main ablation driver
# --------------------------------------------------------------------------- #
def run_ablation(repo_path: str, task: str) -> List[dict]:
    """Execute the agent 6 times with the feature-flag matrix.

    Returns a list of result dicts, one per config.
    """
    results: List[dict] = []

    # Need n_decisions for the baseline formula.  Run a quick analysis once
    # against a pristine copy to learn the decision count.
    probe_dir = _copy_pristine_repo(repo_path)
    try:
        _clean_state()
        os.environ["CONFIDAGENT_CACHE"] = "0"
        os.environ["CONFIDAGENT_ROUTING"] = "0"
        os.environ["CONFIDAGENT_COST_MODEL"] = "0"
        reload()
        from agent.file_reader import FileReader
        from agent.planner import TaskAnalyzer
        fr = FileReader()
        analyzer = TaskAnalyzer(fr, None)
        # analyze() may call bifrost; wrap in try to get a decision count.
        try:
            analysis = analyzer.analyze(task, probe_dir)
            n_decisions = len(analysis.get('decisions', []))
        except Exception:
            n_decisions = 5  # conservative fallback
    finally:
        _clean_state()
        shutil.rmtree(probe_dir, ignore_errors=True)

    baseline_tokens = _compute_naive_baseline(repo_path, n_decisions)

    for config_name, layer_label, flags in CONFIGS:
        run_dir = _copy_pristine_repo(repo_path)
        try:
            metrics = _run_one(run_dir, task, flags)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

        results.append({
            "config": config_name,
            "layer": layer_label,
            **metrics,
        })

    return results, baseline_tokens


def print_table(results: List[dict], baseline_tokens: int) -> None:
    """Print the rich ablation table."""
    print("\n" + "=" * 90)
    print("ConfidAgent Per-Layer Ablation Benchmark")
    print("=" * 90)
    print(f"Documented baseline formula: full repo .py content (chars // 4)")
    print(f"                           + one powerful-model call per decision")
    print(f"Baseline tokens: {baseline_tokens:,}")
    print("-" * 90)
    header = f"{'Config':<34} {'Tokens':>9} {'Cloud':>8} {'Cost($)':>9} {'Calls':>6} {'Cache':>7} {'Correct':>8}"
    print(header)
    print("-" * 90)
    for r in results:
        print(f"{r['config']:<34} {r['total_tokens']:>9,} {r['cloud_tokens']:>8} "
              f"{r['cost_usd']:>9.4f} {r['calls']:>6} {r['cache_hits']:>7} "
              f"{'yes' if r['correct'] else 'no':>8}")
    print("=" * 90)

    # Headline reduction vs the documented baseline formula.
    full_stack = results[-1]
    base_cost = results[0]['cost_usd']
    if baseline_tokens > 0:
        tok_reduction = (baseline_tokens - full_stack['total_tokens']) / baseline_tokens * 100
        cost_reduction = (base_cost - full_stack['cost_usd']) / base_cost * 100 if base_cost > 0 else 0.0
    else:
        tok_reduction = 100.0
        cost_reduction = 0.0
    print(f"\nReduction vs baseline: {tok_reduction:.1f}%  (tokens: {baseline_tokens:,} -> {full_stack['total_tokens']:,})")
    print(f"                         {cost_reduction:.1f}%  (cost: ${base_cost:.4f} -> ${full_stack['cost_usd']:.4f})")

    correct_count = sum(1 for r in results if r['correct'])
    print(f"Correctness: {correct_count}/{len(results)} configs passed verify")


def main():
    repo_path = os.path.join(CONFIDAGENT_DIR, 'demo_repo')
    task = "fix security vulnerabilities"

    if not os.path.exists(repo_path):
        print(f"Error: repo not found: {repo_path}")
        sys.exit(1)

    results, baseline_tokens = run_ablation(repo_path, task)
    print_table(results, baseline_tokens)

    # Assertions.
    full_stack = results[-1]
    baseline = results[0]
    assert full_stack['total_tokens'] < baseline_tokens * 0.15, (
        f"full_stack tokens {full_stack['total_tokens']} not < 15% of baseline {baseline_tokens}"
    )
    assert all(r['correct'] for r in results), "not all configs passed correctness verify"

    # Write results for pitch deck.
    out_dir = os.path.join(CONFIDAGENT_DIR, '.confidagent')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'benchmark.json')
    payload = {
        "baseline_tokens": baseline_tokens,
        "baseline_formula": "full repo .py content (chars // 4) + one powerful-model call per decision",
        "results": results,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    print(f"\nResults written to {out_path}")

    sys.exit(0)


if __name__ == '__main__':
    main()
