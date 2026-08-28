from __future__ import annotations

import re
import statistics
from pathlib import Path

from .features import split_sentences
from .io import load_yaml
from .models import DetectionLevel, NegativeRule, RuleFinding


class RuleEngine:
    def __init__(self, rules: list[NegativeRule]):
        ids = [rule.id for rule in rules]
        if len(ids) != len(set(ids)):
            raise ValueError("negative rule ids must be unique")
        self.rules = rules

    @classmethod
    def from_file(cls, path: str | Path) -> RuleEngine:
        payload = load_yaml(path)
        return cls([NegativeRule.model_validate(item) for item in payload.get("rules", [])])

    def project_prompt(self) -> str:
        sections = ["【条件式文风规则】"]
        for index, rule in enumerate(self.rules, 1):
            exception = "；允许条件：" + " / ".join(rule.allow_when) if rule.allow_when else ""
            sections.append(f"{index}. [{rule.id}] {rule.name}：{rule.detect}。处置：{rule.fix_hint}{exception}。")
        return "\n".join(sections)

    def project_validator_manifest(self) -> list[dict[str, object]]:
        return [{"id": rule.id, "level": rule.detector.level.value, "type": rule.detector.type, "blocking": rule.detector.blocking, "patterns": rule.detector.patterns} for rule in self.rules]

    def assert_projection_parity(self) -> None:
        prompt = self.project_prompt()
        manifest_ids = {item["id"] for item in self.project_validator_manifest()}
        prompt_ids = {rule.id for rule in self.rules if f"[{rule.id}]" in prompt}
        if prompt_ids != manifest_ids:
            raise AssertionError(f"rule projection drift: prompt={prompt_ids}, validator={manifest_ids}")

    def scan(self, text: str, *, include_pending: bool = True) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for rule in self.rules:
            level = rule.detector.level
            if level == DetectionLevel.deterministic:
                occurrences = self._literal_or_regex_count(rule, text)
                findings.append(RuleFinding(rule_id=rule.id, status="hit" if occurrences else "clear", occurrences=occurrences, blocking=rule.detector.blocking and occurrences > 0))
            elif level == DetectionLevel.statistical:
                occurrences, detail = self._statistical_count(rule, text)
                findings.append(RuleFinding(rule_id=rule.id, status="hit" if occurrences else "clear", occurrences=occurrences, detail=detail, blocking=rule.detector.blocking and occurrences > 0))
            elif include_pending and level == DetectionLevel.semantic:
                findings.append(RuleFinding(rule_id=rule.id, status="pending_semantic", detail="Requires contextual semantic comparison or an LLM judge."))
            elif include_pending:
                findings.append(RuleFinding(rule_id=rule.id, status="manual_review", detail="Explicit human review rule."))
        return findings

    @staticmethod
    def _literal_or_regex_count(rule: NegativeRule, text: str) -> int:
        count = 0
        for pattern in rule.detector.patterns:
            count += len(re.findall(pattern, text)) if rule.detector.type == "regex" else text.count(pattern)
        return max(0, count - rule.detector.max_count) if rule.detector.max_count is not None else count

    @staticmethod
    def _statistical_count(rule: NegativeRule, text: str) -> tuple[int, str]:
        sentences = split_sentences(text)
        if rule.id == "uniform_sentence_shape" and len(sentences) >= 4:
            lengths = [len(sentence) for sentence in sentences]
            mean = statistics.mean(lengths)
            coefficient = statistics.pstdev(lengths) / mean if mean else 0
            return int(coefficient < 0.12), f"sentence-length coefficient of variation={coefficient:.3f}"
        if rule.id == "exclamation_overuse":
            count = text.count("!") + text.count("！")
            threshold = rule.detector.max_count if rule.detector.max_count is not None else 2
            return max(0, count - threshold), f"exclamation count={count}, threshold={threshold}"
        return 0, "No statistical implementation registered; kept non-blocking."
