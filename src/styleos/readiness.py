from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from .models import FeedbackRecord, TraceEvent


def readiness_report(
    feedback: list[FeedbackRecord],
    traces: list[TraceEvent],
    *,
    formal_holdout_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    formal_holdout_counts = formal_holdout_counts or {}
    sources = Counter(record.source_id or "unknown" for record in feedback)
    largest_source_share = max(sources.values(), default=0) / len(feedback) if feedback else 1.0
    trace_dates = {event.timestamp.astimezone(UTC).date() for event in traces}
    trace_window_days = 0
    if trace_dates:
        trace_window_days = (max(trace_dates) - min(trace_dates)).days + 1

    active_packs = {record.pack for record in feedback}
    holdouts_ready = bool(active_packs) and all(
        formal_holdout_counts.get(pack, 0) >= 30 for pack in active_packs
    )
    checks = {
        "paired_feedback_at_least_300": len(feedback) >= 300,
        "single_source_share_at_most_50_percent": bool(feedback)
        and largest_source_share <= 0.5,
        "formal_holdout_at_least_30_per_active_pack": holdouts_ready,
        "trace_window_at_least_30_days": trace_window_days >= 30,
    }
    return {
        "ready": all(checks.values()),
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "metrics": {
            "paired_feedback": len(feedback),
            "active_packs": sorted(active_packs),
            "largest_source_share": round(largest_source_share, 4),
            "formal_holdout_counts": formal_holdout_counts,
            "trace_window_days": trace_window_days,
        },
    }


def require_optimization_ready(report: dict[str, Any]) -> None:
    if not report.get("ready"):
        failed = [name for name, passed in report.get("checks", {}).items() if not passed]
        raise RuntimeError("optimization readiness checks failed: " + ", ".join(failed))
