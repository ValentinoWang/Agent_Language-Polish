from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_TOKEN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text)}


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    text: str
    score: float
    metadata: dict[str, Any]


class LocalHybridIndex:
    """Rebuildable local index combining token overlap and character similarity."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS documents ("
                "document_id TEXT PRIMARY KEY, text TEXT NOT NULL, metadata_json TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def add(self, document_id: str, text: str, *, metadata: dict[str, Any] | None = None) -> None:
        if not document_id.strip() or not text.strip():
            raise ValueError("document_id and text are required")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO documents(document_id, text, metadata_json) VALUES (?, ?, ?) "
                "ON CONFLICT(document_id) DO UPDATE SET text=excluded.text, "
                "metadata_json=excluded.metadata_json",
                (document_id, text, json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)),
            )

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        if not query.strip():
            raise ValueError("query is required")
        if limit < 1:
            raise ValueError("limit must be positive")
        query_tokens = _tokens(query)
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM documents").fetchall()
        hits: list[SearchHit] = []
        for row in rows:
            document_tokens = _tokens(row["text"])
            union = query_tokens | document_tokens
            token_score = len(query_tokens & document_tokens) / len(union) if union else 0.0
            character_score = SequenceMatcher(None, query, row["text"]).ratio()
            score = 0.7 * token_score + 0.3 * character_score
            if score > 0:
                hits.append(
                    SearchHit(
                        document_id=row["document_id"],
                        text=row["text"],
                        score=round(score, 6),
                        metadata=json.loads(row["metadata_json"]),
                    )
                )
        return sorted(hits, key=lambda hit: (-hit.score, hit.document_id))[:limit]

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM documents")
