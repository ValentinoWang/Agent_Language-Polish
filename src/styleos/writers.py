from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from .models import ContentLedger, StyleCard


@dataclass(frozen=True)
class RewriteRequest:
    source_text: str
    compiled_prompt: str
    ledger: ContentLedger
    style_card: StyleCard | None
    mode: str
    pack: str


class Writer(Protocol):
    name: str

    def rewrite(self, request: RewriteRequest) -> str: ...


class RuleBasedWriter:
    """Conservative offline baseline.

    This writer deliberately performs only locally auditable removals. It exists so every
    interface remains runnable without silently sending private text to a third party.
    """

    name = "offline-rule-based"

    _replacements = [
        (re.compile(r"^(?:在当今快速发展的时代|随着人工智能技术的不断进步)[，,：:\s]*"), ""),
        (
            re.compile(
                r"(?:值得注意的是|众所周知|总的来说|综上所述|总而言之|不仅如此|不难发现)[，,：:\s]*"
            ),
            "",
        ),
        (re.compile(r"这不仅是([^，。；]+)，更是([^。；]+)"), r"这是\1，也是\2"),
        (re.compile(r"不仅([^，。；]+)，(?:更|还)([^。；]+)"), r"\1，也\2"),
    ]

    def rewrite(self, request: RewriteRequest) -> str:
        text = request.source_text.strip()
        for pattern, replacement in self._replacements:
            text = pattern.sub(replacement, text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + ("\n" if request.source_text.endswith("\n") else "")


class OpenAICompatibleWriter:
    name = "openai-compatible"

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, model: str | None = None, timeout: float = 120):
        self.base_url = (base_url or os.getenv("STYLEOS_OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.getenv("STYLEOS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("STYLEOS_OPENAI_MODEL")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("OpenAI-compatible provider requires STYLEOS_OPENAI_API_KEY or OPENAI_API_KEY")
        if not self.model:
            raise ValueError("OpenAI-compatible provider requires an explicit STYLEOS_OPENAI_MODEL")

    def rewrite(self, request: RewriteRequest) -> str:  # pragma: no cover - external transport
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": request.compiled_prompt},
                    {"role": "user", "content": request.source_text},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()


class AnthropicWriter:
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, model: str | None = None, base_url: str | None = None, timeout: float = 120):
        self.api_key = api_key or os.getenv("STYLEOS_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or os.getenv("STYLEOS_ANTHROPIC_MODEL")
        self.base_url = (base_url or os.getenv("STYLEOS_ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("Anthropic provider requires STYLEOS_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY")
        if not self.model:
            raise ValueError("Anthropic provider requires an explicit STYLEOS_ANTHROPIC_MODEL")

    def rewrite(self, request: RewriteRequest) -> str:  # pragma: no cover - external transport
        response = httpx.post(
            f"{self.base_url}/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": self.model,
                "max_tokens": 4096,
                "temperature": 0.2,
                "system": request.compiled_prompt,
                "messages": [{"role": "user", "content": request.source_text}],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        blocks = response.json()["content"]
        return "".join(str(block.get("text", "")) for block in blocks if block.get("type") == "text").strip()


def writer_from_provider(provider: str) -> Writer:
    normalised = provider.strip().lower()
    if normalised == "offline":
        return RuleBasedWriter()
    if normalised in {"openai", "openai-compatible"}:
        return OpenAICompatibleWriter()
    if normalised == "anthropic":
        return AnthropicWriter()
    raise ValueError(f"unsupported writer provider: {provider}")
