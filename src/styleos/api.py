from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .models import FeedbackRecord, StyleCard
from .service import StyleOSPaths, StyleOSService


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DistillBody(RequestModel):
    texts: list[str] = Field(min_length=2)
    profile_id: str
    track: str
    channel: str
    audience: str
    source_ids: list[str] | None = None


class ApproveBody(RequestModel):
    card: StyleCard
    approved_by: str


class RewriteBody(RequestModel):
    source_text: str = Field(min_length=1)
    pack: str
    mode: str = "balanced"
    provider: Literal["offline", "openai", "openai-compatible", "anthropic"] = "offline"
    profile: str | None = None
    must_keep: list[str] = Field(default_factory=list)


def get_service() -> StyleOSService:
    return StyleOSService(StyleOSPaths.resolve())


app = FastAPI(title="StyleOS", version="0.3.0rc1")


@app.get("/health")
def health() -> dict[str, object]:
    report = get_service().doctor()
    if not report["ok"]:
        raise HTTPException(status_code=503, detail=report)
    return {"status": "ok", "checks": report["checks"]}


@app.get("/readiness")
def readiness() -> dict[str, object]:
    return get_service().readiness()


@app.post("/distill")
def distill(body: DistillBody) -> dict[str, object]:
    try:
        card, path = get_service().distill(
            body.texts,
            profile_id=body.profile_id,
            track=body.track,
            channel=body.channel,
            audience=body.audience,
            source_ids=body.source_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"card": card.model_dump(mode="json"), "path": str(path)}


@app.post("/profiles/approve")
def approve(body: ApproveBody) -> dict[str, object]:
    service = get_service()
    draft_path = service.profiles.save(body.card)
    try:
        card, path = service.approve_profile(draft_path, approved_by=body.approved_by)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"card": card.model_dump(mode="json"), "path": str(path)}


@app.get("/profiles/{profile_id}")
def profile_get(profile_id: str) -> dict[str, object]:
    try:
        card = get_service().profiles.effective(profile_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return card.model_dump(mode="json")


@app.post("/rewrite")
def rewrite(body: RewriteBody) -> dict[str, object]:
    try:
        report, run_dir = get_service().rewrite(
            body.source_text,
            pack=body.pack,
            mode=body.mode,
            provider=body.provider,
            profile=body.profile,
            must_keep=body.must_keep,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"audit": report.model_dump(mode="json"), "run_dir": str(run_dir)}


@app.post("/feedback", status_code=201)
def feedback(record: FeedbackRecord) -> dict[str, object]:
    try:
        get_service().record_feedback(record)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": True, "run_id": record.run_id}
