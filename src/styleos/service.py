from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import unified_diff
from pathlib import Path
from typing import Any

from .feedback import FeedbackStore
from .io import atomic_write, dump_json, dump_yaml, load_yaml, sha256_text
from .ledger import audit_ledger, build_ledger
from .models import (
    AuditReport,
    AuditVerdict,
    ContentLedger,
    FeedbackRecord,
    PackManifest,
    StyleCard,
    TraceEvent,
)
from .pack import PackRepository
from .profiles import ProfileStore, approve_card, distill_draft
from .readiness import readiness_report
from .rules import RuleEngine
from .storage import MetadataStore, VaultObject
from .trace import JsonlTraceSink, TracePolicy
from .writers import RewriteRequest, writer_from_provider


def _repository_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        candidate = Path(explicit)
        if not (candidate / "packs").is_dir():
            raise FileNotFoundError(f"StyleOS Pack repository not found: {candidate}")
        return candidate.resolve()
    if configured := os.getenv("STYLEOS_REPOSITORY_ROOT"):
        candidate = Path(configured)
        if not (candidate / "packs").is_dir():
            raise FileNotFoundError(f"StyleOS Pack repository not found: {candidate}")
        return candidate.resolve()
    candidates = [Path.cwd(), *Path.cwd().parents, Path(__file__).parent]
    for candidate in candidates:
        if (candidate / "packs").is_dir():
            return candidate.resolve()
    raise FileNotFoundError(
        "StyleOS Pack repository not found; run inside the repository or set "
        "STYLEOS_REPOSITORY_ROOT"
    )


@dataclass(frozen=True)
class StyleOSPaths:
    repository: Path
    home: Path

    @classmethod
    def resolve(
        cls,
        *,
        repository: str | Path | None = None,
        home: str | Path | None = None,
    ) -> StyleOSPaths:
        root = _repository_root(repository)
        state_home = Path(home or os.getenv("STYLEOS_HOME") or Path.home() / ".styleos")
        return cls(repository=root, home=state_home.expanduser().resolve())

    @property
    def packs(self) -> Path:
        return self.repository / "packs"

    @property
    def profiles(self) -> Path:
        return self.home / "profiles"

    @property
    def feedback(self) -> Path:
        return self.home / "feedback.jsonl"

    @property
    def traces(self) -> Path:
        return self.home / "traces.jsonl"

    @property
    def metadata(self) -> Path:
        return self.home / "styleos.sqlite3"

    @property
    def runs(self) -> Path:
        return self.home / "runs"


class StyleOSService:
    def __init__(self, paths: StyleOSPaths):
        self.paths = paths
        self.packs = PackRepository(paths.packs)
        self.profiles = ProfileStore(paths.profiles)
        self.feedback = FeedbackStore(paths.feedback)
        self.metadata = MetadataStore(paths.metadata)

    def doctor(self) -> dict[str, Any]:
        lint = self.packs.lint_all()
        errors = {name: issues for name, issues in lint.items() if issues}
        self.paths.home.mkdir(parents=True, exist_ok=True)
        writable = os.access(self.paths.home, os.W_OK)
        checks = {
            "pack_repository_found": bool(self.packs.discover()),
            "packs_valid": not errors,
            "state_home_writable": writable,
        }
        return {
            "ok": all(checks.values()),
            "checks": checks,
            "pack_errors": errors,
            "repository": str(self.paths.repository),
            "home": str(self.paths.home),
        }

    def export_schemas(self, output: str | Path) -> list[Path]:
        target = Path(output)
        models = {
            "content_ledger.schema.json": ContentLedger,
            "pack_manifest.schema.json": PackManifest,
            "style_card.schema.json": StyleCard,
        }
        paths: list[Path] = []
        for filename, model in models.items():
            path = target / filename
            dump_json(model.model_json_schema(), path)
            paths.append(path)
        return paths

    def distill(
        self,
        texts: list[str],
        *,
        profile_id: str,
        track: str,
        channel: str,
        audience: str,
        source_ids: list[str] | None = None,
        output: str | Path | None = None,
    ) -> tuple[StyleCard, Path]:
        card = distill_draft(
            texts,
            profile_id=profile_id,
            track=track,
            channel=channel,
            audience=audience,
            source_ids=source_ids,
        )
        path = Path(output) if output else self.profiles.save(card)
        if output:
            dump_yaml(card, path)
        return card, path

    def approve_profile(
        self,
        profile: str | Path,
        *,
        approved_by: str,
        output: str | Path | None = None,
    ) -> tuple[StyleCard, Path]:
        card = self.profiles.load(profile)
        approved = approve_card(card, approved_by=approved_by)
        path = Path(output) if output else (
            Path(profile) if Path(profile).exists() else self.profiles.path_for(approved.id)
        )
        dump_yaml(approved, path)
        return approved, path

    def rewrite(
        self,
        source_text: str,
        *,
        pack: str,
        mode: str = "balanced",
        provider: str = "offline",
        profile: str | Path | None = None,
        output_root: str | Path | None = None,
        must_keep: list[str] | None = None,
    ) -> tuple[AuditReport, Path]:
        manifest = self.packs.load(pack)
        pack_dir = self.paths.packs / pack
        prompt_target = manifest.targets.get("prompt")
        if not prompt_target or not prompt_target.file:
            raise ValueError(f"Pack {pack} has no executable prompt")
        prompt = (pack_dir / prompt_target.file).read_text(encoding="utf-8")

        card = self.profiles.load(profile) if profile else None
        if pack == "imitate" and (card is None or card.status != "human_approved"):
            raise ValueError("imitate requires a human_approved StyleCard")
        if card:
            prompt += "\n\n【Approved StyleCard】\n" + json.dumps(
                card.model_dump(mode="json"), ensure_ascii=False
            )

        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        trace_id = f"trace_{uuid.uuid4().hex}"
        run_dir = Path(output_root or self.paths.runs) / run_id
        ledger = build_ledger(source_text, must_keep=must_keep)
        trace_sinks = [
            JsonlTraceSink(self.paths.traces, TracePolicy(capture_content=False)),
            JsonlTraceSink(run_dir / "trace.jsonl", TracePolicy(capture_content=False)),
        ]
        started = TraceEvent(trace_id=trace_id, run_id=run_id, stage="rewrite_started")
        for sink in trace_sinks:
            sink.emit(started)

        writer = writer_from_provider(provider)
        output_text = writer.rewrite(
            RewriteRequest(
                source_text=source_text,
                compiled_prompt=prompt,
                ledger=ledger,
                style_card=card,
                mode=mode,
                pack=pack,
            )
        )
        report = audit_ledger(
            ledger,
            source_text,
            output_text,
            run_id=run_id,
            trace_id=trace_id,
        )
        rules_path = self.paths.packs / "global" / "deai.negative.zh.yaml"
        rule_findings = RuleEngine.from_file(rules_path).scan(output_text)
        verdict = report.verdict
        if any(finding.blocking for finding in rule_findings):
            verdict = AuditVerdict.failed
        report = report.model_copy(
            update={"rule_findings": rule_findings, "verdict": verdict}
        )

        diff = "".join(
            unified_diff(
                source_text.splitlines(keepends=True),
                output_text.splitlines(keepends=True),
                fromfile="source.md",
                tofile="final.md",
            )
        )
        atomic_write(run_dir / "final.md", output_text)
        atomic_write(run_dir / "diff.md", diff)
        dump_json(report, run_dir / "audit.json")
        dump_json(ledger, run_dir / "content_ledger.json")
        dump_json(
            {
                "run_id": run_id,
                "trace_id": trace_id,
                "pack": manifest.pack,
                "pack_version": manifest.version,
                "provider": writer.name,
                "source_hash": ledger.source_hash,
                "output_hash": sha256_text(output_text),
                "verdict": report.verdict.value,
            },
            run_dir / "receipt.json",
        )
        completed = TraceEvent(
            trace_id=trace_id,
            run_id=run_id,
            stage="rewrite_completed",
            metadata={"pack": manifest.pack, "verdict": report.verdict.value},
        )
        for sink in trace_sinks:
            sink.emit(completed)
        final_path = run_dir / "final.md"
        self.metadata.register_asset(
            VaultObject(
                namespace="runs",
                object_id=run_id,
                filename="final.md",
                path=final_path,
                content_hash=sha256_text(output_text),
            ),
            metadata={"pack": manifest.pack, "verdict": report.verdict.value},
        )
        self.metadata.enqueue(
            "rewrite_completed",
            {"run_id": run_id, "pack": manifest.pack, "verdict": report.verdict.value},
        )
        return report, run_dir

    def record_feedback(self, record: FeedbackRecord) -> None:
        if record.decision == "edited" and not record.edited_text:
            raise ValueError("edited feedback requires edited_text")
        self.feedback.append(record)

    def readiness(self, *, formal_holdout_counts: dict[str, int] | None = None) -> dict[str, Any]:
        traces: list[TraceEvent] = []
        if self.paths.traces.exists():
            for line_number, line in enumerate(
                self.paths.traces.read_text(encoding="utf-8").splitlines(), 1
            ):
                if not line.strip():
                    continue
                try:
                    traces.append(TraceEvent.model_validate_json(line))
                except Exception as exc:
                    raise ValueError(f"invalid trace event at line {line_number}") from exc
        return readiness_report(
            self.feedback.list(), traces, formal_holdout_counts=formal_holdout_counts
        )


def load_style_card(path: str | Path) -> StyleCard:
    return StyleCard.model_validate(load_yaml(path))
