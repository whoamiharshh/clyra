"""Tests for kernel/memory.py - SQLite file-memory store."""

import os
import tempfile

import pytest

from kernel.memory import get, outline_or_build, put, stats


def _write(tmp_path, name, source):
    p = os.path.join(tmp_path, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(source)
    return p


def _fresh_db(tmp_path, monkeypatch):
    """Point memory module at a tmp db so tests don't collide."""
    import kernel.memory as mem
    mem.LEDGER_DIR = str(tmp_path)
    mem.DB_PATH = os.path.join(str(tmp_path), "memory.db")


def test_put_get_roundtrip(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    p = _write(tmp_path, "mod.py", "def foo():\n    return 1\n")
    put(str(tmp_path), os.path.basename(p), "def foo():\n    return 1\n", "first line")
    entry = get(str(tmp_path), os.path.basename(p))
    assert entry is not None
    assert entry.outline == "def foo():\n    return 1\n"
    assert entry.summary == "first line"


def test_hash_change_invalidates(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    p = _write(tmp_path, "mod.py", "def foo():\n    return 1\n")
    put(str(tmp_path), os.path.basename(p), "old", "old")
    # Change file content
    with open(p, "w", encoding="utf-8") as f:
        f.write("def bar():\n    return 2\n")
    entry = get(str(tmp_path), os.path.basename(p))
    assert entry is None


def test_outline_or_build_miss_then_hit(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    p = _write(tmp_path, "mod.py", "def foo():\n    return 1\n")
    outline, was_cached = outline_or_build(str(tmp_path), os.path.basename(p))
    assert was_cached is False
    assert "def foo()" in outline
    outline2, was_cached2 = outline_or_build(str(tmp_path), os.path.basename(p))
    assert was_cached2 is True
    assert outline2 == outline


def test_stats_counters_increment(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    p = _write(tmp_path, "mod.py", "def foo():\n    return 1\n")
    s0 = stats()
    put(str(tmp_path), os.path.basename(p), "def foo():\n    return 1\n", "first line")
    s1 = stats()
    assert s1["total_misses"] > s0["total_misses"]
    get(str(tmp_path), os.path.basename(p))
    s2 = stats()
    assert s2["total_hits"] > s1["total_hits"]
