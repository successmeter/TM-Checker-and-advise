"""Keyword search over Manual chunks, using SQLite's built-in full-text search (BM25 ranking).

The Manual is legal text whose key terms ("deceptively similar", "same description", "inherently adapted")
are exactly what users and findings mention, so keyword search works well and needs no embedding service.
"""

import re
import sqlite3
from pathlib import Path

from .parse import Chunk

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is", "are", "be", "with", "by", "as", "that", "this", "it"}


_SCHEMA = ("CREATE VIRTUAL TABLE {name} USING fts5("
           "id UNINDEXED, url UNINDEXED, title, heading, text, published UNINDEXED, tokenize='porter unicode61')")


class ManualIndex:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        if not self._columns():
            self._db.execute(_SCHEMA.format(name="chunks"))

    def _columns(self) -> list[str]:
        return [row[1] for row in self._db.execute("PRAGMA table_info(chunks)")]

    def _select(self) -> str:
        # Indexes built before dates were recorded have no "published" column.
        published = "published" if "published" in self._columns() else "''"
        return f"SELECT id, url, title, heading, text, {published} FROM chunks"

    def build(self, chunks: list[Chunk]) -> None:
        with self._db:
            self._db.execute("DROP TABLE IF EXISTS chunks")
            self._db.execute(_SCHEMA.format(name="chunks"))
            self._db.executemany("INSERT INTO chunks (id, url, title, heading, text, published) VALUES (?, ?, ?, ?, ?, ?)",
                                 [(c.id, c.url, c.title, c.heading, c.text, c.published) for c in chunks])

    def count(self) -> int:
        return self._db.execute("SELECT count(*) FROM chunks").fetchone()[0]

    def page_count(self) -> int:
        return self._db.execute("SELECT count(DISTINCT url) FROM chunks").fetchone()[0]

    def search(self, query: str, limit: int = 5) -> list[Chunk]:
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in _STOP]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))
        weights = "0, 0, 2.0, 3.0, 1.0" + (", 0" if "published" in self._columns() else "")
        rows = self._db.execute(
            f"{self._select()} WHERE chunks MATCH ? ORDER BY bm25(chunks, {weights}) LIMIT ?",
            (match, limit),
        ).fetchall()
        return [Chunk(*row) for row in rows]

    def get(self, chunk_id: str) -> Chunk | None:
        row = self._db.execute(f"{self._select()} WHERE id = ?", (chunk_id,)).fetchone()
        return Chunk(*row) if row else None
