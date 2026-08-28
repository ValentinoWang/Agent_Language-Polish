from __future__ import annotations

import json
from pathlib import Path

import pytest

from styleos.feedback import FeedbackStore
from styleos.ledger import build_ledger
from styleos.models import FeedbackRecord, StyleCard, TraceEvent
from styleos.pack import PackRepository
from styleos.trace import (
    JsonlTraceSink,
    NullTraceSink,
    TracePolicy,
    redact_text,
    write_trace_receipt,
)
from styleos.writers import (
    AnthropicWriter,
    OpenAICompatibleWriter,
    RewriteRequest,
    RuleBasedWriter,
    writer_from_provider,
)


def _request(text: str) -> RewriteRequest:
    return RewriteRequest(
        source_text=text,
        compiled_prompt="prompt",
        ledger=build_ledger(text),
        style_card=StyleCard(id="test"),
        mode="balanced",
        pack="global",
    )


def test_pack_repository_lint_and_build(repository_root: Path, tmp_path: Path) -> None:
    repository = PackRepository(repository_root / "packs")
    assert {path.name for path in repository.discover()} == {
        "academic",
        "business",
        "distill",
        "global",
        "imitate",
        "self_media",
    }
    assert not any(repository.lint_all().values())
    built = repository.build_all_skills(tmp_path / "skills")
    assert len(built) == 6
    assert "Execution contract" in (tmp_path / "skills/global/SKILL.md").read_text()
    with pytest.raises(FileNotFoundError):
        repository.load("missing")

    broken = tmp_path / "packs/broken"
    broken.mkdir(parents=True)
    (broken / "pack.yaml").write_text("not: a-valid-pack\n", encoding="utf-8")
    assert PackRepository(tmp_path / "packs").lint("broken")
    assert PackRepository(tmp_path / "absent").discover() == []


def test_offline_and_provider_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    source = "值得注意的是，项目有 12 个样本。\n"
    rewritten = RuleBasedWriter().rewrite(_request(source))
    assert "值得注意的是" not in rewritten
    assert "12" in rewritten
    assert rewritten.endswith("\n")
    assert isinstance(writer_from_provider(" OFFLINE "), RuleBasedWriter)
    with pytest.raises(ValueError, match="unsupported"):
        writer_from_provider("other")
    with pytest.raises(ValueError, match="API_KEY"):
        OpenAICompatibleWriter(api_key="", model="model")
    with pytest.raises(ValueError, match="MODEL"):
        OpenAICompatibleWriter(api_key="key", model="")
    with pytest.raises(ValueError, match="API_KEY"):
        AnthropicWriter(api_key="", model="model")
    with pytest.raises(ValueError, match="MODEL"):
        AnthropicWriter(api_key="key", model="")

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": " openai result "}}]}

    monkeypatch.setattr("styleos.writers.httpx.post", lambda *args, **kwargs: Response())
    assert OpenAICompatibleWriter(api_key="key", model="model").rewrite(_request(source)) == "openai result"

    class AnthropicResponse(Response):
        def json(self) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "one"}, {"type": "other"}, {"type": "text", "text": "two"}]}

    monkeypatch.setattr("styleos.writers.httpx.post", lambda *args, **kwargs: AnthropicResponse())
    assert AnthropicWriter(api_key="key", model="model").rewrite(_request(source)) == "onetwo"


def test_feedback_store_roundtrip_and_invalid_line(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "feedback.jsonl")
    assert store.list() == []
    record = FeedbackRecord(
        run_id="run",
        pack="global.deai",
        profile_id="profile",
        decision="edited",
        edited_text="edited",
        source_id="source-a",
    )
    store.append(record)
    assert store.list() == [record]
    assert store.summary()["edited"] == 1
    assert store.paired_examples(pack="global.deai")[0]["edited_text"] == "edited"
    assert store.paired_examples(pack="other") == []
    (tmp_path / "bad.jsonl").write_text("{}\nnot-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        FeedbackStore(tmp_path / "bad.jsonl").list()


def test_trace_redaction_and_policies(tmp_path: Path) -> None:
    sensitive = "a@example.com 13800138000 api_key=secret"
    redacted = redact_text(sensitive)
    assert "example.com" not in redacted
    assert "13800138000" not in redacted
    assert "secret" not in redacted

    event = TraceEvent(
        trace_id="trace",
        run_id="run",
        stage="test",
        metadata={"nested": [sensitive]},
        content=sensitive,
    )
    path = tmp_path / "trace.jsonl"
    JsonlTraceSink(path).emit(event)
    payload = json.loads(path.read_text())
    assert "content" not in payload
    assert "REDACTED_EMAIL" in payload["metadata"]["nested"][0]

    content_path = tmp_path / "content.jsonl"
    JsonlTraceSink(content_path, TracePolicy(capture_content=True, redact=False)).emit(event)
    assert json.loads(content_path.read_text())["content"] == sensitive
    NullTraceSink().emit(event)
    receipt = tmp_path / "receipt.jsonl"
    write_trace_receipt(receipt, [event])
    assert json.loads(receipt.read_text())["trace_id"] == "trace"
