from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .models import FeedbackRecord


class FeedbackStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, record: FeedbackRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json(exclude_none=True) + "\n")

    def list(self) -> list[FeedbackRecord]:
        if not self.path.exists():
            return []
        records: list[FeedbackRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    records.append(FeedbackRecord.model_validate_json(line))
                except Exception as exc:
                    raise ValueError(f"invalid feedback record at line {line_number}") from exc
        return records

    def summary(self) -> dict[str, object]:
        records = self.list()
        decisions = Counter(record.decision for record in records)
        packs = Counter(record.pack for record in records)
        sources = Counter(record.source_id or "unknown" for record in records)
        return {
            "total": len(records),
            "decisions": dict(decisions),
            "packs": dict(packs),
            "sources": dict(sources),
            "edited": sum(record.decision == "edited" for record in records),
        }

    def paired_examples(self, *, pack: str | None = None) -> list[dict[str, str | None]]:
        return [
            {
                "run_id": record.run_id,
                "pack": record.pack,
                "decision": record.decision,
                "edited_text": record.edited_text,
                "reason": record.reason,
                "source_id": record.source_id,
            }
            for record in self.list()
            if pack is None or record.pack == pack
        ]
