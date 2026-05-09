"""Tests for ``POST /api/lexemes/rerun-by-tag`` handler.

Locked contract:
* ``jobId`` is always ``null`` for the synchronous shape currently shipped
  (the per-interval rerun helpers are synchronous; the field exists so we
  can later upgrade to a job-backed shape without breaking clients).
* ``resolved`` mirrors the ``/api/concepts/by-tag`` shape exactly so a
  caller can render the resolved set immediately.
* ``results`` is one entry per (speaker, conceptId, field). For
  ``field=both`` we run ORTH first then IPA — order is observable.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from app.http.tag_filtered_rerun_handlers import (
    TagFilteredHandlerError,
    build_post_lexemes_rerun_by_tag_response,
)


def _vocab() -> list[dict[str, Any]]:
    return [
        {"id": "t-thesis", "label": "Thesis", "color": "#111111", "concepts": [], "lexemeTargets": []},
    ]


def _record(speaker: str, intervals: list[dict[str, Any]], concept_tags: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "speaker": speaker,
        "concept_tags": concept_tags,
        "tiers": {
            "concept": {"type": "interval", "display_order": 3, "intervals": intervals},
        },
    }


def _seed(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    (annotations_dir / "Saha01.parse.json").write_text(
        json.dumps(
            _record(
                "Saha01",
                intervals=[
                    {"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"},
                    {"start": 3.0, "end": 4.0, "text": "leaf", "concept_id": "c2"},
                ],
                concept_tags={"c1": ["t-thesis"], "c2": ["t-thesis"]},
            )
        ),
        encoding="utf-8",
    )


def _annotation_read_path(tmp_path: Path):
    return lambda speaker: tmp_path / "annotations" / f"{speaker}.parse.json"


def _read_json_any(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_record(payload: Any, speaker: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"speaker": speaker, "tiers": {}, "concept_tags": {}}
    return payload


def _normalize_speaker(value: Any) -> str:
    return str(value or "").strip()


def _stub_per_interval_handler(tier_key: str):
    """Build a stub that mirrors ``build_post_run_<tier>_response``.

    Records the kwargs it was called with on the returned ``calls`` list.
    """
    from http import HTTPStatus as _HTTPStatus

    from app.http.job_observability_handlers import JsonResponseSpec

    calls: list[dict[str, Any]] = []

    def handler(body, **kwargs):
        calls.append({"body": dict(body), "kwargs": kwargs, "tier": tier_key})
        return JsonResponseSpec(
            status=_HTTPStatus.OK,
            payload={tier_key: f"stub-{tier_key}", "interval": {"start": body["start"], "end": body["end"]}, "source": "rerun"},
        )

    return handler, calls


def _build(body: dict[str, Any], tmp_path: Path, *, ortho_handler=None, ipa_handler=None):
    return build_post_lexemes_rerun_by_tag_response(
        body,
        project_root=tmp_path,
        load_tags_vocab=_vocab,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_read_path(tmp_path),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
        resolve_audio_path_for_speaker=lambda speaker: tmp_path / "audio" / "working" / speaker / "working.wav",
        run_ipa_interval=lambda **kwargs: "",
        run_ortho_interval=lambda **kwargs: "",
        build_post_run_ipa_response=ipa_handler if ipa_handler is not None else _stub_per_interval_handler("ipa")[0],
        build_post_run_ortho_response=ortho_handler if ortho_handler is not None else _stub_per_interval_handler("ortho")[0],
        locks_dir=tmp_path / ".parse-locks",
    )


def test_rerun_invokes_ortho_and_ipa_per_concept_for_field_both(tmp_path: Path) -> None:
    _seed(tmp_path)
    ortho_handler, ortho_calls = _stub_per_interval_handler("ortho")
    ipa_handler, ipa_calls = _stub_per_interval_handler("ipa")

    response = _build(
        {
            "speakers": ["Saha01"],
            "tagLabels": ["Thesis"],
            "field": "both",
            "pad": 0.5,
        },
        tmp_path,
        ortho_handler=ortho_handler,
        ipa_handler=ipa_handler,
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["jobId"] is None
    assert response.payload["total"] == 4  # 2 concepts × 2 fields
    assert response.payload["resolved"]["totalConcepts"] == 2
    # ORTH runs before IPA per concept.
    fields = [r["field"] for r in response.payload["results"]]
    assert fields == ["ortho", "ipa", "ortho", "ipa"]
    # Pad is forwarded to the per-interval handlers.
    assert ortho_calls[0]["body"]["pad"] == 0.5
    assert ipa_calls[0]["body"]["pad"] == 0.5
    # conceptId comes through as concept_key on the per-interval body.
    assert {call["body"]["concept_key"] for call in ortho_calls} == {"c1", "c2"}


def test_rerun_field_ipa_only_skips_ortho(tmp_path: Path) -> None:
    _seed(tmp_path)
    ortho_handler, ortho_calls = _stub_per_interval_handler("ortho")
    ipa_handler, ipa_calls = _stub_per_interval_handler("ipa")
    response = _build(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ipa"},
        tmp_path,
        ortho_handler=ortho_handler,
        ipa_handler=ipa_handler,
    )
    assert ortho_calls == []
    assert len(ipa_calls) == 2
    assert response.payload["total"] == 2
    assert all(r["field"] == "ipa" for r in response.payload["results"])


def test_rerun_default_pad_is_0_2(tmp_path: Path) -> None:
    _seed(tmp_path)
    ortho_handler, ortho_calls = _stub_per_interval_handler("ortho")
    _build(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
        tmp_path,
        ortho_handler=ortho_handler,
    )
    assert ortho_calls[0]["body"]["pad"] == 0.2


def test_rerun_invalid_pad_returns_400(tmp_path: Path) -> None:
    _seed(tmp_path)
    with pytest.raises(TagFilteredHandlerError) as exc:
        _build({"speakers": "all", "tagLabels": ["Thesis"], "field": "ipa", "pad": 1.0}, tmp_path)
    assert exc.value.status == HTTPStatus.BAD_REQUEST


def test_rerun_missing_field_returns_400(tmp_path: Path) -> None:
    _seed(tmp_path)
    with pytest.raises(TagFilteredHandlerError) as exc:
        _build({"speakers": "all", "tagLabels": ["Thesis"]}, tmp_path)
    assert exc.value.status == HTTPStatus.BAD_REQUEST


def test_rerun_per_concept_error_does_not_abort_remaining(tmp_path: Path) -> None:
    _seed(tmp_path)
    calls: list[str] = []

    def ortho_handler(body, **kwargs):
        calls.append(body["concept_key"])
        if body["concept_key"] == "c1":
            raise RuntimeError("boom")
        from http import HTTPStatus as _HTTPStatus

        from app.http.job_observability_handlers import JsonResponseSpec

        return JsonResponseSpec(status=_HTTPStatus.OK, payload={"ortho": "ok"})

    response = _build(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
        tmp_path,
        ortho_handler=ortho_handler,
    )
    assert calls == ["c1", "c2"]
    statuses = [r["status"] for r in response.payload["results"]]
    assert statuses == ["error", "ok"]
    assert response.payload["results"][0]["error"] == "boom"
