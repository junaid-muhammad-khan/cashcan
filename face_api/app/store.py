"""SQLite storage. Embeddings only: raw photos are never written to disk."""
from __future__ import annotations

import sqlite3
import time

import numpy as np


MAX_TEMPLATES = 40  # per person; matching 40 templates is still instant, and more variety is the point


class FaceStore:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                wallet TEXT NOT NULL,
                consented_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                vec BLOB NOT NULL
            );
            """
        )

    def user_exists(self, user_id: str) -> bool:
        return self._db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone() is not None

    def add_user(self, user_id: str, wallet: str, embeddings: list[np.ndarray]) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO users(user_id, wallet, consented_at) VALUES (?,?,?)",
                (user_id, wallet, time.time()),
            )
            self._db.executemany(
                "INSERT INTO embeddings(user_id, vec) VALUES (?,?)",
                [(user_id, e.astype(np.float32).tobytes()) for e in embeddings],
            )

    def room_for(self, user_id: str, max_total: int = MAX_TEMPLATES) -> int:
        """How many more templates this person can take."""
        return max(max_total - len(self.embeddings_for(user_id)), 0)

    def add_embeddings(self, user_id: str, embeddings: list[np.ndarray], max_total: int = MAX_TEMPLATES) -> int:
        """Add more templates to an existing person (e.g. webcam frames next to a studio photo). Returns the new total."""
        if not self.user_exists(user_id):
            raise KeyError(user_id)
        have = len(self.embeddings_for(user_id))
        if have + len(embeddings) > max_total:
            raise ValueError(f"'{user_id}' has {have} templates; adding {len(embeddings)} would exceed {max_total}.")
        with self._db:
            self._db.executemany("INSERT INTO embeddings(user_id, vec) VALUES (?,?)",
                                 [(user_id, e.astype(np.float32).tobytes()) for e in embeddings])
        return have + len(embeddings)

    def delete_user(self, user_id: str) -> bool:
        with self._db:
            cur = self._db.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        return cur.rowcount > 0

    def set_wallet(self, user_id: str, wallet: str) -> None:
        with self._db:
            self._db.execute("UPDATE users SET wallet=? WHERE user_id=?", (wallet, user_id))

    def wallet(self, user_id: str) -> str | None:
        row = self._db.execute("SELECT wallet FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else None

    def embeddings_for(self, user_id: str) -> np.ndarray:
        rows = self._db.execute("SELECT vec FROM embeddings WHERE user_id=?", (user_id,)).fetchall()
        return np.stack([np.frombuffer(r[0], np.float32) for r in rows]) if rows else np.zeros((0, 512), np.float32)

    def all_embeddings(self) -> tuple[list[str], np.ndarray]:
        rows = self._db.execute("SELECT user_id, vec FROM embeddings").fetchall()
        if not rows:
            return [], np.zeros((0, 512), np.float32)
        return [r[0] for r in rows], np.stack([np.frombuffer(r[1], np.float32) for r in rows])
