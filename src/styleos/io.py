from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_yaml(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def dump_yaml(data: Any, path: str | Path) -> None:
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json", exclude_none=True)
    atomic_write(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def dump_json(data: Any, path: str | Path, *, indent: int = 2) -> None:
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json", exclude_none=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=indent, default=str) + "\n")


def atomic_write(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
