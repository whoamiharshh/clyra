"""Tests for kernel/ledger.py - append-only cost/token ledger."""

import json
import os
import tempfile

import pytest

import kernel.ledger as ledger


def _fresh_dir(tmp_path, monkeypatch):
    ledger.LEDGER_DIR = str(tmp_path)
    ledger.LEDGER_FILE = os.path.join(str(tmp_path), "ledger.jsonl")
    ledger.CURRENT_RUN_FILE = os.path.join(str(tmp_path), "current_run")


def test_record_appends_valid_json(tmp_path, monkeypatch):
    _fresh_dir(tmp_path, monkeypatch)
    os.makedirs(ledger.LEDGER_DIR, exist_ok=True)
    ledger.record(run_id="run1", stage="completion", tier="cheap", total_tokens=100, cost_usd=0.001)
    with open(ledger.LEDGER_FILE, "r") as f:
        line = f.readline().strip()
    entry = json.loads(line)
    assert entry["run_id"] == "run1"
    assert entry["tier"] == "cheap"
    assert entry["total_tokens"] == 100
    assert entry["cost_usd"] == 0.001


def test_run_total_sums(tmp_path, monkeypatch):
    _fresh_dir(tmp_path, monkeypatch)
    os.makedirs(ledger.LEDGER_DIR, exist_ok=True)
    ledger.record(run_id="run1", stage="c", tier="cheap", total_tokens=100, cost_usd=0.001, cache_hit=True)
    ledger.record(run_id="run1", stage="c", tier="cheap", total_tokens=200, cost_usd=0.002, failover=True)
    ledger.record(run_id="run2", stage="c", tier="cheap", total_tokens=999, cost_usd=9.99)
    totals = ledger.run_total("run1")
    assert totals["calls"] == 2
    assert totals["tokens"] == 300
    assert totals["cost_usd"] == 0.003
    assert totals["cache_hits"] == 1
    assert totals["failovers"] == 1


def test_check_budget_blocks(tmp_path, monkeypatch):
    _fresh_dir(tmp_path, monkeypatch)
    os.makedirs(ledger.LEDGER_DIR, exist_ok=True)
    ledger.record(run_id="run1", stage="c", tier="cheap", total_tokens=0, cost_usd=1.50)
    allowed, reason = ledger.check_budget("run1", projected_cost=1.00, limit_usd=2.00)
    assert allowed is False
    assert "Budget exceeded" in reason


def test_downgrade_tier_ladder(tmp_path, monkeypatch):
    _fresh_dir(tmp_path, monkeypatch)
    assert ledger.downgrade_tier("powerful", 1.00) == "powerful"
    assert ledger.downgrade_tier("powerful", 0.30) == "cheap"
    assert ledger.downgrade_tier("powerful", 0.05) == "local"
    assert ledger.downgrade_tier("cheap", 0.05) == "local"
    assert ledger.downgrade_tier("powerful", 0.00) is None
