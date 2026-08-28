from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from styleos.api import app
from styleos.cli import app as cli_app
from styleos.mcp_server import create_server
from styleos.models import FeedbackRecord
from styleos.service import StyleOSPaths, StyleOSService


def test_service_vertical_flow(service: StyleOSService, tmp_path: Path) -> None:
    assert service.doctor()["ok"] is True
    schemas = service.export_schemas(tmp_path / "schemas")
    assert {path.name for path in schemas} == {
        "content_ledger.schema.json",
        "pack_manifest.schema.json",
        "style_card.schema.json",
    }

    card, draft_path = service.distill(
        ["请看这个结果。", "请看这个证据。"],
        profile_id="demo",
        track="self_media",
        channel="video",
        audience="general",
    )
    assert draft_path.exists()
    approved, approved_path = service.approve_profile(draft_path, approved_by="reviewer")
    assert approved.status == "human_approved"
    assert approved_path == draft_path

    with pytest.raises(ValueError, match="human_approved"):
        service.rewrite("项目有 12 个样本。", pack="imitate")
    report, run_dir = service.rewrite(
        "值得注意的是，项目在 2026 年有 12 个样本。\n",
        pack="global",
        output_root=tmp_path / "runs",
    )
    assert report.verdict.value == "pass"
    assert {path.name for path in run_dir.iterdir()} == {
        "audit.json",
        "content_ledger.json",
        "diff.md",
        "final.md",
        "receipt.json",
        "trace.jsonl",
    }
    assert json.loads((run_dir / "receipt.json").read_text())["provider"] == "offline-rule-based"
    assert service.metadata.get_asset(report.run_id) is not None
    assert service.metadata.pending()[0]["event_type"] == "rewrite_completed"

    imitate_report, _ = service.rewrite(
        "项目有 12 个样本。", pack="imitate", profile=approved_path, output_root=tmp_path / "runs"
    )
    assert imitate_report.verdict.value == "pass"
    with pytest.raises(ValueError, match="edited_text"):
        service.record_feedback(
            FeedbackRecord(run_id="run", pack="global", decision="edited")
        )
    service.record_feedback(
        FeedbackRecord(run_id="run", pack="global", decision="accept", source_id="source")
    )
    readiness = service.readiness(formal_holdout_counts={"global": 30})
    assert readiness["ready"] is False
    assert readiness["metrics"]["paired_feedback"] == 1


def test_service_rejects_invalid_trace(repository_root: Path, tmp_path: Path) -> None:
    paths = StyleOSPaths.resolve(repository=repository_root, home=tmp_path)
    paths.traces.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        StyleOSService(paths).readiness()


def test_paths_reject_explicit_invalid_repository(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Pack repository"):
        StyleOSPaths.resolve(repository=tmp_path / "missing", home=tmp_path / "state")


def test_cli_contracts(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("STYLEOS_REPOSITORY_ROOT", str(repository_root))
    monkeypatch.setenv("STYLEOS_HOME", str(state))
    runner = CliRunner()

    assert runner.invoke(cli_app, ["doctor"]).exit_code == 0
    assert runner.invoke(cli_app, ["pack", "lint"]).exit_code == 0
    skills = tmp_path / "skills"
    assert runner.invoke(cli_app, ["pack", "build", "--output", str(skills)]).exit_code == 0
    assert (skills / "global/SKILL.md").exists()
    schemas = tmp_path / "schemas"
    assert runner.invoke(cli_app, ["schema-export", "--output", str(schemas)]).exit_code == 0

    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("请看结果。", encoding="utf-8")
    second.write_text("请看证据。", encoding="utf-8")
    distill = runner.invoke(
        cli_app,
        [
            "distill",
            str(first),
            str(second),
            "--profile-id",
            "cli-demo",
            "--track",
            "self_media",
            "--channel",
            "video",
            "--audience",
            "general",
        ],
    )
    assert distill.exit_code == 0, distill.output
    profile_path = state / "profiles/cli-demo.style_card.yaml"
    assert runner.invoke(
        cli_app,
        ["profile", "approve", str(profile_path), "--approved-by", "reviewer"],
    ).exit_code == 0

    source = tmp_path / "source.md"
    source.write_text("值得注意的是，样本为 12 个。", encoding="utf-8")
    rewrite = runner.invoke(cli_app, ["rewrite", str(source), "--pack", "global"])
    assert rewrite.exit_code == 0, rewrite.output
    assert runner.invoke(
        cli_app,
        ["feedback", "--run-id", "run", "--pack", "global", "--decision", "accept"],
    ).exit_code == 0
    assert runner.invoke(cli_app, ["readiness"]).exit_code == 1


def test_api_contracts(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STYLEOS_REPOSITORY_ROOT", str(repository_root))
    monkeypatch.setenv("STYLEOS_HOME", str(tmp_path / "api-state"))
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    distilled = client.post(
        "/distill",
        json={
            "texts": ["请看结果。", "请看证据。"],
            "profile_id": "api-demo",
            "track": "self_media",
            "channel": "video",
            "audience": "general",
        },
    )
    assert distilled.status_code == 200
    approved = client.post(
        "/profiles/approve",
        json={"card": distilled.json()["card"], "approved_by": "reviewer"},
    )
    assert approved.status_code == 200
    assert client.get("/profiles/api-demo").status_code == 200
    rewritten = client.post(
        "/rewrite",
        json={"source_text": "值得注意的是，样本为 12 个。", "pack": "global"},
    )
    assert rewritten.status_code == 200
    invalid = client.post(
        "/feedback",
        json={"run_id": "run", "pack": "global", "decision": "edited"},
    )
    assert invalid.status_code == 422
    accepted = client.post(
        "/feedback",
        json={"run_id": "run", "pack": "global", "decision": "accept", "source_id": "a"},
    )
    assert accepted.status_code == 201
    assert client.get("/readiness").json()["ready"] is False


def test_mcp_registers_declared_tools(service: StyleOSService) -> None:
    import anyio

    server = create_server(service)
    tools = anyio.run(server.list_tools)
    assert {tool.name for tool in tools} == {
        "style_distill",
        "style_feedback",
        "style_profile_get",
        "style_rewrite",
    }
