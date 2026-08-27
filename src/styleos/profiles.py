from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .features import aggregate_features
from .io import dump_yaml, load_yaml
from .models import EvidenceRule, StyleCard


def distill_draft(
    texts: list[str],
    *,
    profile_id: str,
    track: str,
    channel: str,
    audience: str,
    source_ids: list[str] | None = None,
) -> StyleCard:
    if len(texts) < 2:
        raise ValueError("distillation requires at least two texts; formal pilot should use 3-10")
    if any(not text.strip() for text in texts):
        raise ValueError("corpus documents must not be empty")
    source_ids = source_ids or [f"doc_{index + 1}" for index in range(len(texts))]
    if len(source_ids) != len(texts):
        raise ValueError("source_ids length must match texts")
    features = aggregate_features(texts)
    sentence = features["sentence_length"]
    punctuation = features["punctuation"]
    repeated = features["repeated_ngrams"]
    evidence_ids = [f"{source_id}#full" for source_id in source_ids]
    rules = [
        EvidenceRule(
            rule_id="syntax.sentence_length",
            description=(
                f"句长采用 mixed 分布；合并语料 p50={sentence['p50']}，"
                f"p75={sentence['p75']}，max={sentence['max']}。"
            ),
            support_count=len(texts),
            confidence=min(0.95, 0.55 + 0.08 * len(texts)),
            evidence_ids=evidence_ids,
        ),
        EvidenceRule(
            rule_id="rhythm.punctuation",
            description="高频标点为：" + "、".join(f"{mark}×{count}" for mark, count in sorted(punctuation.items(), key=lambda item: item[1], reverse=True)[:5]),
            support_count=len(texts),
            confidence=min(0.9, 0.5 + 0.07 * len(texts)),
            evidence_ids=evidence_ids,
        ),
    ]
    if repeated:
        rules.append(
            EvidenceRule(
                rule_id="lexicon.repeated_ngrams",
                description="候选稳定短语：" + "、".join(item["text"] for item in repeated[:5]),
                support_count=len(texts),
                confidence=0.65,
                evidence_ids=evidence_ids,
            )
        )
    review_queue = [
        "确定性统计只能证明表层模式；人格、逻辑动作、认识立场仍需人工阅读确认。",
        "请排除引用、广告模板和他人代写造成的污染。",
    ]
    if len(texts) < 3:
        review_queue.append("语料少于三篇；只能作为工程冒烟卡，不能直接宣称稳定作者风格。")
    return StyleCard(
        id=profile_id,
        status="draft",
        scope={"track": track, "channels": [channel], "audiences": [audience], "languages": ["zh-CN"]},
        voice={"authority": "unknown", "distance": "unknown", "reader_assumption": audience},
        lexicon={"signature_phrases": repeated[:10], "terminology_density": "unknown"},
        syntax={"sentence_length": "mixed", "sentence_length_dist": sentence, "question_ratio": features["question_ratio"], "imperative_ratio": features["imperative_ratio"]},
        rhythm={"punctuation_habits": punctuation},
        paragraph={"sentence_count": features["paragraph_sentence_count"]},
        logic={"preferred_moves": [], "avoid_moves": ["invented_opposition"]},
        epistemics={"restricted": ["证明", "普遍", "首次发现"], "claim_strength_must_match_evidence": True},
        density={"measured_characters": features["characters"]},
        evidence_rules=rules,
        review_queue=review_queue,
        quality_gates={"unsupported_new_claims": 0, "numeric_drift": 0, "citation_drift": 0},
        meta={"document_count": len(texts), "source_ids": source_ids, "features": features, "raw_corpus_embedded": False, "distiller": "deterministic_v1"},
    )


def approve_card(card: StyleCard, *, approved_by: str) -> StyleCard:
    if not approved_by.strip():
        raise ValueError("approved_by is required")
    if not card.evidence_rules:
        raise ValueError("cannot approve a StyleCard without evidence rules")
    payload = card.model_dump(mode="python")
    payload["status"] = "human_approved"
    payload["approved_by"] = approved_by.strip()
    payload.setdefault("meta", {})["approval_note"] = "Human approval records acceptance of the explicit rules, not ownership of the raw corpus."
    return StyleCard.model_validate(payload)


def _overlay(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        result = deepcopy(base)
        for key, value in override.items():
            result[key] = _overlay(result[key], value) if key in result else deepcopy(value)
        return result
    return deepcopy(override)


class ProfileStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, profile_id: str) -> Path:
        safe = profile_id.replace("/", "_").replace("..", "_")
        return self.root / f"{safe}.style_card.yaml"

    def save(self, card: StyleCard) -> Path:
        path = self.path_for(card.id)
        dump_yaml(card, path)
        return path

    def load(self, profile_id_or_path: str | Path) -> StyleCard:
        candidate = Path(profile_id_or_path)
        path = candidate if candidate.exists() else self.path_for(str(profile_id_or_path))
        if not path.exists():
            raise FileNotFoundError(f"StyleCard not found: {profile_id_or_path}")
        return StyleCard.model_validate(load_yaml(path))

    def effective(self, profile_id: str) -> StyleCard:
        cache: dict[str, dict[str, Any]] = {}

        def resolve(current_id: str, stack: tuple[str, ...]) -> dict[str, Any]:
            if current_id in stack:
                raise ValueError("StyleCard inheritance cycle: " + " -> ".join((*stack, current_id)))
            if current_id in cache:
                return deepcopy(cache[current_id])
            card = self.load(current_id)
            merged: dict[str, Any] = {}
            for parent_id in card.inherits:
                merged = _overlay(merged, resolve(parent_id, (*stack, current_id)))
            merged = _overlay(merged, card.model_dump(mode="python"))
            cache[current_id] = merged
            return deepcopy(merged)

        effective = StyleCard.model_validate(resolve(profile_id, ()))
        effective.meta = {**effective.meta, "effective_from": profile_id}
        return effective
