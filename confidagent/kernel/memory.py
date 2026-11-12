"""Kernel Memory - SQLite file-memory store.

The agent must never pay twice for the same file content: outlines and summaries
are persisted keyed by content hash, and invalidated automatically when a file
changes.

Runnable: python -m kernel.memory stats
"""

import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

LEDGER_DIR = os.path.join(os.getcwd(), ".confidagent")
DB_PATH = os.path.join(LEDGER_DIR, "memory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    content_hash TEXT,
    outline TEXT,
    summary TEXT,
    last_seen_ts TEXT,
    times_seen INT
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@dataclass
class MemoryEntry:
    path: str
    content_hash: str
    outline: str
    summary: str
    last_seen_ts: str
    times_seen: int


def _connect() -> sqlite3.Connection:
    os.makedirs(LEDGER_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def _file_hash(repo_path: str, rel_path: str) -> Optional[tuple]:
    """Return (sha256_hex, byte_len) of the file, or None if unreadable."""
    full = os.path.join(repo_path, rel_path)
    try:
        with open(full, "rb") as f:
            data = f.read()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest(), len(data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get(repo_path: str, rel_path: str) -> Optional[MemoryEntry]:
    """Return the cached entry if content_hash still matches; else invalidate and None."""
    hashed = _file_hash(repo_path, rel_path)
    if hashed is None:
        return None
    digest, size = hashed

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT path, content_hash, outline, summary, last_seen_ts, times_seen "
            "FROM files WHERE path = ?",
            (rel_path,),
        ).fetchone()
        if row is None:
            return None

        if row[1] != digest:
            # Content changed since it was remembered: invalidate.
            conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
            conn.commit()
            return None

        # Hit: bump counters, account bytes avoided.
        ts = _now_iso()
        seen = (row[5] or 0) + 1
        conn.execute(
            "UPDATE files SET last_seen_ts = ?, times_seen = ? WHERE path = ?",
            (ts, seen, rel_path),
        )
        prev = _meta_get(conn, "bytes_avoided", "0")
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('bytes_avoided', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = ?",
            (str(int(prev) + size), str(int(prev) + size)),
        )
        _meta_increment(conn, "total_hits")
        conn.commit()
        return MemoryEntry(rel_path, row[1], row[2], row[3], ts, seen)
    finally:
        conn.close()


def put(repo_path: str, rel_path: str, outline: str, summary: str) -> None:
    """Upsert the entry with the file's current hash."""
    hashed = _file_hash(repo_path, rel_path)
    if hashed is None:
        return
    digest, size = hashed

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT times_seen FROM files WHERE path = ?", (rel_path,)
        ).fetchone()
        times_seen = (row[0] if row else 0) or 0
        conn.execute(
            "INSERT INTO files(path, content_hash, outline, summary, last_seen_ts, times_seen) "
            "VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET content_hash=?, outline=?, summary=?, "
            "last_seen_ts=?, times_seen=?",
            (rel_path, digest, outline, summary, _now_iso(), times_seen,
             digest, outline, summary, _now_iso(), times_seen),
        )
        _meta_increment(conn, "total_misses")
        conn.commit()
    finally:
        conn.close()


def outline_or_build(repo_path: str, rel_path: str) -> tuple:
    """(outline, was_cached). On miss builds via kernel.context.file_outline and stores."""
    entry = get(repo_path, rel_path)
    if entry is not None and entry.outline:
        return entry.outline, True

    from kernel.context import file_outline  # local import to avoid cycles
    outline = file_outline(repo_path, rel_path)
    # Cheap deterministic summary: first docstring/header line.
    first_line = ""
    for ln in outline.splitlines():
        if ln.strip():
            first_line = ln.strip()
            break
    put(repo_path, rel_path, outline, first_line)
    return outline, False


def _meta_get(conn: sqlite3.Connection, key: str, default: str = "0") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def _meta_increment(conn: sqlite3.Connection, key: str) -> None:
    prev = int(_meta_get(conn, key, "0"))
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, str(prev + 1), str(prev + 1)),
    )


def stats() -> dict:
    """{entries, total_hits, total_misses, bytes_avoided}."""
    if not os.path.exists(DB_PATH):
        return {"entries": 0, "total_hits": 0, "total_misses": 0, "bytes_avoided": 0}

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(_SCHEMA)
        entries = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        total_hits = int(_meta_get(conn, "total_hits", "0"))
        total_misses = int(_meta_get(conn, "total_misses", "0"))
        bytes_avoided = int(_meta_get(conn, "bytes_avoided", "0"))
    finally:
        conn.close()
    return {
        "entries": entries,
        "total_hits": total_hits,
        "total_misses": total_misses,
        "bytes_avoided": bytes_avoided,
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(json.dumps(stats(), indent=2))
    else:
        print("usage: python -m kernel.memory stats")
