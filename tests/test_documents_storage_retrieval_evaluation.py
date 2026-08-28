from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from styleos.documents import ingest_document
from styleos.evaluation import (
    evaluate_audits,
    evidence_graph_ready,
    fine_tuning_ready,
    sample_tier,
    wilson_interval,
)
from styleos.ledger import audit_ledger, build_ledger
from styleos.retrieval import LocalHybridIndex
from styleos.storage import FileVault, MetadataStore


def test_document_ingestion_text_and_converter(tmp_path: Path) -> None:
    text = tmp_path / "source.md"
    text.write_text("canonical text", encoding="utf-8")
    document = ingest_document(text)
    assert document.source_name == "source.md"
    assert document.media_type == "text/markdown"
    assert document.document_id.startswith("doc_")
    assert document.metadata["conversion_method"] == "utf8_text"

    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"placeholder")

    class Converter:
        def convert(self, source: str) -> SimpleNamespace:
            assert source == str(pdf)
            return SimpleNamespace(text_content="converted text")

    converted = ingest_document(pdf, converter=Converter())
    assert converted.text == "converted text"
    with pytest.raises(FileNotFoundError):
        ingest_document(tmp_path / "missing.md")
    empty = tmp_path / "empty.md"
    empty.write_text(" ", encoding="utf-8")
    with pytest.raises(ValueError, match="no text"):
        ingest_document(empty)


def test_file_vault_and_metadata_outbox(tmp_path: Path) -> None:
    vault = FileVault(tmp_path / "vault")
    item = vault.put_text("profiles", "profile-1", "card.yaml", "content")
    assert vault.read_text("profiles", "profile-1", "card.yaml") == "content"
    with pytest.raises(ValueError, match="safe path"):
        vault.put_text("../bad", "id", "file", "content")
    with pytest.raises(FileNotFoundError):
        vault.read_text("profiles", "missing", "card.yaml")

    metadata = MetadataStore(tmp_path / "state.sqlite3")
    metadata.register_asset(item, metadata={"status": "draft"})
    stored = metadata.get_asset("profile-1")
    assert stored is not None
    assert stored["metadata"] == {"status": "draft"}
    assert metadata.get_asset("missing") is None

    event_id = metadata.enqueue("profile_saved", {"id": "profile-1"})
    assert metadata.pending()[0]["payload"] == {"id": "profile-1"}
    with pytest.raises(ValueError, match="positive"):
        metadata.pending(limit=0)
    metadata.mark_sent(event_id)
    assert metadata.pending() == []
    with pytest.raises(KeyError, match="not found"):
        metadata.mark_sent(event_id)
    with pytest.raises(ValueError, match="event_type"):
        metadata.enqueue(" ", {})


def test_local_hybrid_index_is_rebuildable(tmp_path: Path) -> None:
    index = LocalHybridIndex(tmp_path / "search.sqlite3")
    index.add("a", "科研论文需要保留数据与引用", metadata={"pack": "academic"})
    index.add("b", "口播脚本需要自然节奏", metadata={"pack": "self_media"})
    results = index.search("论文数据")
    assert results[0].document_id == "a"
    assert results[0].metadata["pack"] == "academic"
    index.add("a", "论文数据和公式", metadata={"updated": True})
    assert index.search("公式")[0].metadata["updated"] is True
    with pytest.raises(ValueError, match="required"):
        index.add("", "text")
    with pytest.raises(ValueError, match="query"):
        index.search(" ")
    with pytest.raises(ValueError, match="positive"):
        index.search("query", limit=0)
    index.clear()
    assert index.search("论文") == []


def test_evaluation_statistics_and_independent_guards() -> None:
    low, high = wilson_interval(8, 10)
    assert 0 < low < 0.8 < high < 1
    assert sample_tier(10) == "smoke"
    assert sample_tier(30) == "phase"
    assert sample_tier(100) == "formal_holdout"
    with pytest.raises(ValueError):
        wilson_interval(1, 0)
    with pytest.raises(ValueError):
        wilson_interval(2, 1)
    with pytest.raises(ValueError):
        sample_tier(0)

    source = "样本为 12 个。"
    ledger = build_ledger(source)
    passed = audit_ledger(ledger, source, source, run_id="pass", trace_id="t")
    failed = audit_ledger(ledger, source, "样本缺失。", run_id="fail", trace_id="t")
    evaluation = evaluate_audits([passed, failed])
    assert evaluation.total == 2
    assert evaluation.passed == 1
    assert evaluation.failed == 1
    assert evaluation.tier == "smoke"
    with pytest.raises(ValueError):
        evaluate_audits([])

    assert evidence_graph_ready(evaluated_cases=20, baseline_failures=4)
    assert not evidence_graph_ready(evaluated_cases=19, baseline_failures=19)
    with pytest.raises(ValueError):
        evidence_graph_ready(evaluated_cases=2, baseline_failures=3)
    assert fine_tuning_ready(
        paired_examples=2000, dspy_plateau_confirmed=True, holdout_regressions=0
    )
    assert not fine_tuning_ready(
        paired_examples=1999, dspy_plateau_confirmed=True, holdout_regressions=0
    )
    with pytest.raises(ValueError):
        fine_tuning_ready(
            paired_examples=-1, dspy_plateau_confirmed=False, holdout_regressions=0
        )
