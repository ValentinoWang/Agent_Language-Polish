from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .models import AuditReport, AuditVerdict


def wilson_interval(successes: int, total: int, *, z: float = 1.96) -> tuple[float, float]:
    if total < 1:
        raise ValueError("total must be positive")
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2))
        / denominator
    )
    return round(max(0.0, centre - margin), 6), round(min(1.0, centre + margin), 6)


def sample_tier(total: int) -> Literal["smoke", "phase", "formal_holdout"]:
    if total < 1:
        raise ValueError("sample count must be positive")
    if total < 30:
        return "smoke"
    if total < 100:
        return "phase"
    return "formal_holdout"


@dataclass(frozen=True)
class AuditEvaluation:
    total: int
    passed: int
    review_required: int
    failed: int
    pass_rate: float
    pass_rate_interval: tuple[float, float]
    tier: str


def evaluate_audits(reports: list[AuditReport]) -> AuditEvaluation:
    if not reports:
        raise ValueError("at least one audit report is required")
    passed = sum(report.verdict == AuditVerdict.passed for report in reports)
    review = sum(report.verdict == AuditVerdict.review_required for report in reports)
    failed = sum(report.verdict == AuditVerdict.failed for report in reports)
    return AuditEvaluation(
        total=len(reports),
        passed=passed,
        review_required=review,
        failed=failed,
        pass_rate=round(passed / len(reports), 6),
        pass_rate_interval=wilson_interval(passed, len(reports)),
        tier=sample_tier(len(reports)),
    )


def evidence_graph_ready(*, evaluated_cases: int, baseline_failures: int) -> bool:
    if evaluated_cases < 0 or baseline_failures < 0 or baseline_failures > evaluated_cases:
        raise ValueError("invalid evidence graph counts")
    return evaluated_cases >= 20 and baseline_failures / evaluated_cases >= 0.2


def fine_tuning_ready(
    *, paired_examples: int, dspy_plateau_confirmed: bool, holdout_regressions: int
) -> bool:
    if paired_examples < 0 or holdout_regressions < 0:
        raise ValueError("readiness counts must not be negative")
    return paired_examples >= 2000 and dspy_plateau_confirmed and holdout_regressions == 0
