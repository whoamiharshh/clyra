"""Demo database access module."""

import sqlite3
from typing import Any, List, Tuple


class Database:
    """Simple wrapper around SQLite with safe, parameterized queries."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection."""
        return sqlite3.connect(self.db_path)

    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> List[Tuple]:
        """
        Execute a SQL statement using parameterized arguments.

        Returns fetched rows for SELECT statements; otherwise returns an empty list.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            if query.lstrip().upper().startswith("SELECT"):
                return cursor.fetchall()

            conn.commit()
            return []

    def get_user_by_username(self, username: str):
        """
        Retrieve a user record by username using a safe, parameterized query.
        Returns a tuple (id, username, password_hash) or None.
        """
        rows = self.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        )
        return rows[0] if rows else None
