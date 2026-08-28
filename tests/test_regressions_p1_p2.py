from __future__ import annotations

from pathlib import Path

import yaml

from styleos.ledger import audit_ledger, build_ledger
from styleos.pack import PackRepository
from styleos.rules import RuleEngine
from styleos.writers import RewriteRequest, RuleBasedWriter

ROOT = Path(__file__).parents[1]


def request(text: str) -> RewriteRequest:
    return RewriteRequest(
        source_text=text,
        compiled_prompt="prompt",
        ledger=build_ledger(text),
        style_card=None,
        mode="conservative",
        pack="global",
    )


def test_rule_migration_and_loose_enumeration() -> None:
    engine = RuleEngine.from_file(ROOT / "packs/global/deai.negative.zh.yaml")
    cases = {
        "总而言之，我们继续。": "empty_transition",
        "不仅如此，下一点更关键。": "empty_transition",
        "不难发现，数据变了。": "empty_transition",
        "让我们一起看看结果。": "ai_pet_phrases",
        "这个方案赋能业务。": "abstract_cliche_density",
        "我们要打造闭环。": "abstract_cliche_density",
        "两项能力深度融合。": "abstract_cliche_density",
        "这件事引发了广泛关注。": "abstract_cliche_density",
        "首先说明第一点。其次说明第二点。": "mechanical_enumeration",
        "近年来，越来越多的人开始关注。": "empty_opening",
    }
    for text, rule_id in cases.items():
        by_id = {finding.rule_id: finding for finding in engine.scan(text)}
        assert by_id[rule_id].status == "hit", (text, rule_id, by_id[rule_id])


def test_writer_keeps_sentence_complete() -> None:
    source = "其次，这不仅是数字的提升，更是价值的体现。"
    output = RuleBasedWriter().rewrite(request(source))
    assert output == "其次，这是数字的提升，也是价值的体现。"
    assert output != "其次，价值的体现。"


def test_moderate_semantic_similarity_requires_review() -> None:
    source = "这不仅是数字的提升，更是价值的体现。"
    ledger = build_ledger(source, claims=[source])
    report = audit_ledger(
        ledger,
        source,
        "其次，价值的体现。",
        run_id="run",
        trace_id="trace",
    )
    assert report.verdict.value == "review_required"
    assert report.semantic_findings[0].status == "uncertain"


def test_prompt_compilation_and_drift(tmp_path: Path) -> None:
    packs = tmp_path / "packs"
    global_dir = packs / "global"
    (global_dir / "examples").mkdir(parents=True)
    (global_dir / "deai.negative.zh.yaml").write_text(
        (ROOT / "packs/global/deai.negative.zh.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    prompt = (
        "before\n<!-- STYLEOS:NEGATIVE_RULES:START -->\n"
        "stale\n<!-- STYLEOS:NEGATIVE_RULES:END -->\nafter\n"
    )
    (global_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    manifest = {
        "pack": "global.deai",
        "name": "Global",
        "kind": "utility",
        "version": "1.0.0",
        "owner": "test",
        "description": "test",
        "inputs": [],
        "outputs": [],
        "targets": {"prompt": {"file": "prompt.md"}},
        "delivery": {"prompt": "ready"},
        "validation": {"example": "passed", "formal_blind_test": "pending"},
        "maturity": "planned",
        "eval": {"evaluator_profile": "test", "baseline": "test"},
    }
    (global_dir / "pack.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (global_dir / "examples/example.md").write_text("x", encoding="utf-8")

    repository = PackRepository(packs)
    assert repository.prompt_drift("global")
    try:
        repository.build_prompt("global", check=True)
    except ValueError as exc:
        assert "drift" in str(exc)
    else:
        raise AssertionError("drift check should fail")
    repository.build_prompt("global")
    assert not repository.prompt_drift("global")
    compiled = (global_dir / "prompt.md").read_text(encoding="utf-8")
    assert "[empty_opening]" in compiled
    assert "总而言之" in compiled

    markerless = compiled.replace("<!-- STYLEOS:NEGATIVE_RULES:START -->", "").replace(
        "<!-- STYLEOS:NEGATIVE_RULES:END -->", ""
    )
    (global_dir / "prompt.md").write_text(markerless, encoding="utf-8")
    try:
        repository.build_prompt("global", check=True)
    except ValueError as exc:
        assert "missing rule projection markers" in str(exc)
    else:
        raise AssertionError("global prompt must retain the rule projection markers")
