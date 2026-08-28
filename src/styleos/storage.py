from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .io import atomic_write, sha256_text


def _safe_segment(value: str, *, field: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value:
        raise ValueError(f"{field} must be one safe path segment")
    return value


@dataclass(frozen=True)
class VaultObject:
    namespace: str
    object_id: str
    filename: str
    path: Path
    content_hash: str


class FileVault:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def put_text(
        self, namespace: str, object_id: str, filename: str, content: str
    ) -> VaultObject:
        namespace = _safe_segment(namespace, field="namespace")
        object_id = _safe_segment(object_id, field="object_id")
        filename = _safe_segment(filename, field="filename")
        path = self.root / namespace / object_id / filename
        atomic_write(path, content)
        return VaultObject(
            namespace=namespace,
            object_id=object_id,
            filename=filename,
            path=path,
            content_hash=sha256_text(content),
        )

    def read_text(self, namespace: str, object_id: str, filename: str) -> str:
        path = (
            self.root
            / _safe_segment(namespace, field="namespace")
            / _safe_segment(object_id, field="object_id")
            / _safe_segment(filename, field="filename")
        )
        if not path.is_file():
            raise FileNotFoundError(f"vault object not found: {namespace}/{object_id}/{filename}")
        return path.read_text(encoding="utf-8")


class MetadataStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    object_id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'sent')),
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                );
                """
            )

    def register_asset(self, item: VaultObject, *, metadata: dict[str, Any] | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assets(object_id, namespace, path, content_hash, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_id) DO UPDATE SET
                    namespace=excluded.namespace,
                    path=excluded.path,
                    content_hash=excluded.content_hash,
                    metadata_json=excluded.metadata_json
                """,
                (
                    item.object_id,
                    item.namespace,
                    str(item.path),
                    item.content_hash,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_asset(self, object_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE object_id = ?", (object_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        return result

    def enqueue(self, event_type: str, payload: dict[str, Any]) -> str:
        if not event_type.strip():
            raise ValueError("event_type is required")
        event_id = f"evt_{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO outbox(event_id, event_type, payload_json, status, created_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (
                    event_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return event_id

    def pending(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM outbox WHERE status = 'pending' ORDER BY created_at, event_id LIMIT ?",
                (limit,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def mark_sent(self, event_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE outbox SET status = 'sent', sent_at = ? "
                "WHERE event_id = ? AND status = 'pending'",
                (datetime.now(UTC).isoformat(), event_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"pending outbox event not found: {event_id}")
