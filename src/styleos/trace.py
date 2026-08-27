from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .io import atomic_write
from .models import TraceEvent

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|authorization)\s*[:=]\s*['\"]?[^\s'\"]+")


@dataclass(frozen=True)
class TracePolicy:
    capture_content: bool = False
    redact: bool = True
    retention_days: int = 30


class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...


class NullTraceSink:
    def emit(self, event: TraceEvent) -> None:
        del event


def redact_text(text: str) -> str:
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    text = _PHONE.sub("[REDACTED_PHONE]", text)
    return _SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", text)


class JsonlTraceSink:
    def __init__(self, path: str | Path, policy: TracePolicy | None = None):
        self.path = Path(path)
        self.policy = policy or TracePolicy()

    def emit(self, event: TraceEvent) -> None:
        payload = event.model_dump(mode="json", exclude_none=True)
        if not self.policy.capture_content:
            payload.pop("content", None)
        elif self.policy.redact and payload.get("content"):
            payload["content"] = redact_text(str(payload["content"]))
        if self.policy.redact:
            payload["metadata"] = self._redact_metadata(payload.get("metadata", {}))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    @staticmethod
    def _redact_metadata(value: object) -> object:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, list):
            return [JsonlTraceSink._redact_metadata(item) for item in value]
        if isinstance(value, dict):
            return {key: JsonlTraceSink._redact_metadata(item) for key, item in value.items()}
        return value


class LangfuseTraceSink:
    """Optional privacy-gated Langfuse adapter.

    The adapter intentionally receives already-sanitised metadata by default. Full content
    capture must be explicitly enabled through TracePolicy.
    """

    def __init__(self, policy: TracePolicy | None = None):
        self.policy = policy or TracePolicy()
        try:
            from langfuse import Langfuse
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Install styleos[langfuse] to use LangfuseTraceSink") from exc
        self.client = Langfuse()

    def emit(self, event: TraceEvent) -> None:  # pragma: no cover - external transport
        payload = event.model_dump(mode="json", exclude_none=True)
        content = payload.pop("content", None)
        if content and self.policy.capture_content:
            payload["content"] = redact_text(content) if self.policy.redact else content
        self.client.event(name=event.stage, metadata=payload)


def write_trace_receipt(path: str | Path, events: list[TraceEvent]) -> None:
    atomic_write(path, "\n".join(event.model_dump_json(exclude_none=True) for event in events) + "\n")
