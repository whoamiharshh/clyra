"""Kernel Cache - SQLite caches for agent-internal artifacts.

NOTE: This does NOT cache LLM completions. Bifrost handles LLM-completion
caching at the gateway layer; do not duplicate that here.

Two tables at .confidagent/cache.db:
  decision_cache    key = sha256(normalized_task + repo_file_manifest_hash)
                    value = JSON decision list, ttl = 7 days
  verification_cache key = sha256(normalized_claim)
                     value = JSON freshness result, ttl = settings.cache_ttl_seconds
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

from kernel.settings import settings

CACHE_DIR = os.path.join(os.getcwd(), ".confidagent")
DB_PATH = os.path.join(CACHE_DIR, "cache.db")

DECISION_TTL_SECONDS = 7 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decision_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS verification_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
"""

_SKIP_DIRS = {"__pycache__", ".venv", ".git", "node_modules", "venv", "env",
              "dist", "build", ".idea", ".vscode", ".pytest_cache", ".confidagent"}


def _connect() -> sqlite3.Connection:
    os.makedirs(CACHE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_task(task: str) -> str:
    """Lowercase, collapse whitespace for a stable task key."""
    return re.sub(r"\s+", " ", task.strip().lower())


def repo_file_manifest_hash(repo_path: str) -> str:
    """sha256 over sorted (rel_path, sha256(content)) pairs for all .py files.

    Changing any .py file invalidates the manifest, and thus the decision cache.
    """
    entries: List[tuple] = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, repo_path).replace("\\", "/")
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            entries.append((rel, hashlib.sha256(data).hexdigest()))
    entries.sort()
    blob = "\n".join(f"{p}:{h}" for p, h in entries)
    return _sha(blob)


def _enabled() -> bool:
    return os.getenv("CONFIDAGENT_NO_CACHE", "") != "1"


def _lookup(table: str, key: str) -> Optional[Any]:
    if not _enabled():
        return None
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT value, expires_at FROM {table} WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if row[1] < time.time():
            conn.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
            conn.commit()
            return None
        return json.loads(row[0])
    finally:
        conn.close()


def _store(table: str, key: str, value: Any, ttl_seconds: int) -> None:
    if not _enabled():
        return
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            f"INSERT INTO {table}(key, value, created_at, expires_at) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=?, created_at=?, expires_at=?",
            (key, json.dumps(value), now, now + ttl_seconds,
             json.dumps(value), now, now + ttl_seconds),
        )
        conn.commit()
    finally:
        conn.close()


def prune() -> int:
    """Delete expired rows from both tables; returns rows removed."""
    if not os.path.exists(DB_PATH):
        return 0
    conn = _connect()
    try:
        removed = 0
        for table in ("decision_cache", "verification_cache"):
            cur = conn.execute(f"DELETE FROM {table} WHERE expires_at < ?", (time.time(),))
            removed += cur.rowcount
        conn.commit()
        return removed
    finally:
        conn.close()


# --------------------------------------------------------------------- #
# Decision-plan cache
# --------------------------------------------------------------------- #

def get_decision(task: str, repo_path: str) -> Optional[list]:
    """Cached decision list for (task, repo state), or None."""
    key = _sha(normalize_task(task) + repo_file_manifest_hash(repo_path))
    return _lookup("decision_cache", key)


def put_decision(task: str, repo_path: str, decisions: list) -> None:
    key = _sha(normalize_task(task) + repo_file_manifest_hash(repo_path))
    _store("decision_cache", key, decisions, DECISION_TTL_SECONDS)


# --------------------------------------------------------------------- #
# Claim verification cache
# --------------------------------------------------------------------- #

def get_verification(claim: str) -> Optional[dict]:
    """Cached freshness result for a claim, or None."""
    key = _sha(normalize_task(claim))
    return _lookup("verification_cache", key)


def put_verification(claim: str, result: dict) -> None:
    key = _sha(normalize_task(claim))
    _store("verification_cache", key, result, settings.cache_ttl_seconds)


# Prune expired rows once at process start.
try:
    prune()
except Exception:
    pass
