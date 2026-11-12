"""Tests for kernel/cache.py - SQLite caches."""

import os
import tempfile
import time

import pytest

import kernel.cache as cache


def _fresh_db(tmp_path, monkeypatch):
    cache.CACHE_DIR = str(tmp_path)
    cache.DB_PATH = os.path.join(str(tmp_path), "cache.db")


def test_decision_hit_on_unchanged_repo(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    repo = os.path.join(str(tmp_path), "repo")
    os.makedirs(repo)
    with open(os.path.join(repo, "a.py"), "w") as f:
        f.write("x = 1\n")
    cache.put_decision("fix bug", repo, [{"id": 1, "name": "fix"}])
    hit = cache.get_decision("fix bug", repo)
    assert hit == [{"id": 1, "name": "fix"}]


def test_decision_miss_after_file_change(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    repo = os.path.join(str(tmp_path), "repo")
    os.makedirs(repo)
    with open(os.path.join(repo, "a.py"), "w") as f:
        f.write("x = 1\n")
    cache.put_decision("fix bug", repo, [{"id": 1}])
    # Change a file -> manifest hash changes -> miss
    with open(os.path.join(repo, "a.py"), "w") as f:
        f.write("x = 2\n")
    hit = cache.get_decision("fix bug", repo)
    assert hit is None


def test_ttl_expiry_via_monkeypatched_time(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    repo = os.path.join(str(tmp_path), "repo")
    os.makedirs(repo)
    with open(os.path.join(repo, "a.py"), "w") as f:
        f.write("x = 1\n")
    cache.put_decision("fix bug", repo, [{"id": 1}])
    # Monkeypatch time.time to be far in the future so the entry expires.
    original_time = time.time
    monkeypatch.setattr(cache.time, "time", lambda: original_time() + 10 * 365 * 24 * 3600)
    hit = cache.get_decision("fix bug", repo)
    assert hit is None


def test_no_cache_bypass(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    repo = os.path.join(str(tmp_path), "repo")
    os.makedirs(repo)
    with open(os.path.join(repo, "a.py"), "w") as f:
        f.write("x = 1\n")
    monkeypatch.setenv("CONFIDAGENT_NO_CACHE", "1")
    cache.put_decision("fix bug", repo, [{"id": 1}])
    hit = cache.get_decision("fix bug", repo)
    assert hit is None
    monkeypatch.delenv("CONFIDAGENT_NO_CACHE", raising=False)
