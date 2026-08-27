from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeliveryState(StrEnum):
    unavailable = "unavailable"
    buildable = "buildable"
    ready = "ready"


class ValidationState(StrEnum):
    pending = "pending"
    passed = "passed"
    blocked = "blocked"


class MaturityLevel(StrEnum):
    planned = "planned"
    prompt_ready = "prompt_ready"
    pilot_validated = "pilot_validated"
    engine_compiled = "engine_compiled"
    service_ready = "service_ready"
    optimization_ready = "optimization_ready"
    production_validated = "production_validated"


class DetectionLevel(StrEnum):
    deterministic = "deterministic"
    statistical = "statistical"
    semantic = "semantic"
    human = "human"


class AuditVerdict(StrEnum):
    passed = "pass"
    review_required = "review_required"
    failed = "fail"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PackInput(Model):
    slot: str
    type: str
    required: bool = True
    source: str = "user"
    enum: list[str] = Field(default_factory=list)
    description: str = ""


class PackOutput(Model):
    name: str
    format: str
    description: str = ""


class PackTarget(Model):
    file: str | None = None
    tool: str | None = None
    since: str = "v0"


class DeliveryAxis(Model):
    prompt: DeliveryState = DeliveryState.unavailable
    skill: DeliveryState = DeliveryState.unavailable
    cli: DeliveryState = DeliveryState.unavailable
    mcp: DeliveryState = DeliveryState.unavailable
    api: DeliveryState = DeliveryState.unavailable


class ValidationAxis(Model):
    example: ValidationState = ValidationState.pending
    automated_smoke: ValidationState = ValidationState.pending
    formal_blind_test: ValidationState = ValidationState.pending
    real_pilot: ValidationState = ValidationState.pending
    notes: list[str] = Field(default_factory=list)


class CompiledFrom(Model):
    blocks: list[str] = Field(default_factory=list)
    style_cards: list[str] = Field(default_factory=list)
    domain_pack: str | None = None
    negative_cards: list[str] = Field(default_factory=list)


class EvalSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    evaluator_profile: str
    baseline: str
    smoke_set: str | None = None
    formal_set: str | None = None
    gates: dict[str, Any] = Field(default_factory=dict)


class PackManifest(Model):
    pack: str
    name: str
    kind: Literal["writing_module", "utility"]
    version: str
    language: str = "zh-CN"
    owner: str
    description: str
    inputs: list[PackInput] = Field(default_factory=list)
    outputs: list[PackOutput] = Field(default_factory=list)
    targets: dict[str, PackTarget] = Field(default_factory=dict)
    compiled_from: CompiledFrom = Field(default_factory=CompiledFrom)
    delivery: DeliveryAxis = Field(default_factory=DeliveryAxis)
    validation: ValidationAxis = Field(default_factory=ValidationAxis)
    maturity: MaturityLevel = MaturityLevel.planned
    eval: EvalSpec
    changelog: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_delivery_contract(self) -> "PackManifest":
        prompt = self.targets.get("prompt")
        if self.delivery.prompt == DeliveryState.ready and (prompt is None or not prompt.file):
            raise ValueError("delivery.prompt=ready requires targets.prompt.file")
        mature = {
            MaturityLevel.pilot_validated,
            MaturityLevel.engine_compiled,
            MaturityLevel.service_ready,
            MaturityLevel.optimization_ready,
            MaturityLevel.production_validated,
        }
        if self.maturity in mature and self.validation.example != ValidationState.passed:
            raise ValueError("maturity at or above pilot_validated requires a passed example")
        return self


class EvidenceRule(Model):
    rule_id: str
    description: str
    support_count: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    counterexamples: list[str] = Field(default_factory=list)
    status: Literal["draft", "human_approved", "rejected"] = "draft"


class StyleCard(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    version: str = "0.1.0"
    status: Literal["draft", "human_approved", "deprecated"] = "draft"
    approved_by: str | None = None
    inherits: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    voice: dict[str, Any] = Field(default_factory=dict)
    lexicon: dict[str, Any] = Field(default_factory=dict)
    syntax: dict[str, Any] = Field(default_factory=dict)
    rhythm: dict[str, Any] = Field(default_factory=dict)
    paragraph: dict[str, Any] = Field(default_factory=dict)
    logic: dict[str, Any] = Field(default_factory=dict)
    epistemics: dict[str, Any] = Field(default_factory=dict)
    rhetoric: dict[str, Any] = Field(default_factory=dict)
    density: dict[str, Any] = Field(default_factory=dict)
    negative_patterns: list[dict[str, Any]] = Field(default_factory=list)
    exemplars: dict[str, list[dict[str, Any]]] = Field(default_factory=lambda: {"positive": [], "negative": []})
    evidence_rules: list[EvidenceRule] = Field(default_factory=list)
    must_preserve: list[str] = Field(default_factory=lambda: ["numbers", "units", "entities", "equations", "citations", "quotes"])
    quality_gates: dict[str, int | float | str] = Field(default_factory=dict)
    review_queue: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def approval_requires_evidence(self) -> "StyleCard":
        if self.status == "human_approved":
            if not self.approved_by:
                raise ValueError("human_approved StyleCard requires approved_by")
            if not self.evidence_rules:
                raise ValueError("human_approved StyleCard requires evidence_rules")
        return self


class HardLocks(Model):
    entities: list[str] = Field(default_factory=list)
    numbers: list[str] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    equations: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)


class SemanticLock(Model):
    kind: Literal["claim", "condition", "causal_link", "statement_grade"]
    text: str
    strength: int = Field(default=1, ge=0, le=4)
    scope: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    source_span: str | None = None


class ContentLedger(Model):
    ledger_id: str
    task_type: Literal["rewrite", "create", "translate"] = "rewrite"
    source_hash: str
    hard_locks: HardLocks
    semantic_locks: list[SemanticLock] = Field(default_factory=list)
    allowed_operations: list[str] = Field(default_factory=list)
    forbidden_operations: list[str] = Field(default_factory=lambda: ["add_facts", "delete_conditions", "upgrade_claim_strength", "alter_hard_locks"])
    gaps: list[str] = Field(default_factory=list)
    extraction: dict[str, Any] = Field(default_factory=dict)


class RuleDetector(Model):
    level: DetectionLevel
    type: Literal["literal", "regex", "counter", "parser", "llm_judge", "manual"]
    blocking: bool = False
    patterns: list[str] = Field(default_factory=list)
    max_count: int | None = None


class NegativeRule(Model):
    id: str
    name: str
    detect: str
    policy: Literal["remove_when_no_function", "conditional", "forbid", "cap"]
    allow_when: list[str] = Field(default_factory=list)
    reject_when: list[str] = Field(default_factory=list)
    fix_hint: str
    detector: RuleDetector


class LockFinding(Model):
    category: str
    value: str
    status: Literal["present", "missing", "added", "uncertain"]
    detail: str = ""


class RuleFinding(Model):
    rule_id: str
    status: Literal["clear", "hit", "pending_semantic", "manual_review"]
    occurrences: int = 0
    detail: str = ""
    blocking: bool = False


class AuditReport(Model):
    run_id: str
    hard_lock_findings: list[LockFinding] = Field(default_factory=list)
    semantic_findings: list[LockFinding] = Field(default_factory=list)
    rule_findings: list[RuleFinding] = Field(default_factory=list)
    new_hard_facts: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    verdict: AuditVerdict
    trace_id: str
    versions: dict[str, str] = Field(default_factory=dict)


class TraceEvent(Model):
    trace_id: str
    run_id: str
    stage: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    content: str | None = None


class FeedbackRecord(Model):
    run_id: str
    pack: str
    profile_id: str | None = None
    decision: Literal["accept", "reject", "edited"]
    edited_text: str | None = None
    reason: str | None = None
    source_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["AuditReport", "AuditVerdict", "ContentLedger", "DeliveryAxis", "DeliveryState", "DetectionLevel", "EvidenceRule", "FeedbackRecord", "HardLocks", "LockFinding", "MaturityLevel", "NegativeRule", "PackManifest", "RuleFinding", "SemanticLock", "StyleCard", "TraceEvent", "ValidationAxis", "ValidationState"]
