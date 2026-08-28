from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .models import FeedbackRecord
from .service import StyleOSPaths, StyleOSService

app = typer.Typer(no_args_is_help=True, help="Auditable style compiler")
pack_app = typer.Typer(no_args_is_help=True, help="Validate and compile Packs")
profile_app = typer.Typer(no_args_is_help=True, help="Manage StyleCards")
app.add_typer(pack_app, name="pack")
app.add_typer(profile_app, name="profile")


def _service() -> StyleOSService:
    return StyleOSService(StyleOSPaths.resolve())


def _print(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _fail(message: str, *, code: int = 1) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code)


@app.command()
def doctor() -> None:
    """Check Pack contracts and the local state directory."""
    report = _service().doctor()
    _print(report)
    if not report["ok"]:
        raise typer.Exit(1)


@pack_app.command("lint")
def pack_lint(pack: Annotated[str | None, typer.Argument()] = None) -> None:
    """Validate one Pack or every discovered Pack."""
    repository = _service().packs
    results = {pack: repository.lint(pack)} if pack else repository.lint_all()
    _print(results)
    if any(results.values()):
        raise typer.Exit(1)


@pack_app.command("build")
def pack_build(
    output: Annotated[Path, typer.Option("--output", help="Generated Skill root")] = Path(
        ".claude/skills"
    ),
    pack: Annotated[str | None, typer.Option("--pack")] = None,
) -> None:
    """Compile Pack sources into Codex/Claude Skill files."""
    repository = _service().packs
    try:
        paths = [repository.build_skill(pack, output)] if pack else repository.build_all_skills(output)
    except (FileNotFoundError, ValueError) as exc:
        _fail(str(exc))
    _print({"built": [str(path) for path in paths]})


@app.command("schema-export")
def schema_export(
    output: Annotated[Path, typer.Option("--output")] = Path("generated/schemas"),
) -> None:
    """Export JSON Schema from the authoritative Pydantic models."""
    paths = _service().export_schemas(output)
    _print({"generated": [str(path) for path in paths]})


@app.command()
def distill(
    corpus: Annotated[list[Path], typer.Argument(help="Two or more UTF-8 text files")],
    profile_id: Annotated[str, typer.Option("--profile-id")],
    track: Annotated[str, typer.Option("--track")],
    channel: Annotated[str, typer.Option("--channel")],
    audience: Annotated[str, typer.Option("--audience")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Create an evidence-bearing draft StyleCard from local corpus files."""
    try:
        texts = [path.read_text(encoding="utf-8") for path in corpus]
        card, path = _service().distill(
            texts,
            profile_id=profile_id,
            track=track,
            channel=channel,
            audience=audience,
            source_ids=[path.name for path in corpus],
            output=output,
        )
    except (OSError, ValueError) as exc:
        _fail(str(exc))
    _print({"profile_id": card.id, "status": card.status, "output": str(path)})


@profile_app.command("approve")
def profile_approve(
    profile: Annotated[str, typer.Argument(help="StyleCard id or YAML path")],
    approved_by: Annotated[str, typer.Option("--approved-by")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Record explicit human approval for a draft StyleCard."""
    try:
        card, path = _service().approve_profile(
            profile, approved_by=approved_by, output=output
        )
    except (FileNotFoundError, ValueError) as exc:
        _fail(str(exc))
    _print({"profile_id": card.id, "status": card.status, "output": str(path)})


@app.command()
def rewrite(
    source: Annotated[Path, typer.Argument(help="UTF-8 source file")],
    pack: Annotated[str, typer.Option("--pack")],
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    mode: Annotated[str, typer.Option("--mode")] = "balanced",
    provider: Annotated[str, typer.Option("--provider")] = "offline",
    output_root: Annotated[Path | None, typer.Option("--output-root")] = None,
    must_keep: Annotated[list[str] | None, typer.Option("--must-keep")] = None,
) -> None:
    """Rewrite a file and persist the ledger, diff, audit, and receipt."""
    try:
        source_text = source.read_text(encoding="utf-8")
        report, run_dir = _service().rewrite(
            source_text,
            pack=pack,
            profile=profile,
            mode=mode,
            provider=provider,
            output_root=output_root,
            must_keep=must_keep,
        )
    except (OSError, ValueError) as exc:
        _fail(str(exc))
    _print({"run_id": report.run_id, "verdict": report.verdict, "output": str(run_dir)})
    if report.verdict.value == "fail":
        raise typer.Exit(2)


@app.command()
def feedback(
    run_id: Annotated[str, typer.Option("--run-id")],
    pack: Annotated[str, typer.Option("--pack")],
    decision: Annotated[str, typer.Option("--decision")],
    profile_id: Annotated[str | None, typer.Option("--profile-id")] = None,
    edited_text: Annotated[str | None, typer.Option("--edited-text")] = None,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    source_id: Annotated[str | None, typer.Option("--source-id")] = None,
) -> None:
    """Append an accept, reject, or edited decision to preference memory."""
    try:
        record = FeedbackRecord(
            run_id=run_id,
            pack=pack,
            profile_id=profile_id,
            decision=decision,
            edited_text=edited_text,
            reason=reason,
            source_id=source_id,
        )
        _service().record_feedback(record)
    except ValueError as exc:
        _fail(str(exc))
    _print({"recorded": True, "run_id": run_id, "decision": decision})


@app.command()
def readiness() -> None:
    """Evaluate evidence gates for data-driven optimization."""
    try:
        report = _service().readiness()
    except ValueError as exc:
        _fail(str(exc))
    _print(report)
    if not report["ready"]:
        raise typer.Exit(1)


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8000,
) -> None:
    """Run the local FastAPI service."""
    import uvicorn

    uvicorn.run("styleos.api:app", host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    app()
