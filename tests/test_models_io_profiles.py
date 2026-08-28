from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from styleos.io import atomic_write, dump_json, dump_yaml, load_yaml, sha256_text
from styleos.models import EvidenceRule, StyleCard
from styleos.profiles import ProfileStore, approve_card, distill_draft


def _draft(profile_id: str, *, inherits: list[str] | None = None) -> StyleCard:
    return StyleCard(
        id=profile_id,
        inherits=inherits or [],
        evidence_rules=[
            EvidenceRule(
                rule_id="syntax.length",
                description="measured",
                support_count=2,
                confidence=0.8,
                evidence_ids=["a", "b"],
            )
        ],
    )


def test_style_card_approval_invariants() -> None:
    with pytest.raises(ValidationError, match="approved_by"):
        StyleCard(id="bad", status="human_approved", evidence_rules=[_draft("x").evidence_rules[0]])
    with pytest.raises(ValidationError, match="evidence_rules"):
        StyleCard(id="bad", status="human_approved", approved_by="reviewer")

    approved = approve_card(_draft("good"), approved_by=" reviewer ")
    assert approved.status == "human_approved"
    assert approved.approved_by == "reviewer"
    with pytest.raises(ValueError, match="approved_by"):
        approve_card(_draft("good"), approved_by=" ")
    with pytest.raises(ValueError, match="without evidence"):
        approve_card(StyleCard(id="empty"), approved_by="reviewer")


def test_distill_validates_corpus_and_records_evidence() -> None:
    with pytest.raises(ValueError, match="at least two"):
        distill_draft(["one"], profile_id="p", track="x", channel="y", audience="z")
    with pytest.raises(ValueError, match="must not be empty"):
        distill_draft(["one", " "], profile_id="p", track="x", channel="y", audience="z")
    with pytest.raises(ValueError, match="source_ids"):
        distill_draft(
            ["one", "two"],
            profile_id="p",
            track="x",
            channel="y",
            audience="z",
            source_ids=["one"],
        )

    card = distill_draft(
        ["请先看结果。结果很清楚。", "请先看证据。证据很清楚。"],
        profile_id="author.channel.v1",
        track="self_media",
        channel="video",
        audience="general",
        source_ids=["a", "b"],
    )
    assert card.status == "draft"
    assert card.meta["raw_corpus_embedded"] is False
    assert card.meta["document_count"] == 2
    assert card.evidence_rules
    assert any("少于三篇" in item for item in card.review_queue)


def test_profile_store_roundtrip_inheritance_and_cycle(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path)
    parent = _draft("parent")
    parent.voice = {"distance": "close"}
    child = _draft("child", inherits=["parent"])
    child.voice = {"authority": "peer"}
    store.save(parent)
    store.save(child)

    effective = store.effective("child")
    assert effective.voice == {"distance": "close", "authority": "peer"}
    assert effective.meta["effective_from"] == "child"
    assert store.load(store.path_for("child")).id == "child"
    with pytest.raises(FileNotFoundError):
        store.load("missing")

    store.save(_draft("a", inherits=["b"]))
    store.save(_draft("b", inherits=["a"]))
    with pytest.raises(ValueError, match="inheritance cycle"):
        store.effective("a")
    assert ".." not in store.path_for("../unsafe").name


def test_atomic_serialization_helpers(tmp_path: Path) -> None:
    text_path = tmp_path / "nested" / "value.txt"
    atomic_write(text_path, "first")
    atomic_write(text_path, "second")
    assert text_path.read_text() == "second"
    assert not list(text_path.parent.glob(".value.txt.*"))

    card = _draft("serialized")
    yaml_path = tmp_path / "card.yaml"
    json_path = tmp_path / "card.json"
    dump_yaml(card, yaml_path)
    dump_json(card, json_path)
    assert load_yaml(yaml_path)["id"] == "serialized"
    assert json.loads(json_path.read_text())["id"] == "serialized"
    assert yaml.safe_load(yaml_path.read_text())["status"] == "draft"
    assert sha256_text("same") == sha256_text("same")
    assert sha256_text("same") != sha256_text("different")
