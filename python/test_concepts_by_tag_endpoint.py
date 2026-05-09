"""Tests for ``POST /api/concepts/by-tag`` handler.

The contract is documented in the PR description. Two stable points the
two sister lanes (FE modal + MCP wrappers) consume:

* ``perSpeaker`` ALWAYS includes every requested speaker, even when its
  ``conceptCount`` is 0. This keeps the response shape symmetric and lets
  the FE render "no matches" rows without the caller having to pre-zero.
* ``ambiguousTags`` and ``unknownTags`` are always present (possibly
  empty); each label is reported in only one bucket.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Sequence

import pytest

from app.http.tag_filtered_rerun_handlers import (
    TagFilteredHandlerError,
    build_post_concepts_by_tag_response,
)


def _vocab() -> list[dict[str, Any]]:
    return [
        {"id": "t-thesis", "label": "Thesis", "color": "#111111", "concepts": [], "lexemeTargets": []},
        {"id": "t-list", "label": "WordList", "color": "#222222", "concepts": [], "lexemeTargets": []},
    ]


def _record(speaker: str, *, concept_tags: dict[str, list[str]] | None, intervals: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "speaker": speaker,
        "concept_tags": concept_tags or {},
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": intervals,
            },
        },
    }


def _seed_workspace(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    (annotations_dir / "Saha01.parse.json").write_text(
        json.dumps(
            _record(
                "Saha01",
                concept_tags={"c1": ["t-thesis"], "c2": ["t-thesis", "t-list"]},
                intervals=[
                    {"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"},
                    {"start": 3.0, "end": 4.0, "text": "leaf", "concept_id": "c2"},
                ],
            )
        ),
        encoding="utf-8",
    )
    (annotations_dir / "Saha02.parse.json").write_text(
        json.dumps(
            _record(
                "Saha02",
                concept_tags={"c3": ["t-list"]},
                intervals=[
                    {"start": 5.0, "end": 6.0, "text": "twig", "concept_id": "c3"},
                ],
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


def _build(body: dict[str, Any], tmp_path: Path, *, vocab: Sequence[dict[str, Any]] | None = None):
    return build_post_concepts_by_tag_response(
        body,
        project_root=tmp_path,
        load_tags_vocab=lambda: list(vocab if vocab is not None else _vocab()),
        annotation_read_path_for_speaker=_annotation_read_path(tmp_path),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
    )


def test_any_match_returns_concepts_for_each_speaker(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    response = _build(
        {"speakers": ["Saha01", "Saha02"], "tagLabels": ["Thesis", "WordList"]},
        tmp_path,
    )
    assert response.status == HTTPStatus.OK
    assert response.payload["totalConcepts"] == 3
    saha01 = response.payload["perSpeaker"]["Saha01"]
    assert saha01["conceptCount"] == 2
    assert [hit["conceptId"] for hit in saha01["concepts"]] == ["c1", "c2"]
    assert sorted(saha01["concepts"][1]["tags"]) == ["Thesis", "WordList"]
    saha02 = response.payload["perSpeaker"]["Saha02"]
    assert saha02["conceptCount"] == 1
    assert saha02["concepts"][0]["conceptId"] == "c3"


def test_all_match_filters_to_intersection(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    response = _build(
        {"speakers": ["Saha01", "Saha02"], "tagLabels": ["Thesis", "WordList"], "match": "all"},
        tmp_path,
    )
    assert response.payload["totalConcepts"] == 1
    assert response.payload["perSpeaker"]["Saha01"]["conceptCount"] == 1
    assert response.payload["perSpeaker"]["Saha01"]["concepts"][0]["conceptId"] == "c2"
    # Empty speaker entry MUST still be present with conceptCount=0 so the
    # FE can render a "no matches" row.
    assert response.payload["perSpeaker"]["Saha02"] == {"conceptCount": 0, "concepts": []}


def test_default_match_is_any(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    response = _build(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis", "WordList"]},
        tmp_path,
    )
    assert response.payload["totalConcepts"] == 2


def test_speakers_all_expands_to_workspace(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    response = _build(
        {"speakers": "all", "tagLabels": ["Thesis"]},
        tmp_path,
    )
    assert set(response.payload["perSpeaker"].keys()) == {"Saha01", "Saha02"}


def test_unknown_tag_label_is_listed_without_failing(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    response = _build(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis", "Mystery"]},
        tmp_path,
    )
    assert response.payload["unknownTags"] == ["Mystery"]
    assert response.payload["ambiguousTags"] == {}
    # Known tag still resolves and concepts come back.
    assert response.payload["perSpeaker"]["Saha01"]["conceptCount"] == 2


def test_ambiguous_tag_label_is_listed_separately(tmp_path: Path) -> None:
    vocab = [
        {"id": "t1", "label": "Thesis", "color": "#111111", "concepts": [], "lexemeTargets": []},
        {"id": "t2", "label": "thesis", "color": "#222222", "concepts": [], "lexemeTargets": []},
        {"id": "t3", "label": "WordList", "color": "#333333", "concepts": [], "lexemeTargets": []},
    ]
    _seed_workspace(tmp_path)
    response = _build(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis", "WordList"]},
        tmp_path,
        vocab=vocab,
    )
    assert response.payload["ambiguousTags"] == {"Thesis": ["t1", "t2"]}
    assert response.payload["unknownTags"] == []


def test_empty_tag_labels_returns_400(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    with pytest.raises(TagFilteredHandlerError) as exc:
        _build({"speakers": "all", "tagLabels": []}, tmp_path)
    assert exc.value.status == HTTPStatus.BAD_REQUEST


def test_invalid_match_returns_400(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    with pytest.raises(TagFilteredHandlerError) as exc:
        _build({"speakers": "all", "tagLabels": ["Thesis"], "match": "either"}, tmp_path)
    assert exc.value.status == HTTPStatus.BAD_REQUEST


def test_unknown_speaker_in_list_returns_404(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    with pytest.raises(TagFilteredHandlerError) as exc:
        _build({"speakers": ["Saha01", "GhostSpeaker"], "tagLabels": ["Thesis"]}, tmp_path)
    assert exc.value.status == HTTPStatus.NOT_FOUND
    assert "GhostSpeaker" in exc.value.message


def test_unknown_speaker_when_speakers_all_does_not_404(tmp_path: Path) -> None:
    """`"all"` resolves only to extant annotation files, so unknown-speaker
    can never trigger 404 in this branch."""
    _seed_workspace(tmp_path)
    response = _build({"speakers": "all", "tagLabels": ["Thesis"]}, tmp_path)
    assert response.status == HTTPStatus.OK


def test_concepts_by_tag_all_match_400s_on_unknown_label(tmp_path: Path) -> None:
    """match='all' must 400 if any requested label is unknown; the resolver
    silently dropping it would degrade AND semantics into intersection-over-
    the-resolved-subset and contradict the caller's request.
    """
    _seed_workspace(tmp_path)
    with pytest.raises(TagFilteredHandlerError) as exc:
        _build(
            {"speakers": ["Saha01"], "tagLabels": ["Thesis", "Mystery"], "match": "all"},
            tmp_path,
        )
    assert exc.value.status == HTTPStatus.BAD_REQUEST
    assert "match='all'" in exc.value.message
    assert "Mystery" in exc.value.message


def test_concepts_by_tag_all_match_400s_on_ambiguous_label(tmp_path: Path) -> None:
    """match='all' must 400 if any requested label is ambiguous in the vocab."""
    vocab = [
        {"id": "t1", "label": "Thesis", "color": "#111111", "concepts": [], "lexemeTargets": []},
        {"id": "t2", "label": "thesis", "color": "#222222", "concepts": [], "lexemeTargets": []},
        {"id": "t3", "label": "WordList", "color": "#333333", "concepts": [], "lexemeTargets": []},
    ]
    _seed_workspace(tmp_path)
    with pytest.raises(TagFilteredHandlerError) as exc:
        _build(
            {"speakers": ["Saha01"], "tagLabels": ["Thesis", "WordList"], "match": "all"},
            tmp_path,
            vocab=vocab,
        )
    assert exc.value.status == HTTPStatus.BAD_REQUEST
    assert "match='all'" in exc.value.message
    assert "Thesis" in exc.value.message
    assert "t1" in exc.value.message and "t2" in exc.value.message


def test_concepts_by_tag_any_match_keeps_unknown_in_response(tmp_path: Path) -> None:
    """match='any' keeps existing degrade-gracefully behaviour: unknown labels
    surface in unknownTags but the route still returns 200 with the resolved
    subset so the FE can show a warning without blocking.
    """
    _seed_workspace(tmp_path)
    response = _build(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis", "Mystery"], "match": "any"},
        tmp_path,
    )
    assert response.status == HTTPStatus.OK
    assert response.payload["unknownTags"] == ["Mystery"]
    assert response.payload["perSpeaker"]["Saha01"]["conceptCount"] == 2


def test_concepts_by_tag_with_empty_speakers_list_returns_empty(tmp_path: Path) -> None:
    """Documented edge case: empty `speakers` list short-circuits to a 200
    with empty perSpeaker and totalConcepts=0.
    """
    _seed_workspace(tmp_path)
    response = _build({"speakers": [], "tagLabels": ["Thesis"]}, tmp_path)
    assert response.status == HTTPStatus.OK
    assert response.payload["totalConcepts"] == 0
    assert response.payload["perSpeaker"] == {}
