"""Keyword search over Manual chunks, using SQLite's built-in full-text search (BM25 ranking).

The Manual is legal text whose key terms ("deceptively similar", "same description", "inherently adapted")
are exactly what users and findings mention, so keyword search works well and needs no embedding service.
"""

import re
import sqlite3
from pathlib import Path

from .parse import Chunk

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is", "are", "be", "with", "by", "as", "that", "this", "it"}


class ManualIndex:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
            "id UNINDEXED, url UNINDEXED, title, heading, text, tokenize='porter unicode61')"
        )

    def build(self, chunks: list[Chunk]) -> None:
        with self._db:
            self._db.execute("DELETE FROM chunks")
            self._db.executemany("INSERT INTO chunks (id, url, title, heading, text) VALUES (?, ?, ?, ?, ?)",
                                 [(c.id, c.url, c.title, c.heading, c.text) for c in chunks])

    def count(self) -> int:
        return self._db.execute("SELECT count(*) FROM chunks").fetchone()[0]

    def search(self, query: str, limit: int = 5) -> list[Chunk]:
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in _STOP]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))
        rows = self._db.execute(
            "SELECT id, url, title, heading, text FROM chunks WHERE chunks MATCH ? "
            "ORDER BY bm25(chunks, 0, 0, 2.0, 3.0, 1.0) LIMIT ?",
            (match, limit),
        ).fetchall()
        return [Chunk(*row) for row in rows]

    def get(self, chunk_id: str) -> Chunk | None:
        row = self._db.execute("SELECT id, url, title, heading, text FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
        return Chunk(*row) if row else None
