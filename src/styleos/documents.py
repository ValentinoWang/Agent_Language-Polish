from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .io import sha256_text


class ConversionResult(Protocol):
    text_content: str


class DocumentConverter(Protocol):
    def convert(self, source: str) -> ConversionResult: ...


class CanonicalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    source_name: str
    media_type: str
    text: str
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def ingest_document(
    path: str | Path, *, converter: DocumentConverter | None = None
) -> CanonicalDocument:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"document not found: {source}")
    suffix = source.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        text = source.read_text(encoding="utf-8")
        method = "utf8_text"
    else:
        if converter is None:
            try:
                from markitdown import MarkItDown
            except ImportError as exc:
                raise RuntimeError(
                    "non-text documents require the documents extra: pip install 'styleos[documents]'"
                ) from exc
            converter = MarkItDown()
        text = converter.convert(str(source)).text_content
        method = type(converter).__name__
    if not text.strip():
        raise ValueError(f"document contains no text: {source}")
    content_hash = sha256_text(text)
    media_type = {
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
    }.get(suffix, mimetypes.guess_type(source.name)[0] or "application/octet-stream")
    return CanonicalDocument(
        document_id=f"doc_{content_hash[:16]}",
        source_name=source.name,
        media_type=media_type,
        text=text,
        content_hash=content_hash,
        metadata={"conversion_method": method, "bytes": source.stat().st_size},
    )
