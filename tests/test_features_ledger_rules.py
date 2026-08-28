from __future__ import annotations

from pathlib import Path

import pytest

from styleos.features import (
    aggregate_features,
    extract_style_features,
    split_paragraphs,
    split_sentences,
)
from styleos.ledger import audit_ledger, build_ledger
from styleos.models import DetectionLevel, NegativeRule, RuleDetector
from styleos.rules import RuleEngine


def _rule(
    rule_id: str,
    *,
    level: DetectionLevel = DetectionLevel.deterministic,
    detector_type: str = "literal",
    patterns: list[str] | None = None,
    max_count: int | None = None,
) -> NegativeRule:
    return NegativeRule(
        id=rule_id,
        name=rule_id,
        detect="test",
        policy="conditional",
        fix_hint="fix",
        detector=RuleDetector(
            level=level,
            type=detector_type,
            patterns=patterns or [],
            max_count=max_count,
        ),
    )


def test_feature_extraction_and_aggregation() -> None:
    text = "请先看数据！结果可靠吗？\n\n第二段更长一些。"
    assert len(split_sentences(text)) == 3
    assert len(split_paragraphs(text)) == 2
    features = extract_style_features(text)
    assert features["sentence_count"] == 3
    assert features["paragraph_count"] == 2
    assert features["question_ratio"] > 0
    assert features["imperative_ratio"] > 0
    aggregate = aggregate_features([text, "另一篇文本。"])
    assert aggregate["document_count"] == 2
    assert len(aggregate["per_document"]) == 2
    with pytest.raises(ValueError, match="at least one"):
        aggregate_features([])


def test_ledger_preserves_hard_locks_and_detects_drift() -> None:
    source = '项目 ABC_1 在 2026 年记录 12.5kg，结果与 B 相关 [1]，并称“保持边界”。'
    ledger = build_ledger(source, must_keep=["项目"])
    assert "12.5kg" in ledger.hard_locks.numbers
    assert "2026" in ledger.hard_locks.dates
    assert ledger.semantic_locks

    passed = audit_ledger(ledger, source, source, run_id="run", trace_id="trace")
    assert passed.verdict.value == "pass"
    missing = audit_ledger(
        ledger,
        source,
        "项目结果与 B 相关。",
        run_id="run",
        trace_id="trace",
    )
    assert missing.verdict.value == "fail"
    added = audit_ledger(
        build_ledger("样本为 12 个。"),
        "样本为 12 个。",
        "样本为 12 个，新增 99 个。",
        run_id="run",
        trace_id="trace",
    )
    assert "99" in added.new_hard_facts
    with pytest.raises(ValueError, match="must not be empty"):
        build_ledger(" ")


def test_ledger_blocks_claim_and_causality_upgrades() -> None:
    claim_source = "结果可能改善表现。"
    claim = build_ledger(claim_source, claims=[claim_source])
    report = audit_ledger(
        claim,
        claim_source,
        "结果证明改善表现。",
        run_id="r",
        trace_id="t",
    )
    assert report.verdict.value == "fail"

    causal_source = "A 与 B 相关。"
    causal = build_ledger(causal_source)
    report = audit_ledger(
        causal,
        causal_source,
        "A 导致 B。",
        run_id="r",
        trace_id="t",
    )
    assert report.verdict.value == "fail"

    uncertain = audit_ledger(
        build_ledger("仅在当前范围内结果可能有效。"),
        "仅在当前范围内结果可能有效。",
        "完全不同的表述。",
        run_id="r",
        trace_id="t",
    )
    assert uncertain.verdict.value == "review_required"


def test_rule_projection_and_all_detector_levels(repository_root: Path) -> None:
    engine = RuleEngine.from_file(repository_root / "packs/global/deai.negative.zh.yaml")
    engine.assert_projection_parity()
    findings = engine.scan("值得注意的是，这很炸裂！！！")
    by_id = {finding.rule_id: finding for finding in findings}
    assert by_id["empty_transition"].status == "hit"
    assert by_id["exclamation_overuse"].occurrences == 1
    assert by_id["per_paragraph_summary"].status == "pending_semantic"
    assert by_id["known_concept_lecture"].status == "manual_review"
    assert not any(item.status == "pending_semantic" for item in engine.scan("text", include_pending=False))

    uniform = RuleEngine(
        [
            _rule(
                "uniform_sentence_shape",
                level=DetectionLevel.statistical,
                detector_type="counter",
            )
        ]
    ).scan("一二三四。一二三四。一二三四。一二三四。")
    assert uniform[0].status == "hit"
    unknown = RuleEngine(
        [_rule("unknown", level=DetectionLevel.statistical, detector_type="counter")]
    ).scan("text")
    assert unknown[0].status == "clear"

    capped = RuleEngine([_rule("cap", patterns=["x"], max_count=1)]).scan("xxx")
    assert capped[0].occurrences == 2
    with pytest.raises(ValueError, match="unique"):
        RuleEngine([_rule("same"), _rule("same")])
