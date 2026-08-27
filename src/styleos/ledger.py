from __future__ import annotations

import re
import uuid
from difflib import SequenceMatcher

from .features import split_sentences
from .io import sha256_text
from .models import AuditReport, AuditVerdict, ContentLedger, HardLocks, LockFinding, SemanticLock

_NUMBER = re.compile(r"(?<![\w.])(?:￥|¥|\$)?-?\d+(?:\.\d+)?(?:%|％|万|亿|元|美元|人民币|年|月|日|秒|分钟|小时|kg|g|km|m|cm|mm|ms|s)?")
_DATE = re.compile(r"(?:19|20)\d{2}(?:[-/.年]\d{1,2})?(?:[-/.月]\d{1,2}日?)?")
_CITATION = re.compile(r"\[[0-9,;\-\s]+\]|\([^()]{0,80}(?:19|20)\d{2}[^()]{0,40}\)")
_EQUATION = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$|\\\(.*?\\\)|\\\[.*?\\\]|\\begin\{equation\}.*?\\end\{equation\}", re.DOTALL)
_QUOTE = re.compile(r"“[^”\n]{1,300}”|\"[^\"\n]{1,300}\"")
_IDENTIFIER = re.compile(r"\b[A-Z][A-Z0-9_-]{1,}\b|\b[a-zA-Z]+(?:_[a-zA-Z0-9]+)+\b")
_CONDITION = re.compile(r"仅|只在|在.{0,30}范围内|前提|条件|假设|不超过|至少|至多")
_CLAIM = re.compile(r"表明|提示|支持|证明|说明|发现|可能|倾向于|普遍|必然")
_CAUSAL = re.compile(r"相关|关联|因果|导致|引起|造成|因此")
_STRENGTH = {"可能": 1, "提示": 1, "倾向于": 1, "支持": 2, "表明": 2, "说明": 2, "发现": 2, "证明": 4, "必然": 4, "普遍": 4}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _strength(text: str) -> int:
    return max((_STRENGTH[token] for token in _STRENGTH if token in text), default=1)


def build_ledger(source_text: str, *, task_type: str = "rewrite", must_keep: list[str] | None = None, claims: list[str] | None = None, conditions: list[str] | None = None, allowed_operations: list[str] | None = None) -> ContentLedger:
    if not source_text.strip():
        raise ValueError("source_text must not be empty")
    must_keep = must_keep or []
    hard = HardLocks(
        entities=_unique(must_keep),
        numbers=_unique(_NUMBER.findall(source_text)),
        units=_unique(re.findall(r"(?<=\d)(?:%|％|万|亿|元|美元|人民币|年|月|日|秒|分钟|小时|kg|g|km|cm|mm|ms|s)", source_text)),
        dates=_unique(_DATE.findall(source_text)),
        citations=_unique(_CITATION.findall(source_text)),
        equations=_unique(_EQUATION.findall(source_text)),
        quotes=_unique(_QUOTE.findall(source_text)),
        identifiers=_unique([*must_keep, *_IDENTIFIER.findall(source_text)]),
    )
    semantic: list[SemanticLock] = []
    for text in claims or []:
        semantic.append(SemanticLock(kind="claim", text=text, strength=_strength(text)))
    for text in conditions or []:
        semantic.append(SemanticLock(kind="condition", text=text, strength=1))
    if not claims and not conditions:
        for sentence in split_sentences(source_text):
            if _CONDITION.search(sentence):
                semantic.append(SemanticLock(kind="condition", text=sentence, strength=1, source_span=sentence))
            elif _CLAIM.search(sentence):
                semantic.append(SemanticLock(kind="claim", text=sentence, strength=_strength(sentence), source_span=sentence))
            if _CAUSAL.search(sentence):
                semantic.append(SemanticLock(kind="causal_link", text=sentence, strength=_strength(sentence), source_span=sentence))
    return ContentLedger(
        ledger_id=f"ledger_{uuid.uuid4().hex[:12]}",
        task_type=task_type,
        source_hash=sha256_text(source_text),
        hard_locks=hard,
        semantic_locks=semantic,
        allowed_operations=allowed_operations or ["replace_wording", "remove_redundancy", "adjust_register"],
        extraction={
            "method": "deterministic_v1",
            "hard_lock_regression_scope": "items successfully extracted into this ledger",
            "semantic_policy": "best-effort comparison; uncertainty blocks automatic pass",
        },
    )


def _best_sentence(source: str, output_sentences: list[str]) -> tuple[str, float]:
    best, ratio = "", 0.0
    for candidate in output_sentences:
        current = SequenceMatcher(None, _normalise(source), _normalise(candidate)).ratio()
        if current > ratio:
            best, ratio = candidate, current
    return best, ratio


def audit_ledger(ledger: ContentLedger, source_text: str, output_text: str, *, run_id: str, trace_id: str) -> AuditReport:
    hard_findings: list[LockFinding] = []
    output_normalised = _normalise(output_text)
    for category, values in ledger.hard_locks.model_dump().items():
        for value in values:
            status = "present" if _normalise(value) in output_normalised else "missing"
            hard_findings.append(LockFinding(category=category, value=value, status=status))
    source_numbers, output_numbers = set(_NUMBER.findall(source_text)), set(_NUMBER.findall(output_text))
    source_identifiers, output_identifiers = set(_IDENTIFIER.findall(source_text)), set(_IDENTIFIER.findall(output_text))
    new_hard_facts = sorted((output_numbers - source_numbers) | (output_identifiers - source_identifiers))
    for value in new_hard_facts:
        hard_findings.append(LockFinding(category="new_hard_fact", value=value, status="added"))

    output_sentences = split_sentences(output_text)
    semantic_findings: list[LockFinding] = []
    uncertainty: list[str] = []
    for lock in ledger.semantic_locks:
        candidate, similarity = _best_sentence(lock.text, output_sentences)
        if similarity < 0.35:
            semantic_findings.append(LockFinding(category=lock.kind, value=lock.text, status="uncertain", detail="No sufficiently similar output sentence; human review required."))
            uncertainty.append(f"{lock.kind}: {lock.text}")
            continue
        if lock.kind == "claim" and _strength(candidate) > lock.strength:
            semantic_findings.append(LockFinding(category=lock.kind, value=lock.text, status="missing", detail=f"Claim strength may have increased in: {candidate}"))
            continue
        if lock.kind == "causal_link":
            source_is_correlation = any(token in lock.text for token in ("相关", "关联"))
            output_is_causal = any(token in candidate for token in ("导致", "引起", "造成"))
            if source_is_correlation and output_is_causal:
                semantic_findings.append(LockFinding(category=lock.kind, value=lock.text, status="missing", detail=f"Correlation may have been upgraded to causation: {candidate}"))
                continue
        semantic_findings.append(LockFinding(category=lock.kind, value=lock.text, status="present", detail=f"Best semantic anchor similarity={similarity:.2f}"))

    hard_failure = any(item.status in {"missing", "added"} for item in hard_findings)
    semantic_failure = any(item.status == "missing" for item in semantic_findings)
    verdict = AuditVerdict.failed if hard_failure or semantic_failure else AuditVerdict.review_required if uncertainty else AuditVerdict.passed
    return AuditReport(run_id=run_id, hard_lock_findings=hard_findings, semantic_findings=semantic_findings, new_hard_facts=new_hard_facts, uncertainty=uncertainty, verdict=verdict, trace_id=trace_id, versions={"ledger": "1.0", "semantic_auditor": "heuristic_v1"})
