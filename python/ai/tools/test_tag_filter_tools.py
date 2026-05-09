"""Tests for the tag-filter MCP tools.

These tests pin the tool result shape and the strict 400/409 boundaries
that mirror Lane A (PR #321 fix-up cabc9a9):

* `list_concepts_by_tag` and `rerun_lexemes_by_tag` both reject
  ``match='all'`` when any requested tagLabel is unknown OR ambiguous,
  with a tool-level error message starting
  ``"match='all' requires every tagLabel to resolve to exactly one tag; "``.

* `rerun_lexemes_by_tag` additionally rejects any ambiguous tagLabel
  even under ``match='any'``, with a message starting
  ``"rerun-by-tag refuses to disambiguate; ambiguous tagLabels: "``.
  Silently disambiguating would consume GPU and overwrite annotations
  on a concept set the caller didn't approve.

* `field='both'` runs ortho FIRST then ipa per concept hit (observable
  ordering — the FE depends on it).

* The rerun tool's per-result entries carry an integer ``statusCode``
  matching the per-interval handler's HTTP status when an error
  surfaces — this is the contract Lane A pinned in fix-up cabc9a9.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

# Import chat_tools first to fully populate it before tag_filter_tools
# tries to re-enter via ``from ..chat_tools import ChatToolSpec``. Without
# this ordering, the partial-import shows up at test collection time
# even though the production import order is fine.
import ai.chat_tools  # noqa: F401  (priming import to avoid circular load)

from ai.tools.tag_filter_tools import (
    TAG_FILTER_TOOL_HANDLERS,
    TAG_FILTER_TOOL_NAMES,
    TAG_FILTER_TOOL_SPECS,
    tool_list_concepts_by_tag,
    tool_rerun_lexemes_by_tag,
)


# ----------------------------------------------------------------------
# Workspace fixtures.
#
# We fake just enough of ParseChatTools to satisfy the handlers — they
# only need ``project_root`` and ``tags_path``. Tests run against
# tmp_path; never touch /home/lucas/parse-workspace.
# ----------------------------------------------------------------------


class _FakeTools:
    """Minimal stand-in for ParseChatTools used by the handlers under test."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.tags_path = self.project_root / "parse-tags.json"


def _vocab(*entries: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(entries)


def _seed_tags(tools: _FakeTools, tags: List[Dict[str, Any]]) -> None:
    tools.tags_path.write_text(json.dumps(tags), encoding="utf-8")


def _seed_speaker(
    tools: _FakeTools,
    speaker: str,
    *,
    concept_tags: Dict[str, List[str]],
    intervals: List[Dict[str, Any]],
) -> Path:
    annotations = tools.project_root / "annotations"
    annotations.mkdir(parents=True, exist_ok=True)
    record = {
        "speaker": speaker,
        "concept_tags": concept_tags,
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": intervals,
            }
        },
    }
    path = annotations / "{0}.parse.json".format(speaker)
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _seed_audio(tools: _FakeTools, speaker: str) -> Path:
    audio_dir = tools.project_root / "audio" / "working" / speaker
    audio_dir.mkdir(parents=True, exist_ok=True)
    path = audio_dir / "working.wav"
    path.write_bytes(b"RIFFWAVEfake")
    return path


def _seed_concepts_csv(tools: _FakeTools, ids: List[str]) -> None:
    import csv as _csv

    path = tools.project_root / "concepts.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"],
        )
        writer.writeheader()
        for cid in ids:
            writer.writerow(
                {
                    "id": cid,
                    "concept_en": cid,
                    "source_item": cid,
                    "source_survey": "KLQ",
                    "custom_order": "",
                }
            )


# ----------------------------------------------------------------------
# Spec / wiring sanity.
# ----------------------------------------------------------------------


def test_tag_filter_tool_specs_register_two_canonical_names() -> None:
    assert set(TAG_FILTER_TOOL_NAMES) == {"list_concepts_by_tag", "rerun_lexemes_by_tag"}
    assert set(TAG_FILTER_TOOL_SPECS.keys()) == set(TAG_FILTER_TOOL_NAMES)
    assert set(TAG_FILTER_TOOL_HANDLERS.keys()) == set(TAG_FILTER_TOOL_NAMES)


def test_list_concepts_by_tag_spec_describes_match_modes() -> None:
    spec = TAG_FILTER_TOOL_SPECS["list_concepts_by_tag"]
    description = spec.description.lower()
    # The handoff requires this exact pedagogy text so the LLM picks
    # match=all only when intersection semantics are wanted.
    assert "any = the union" in description
    assert "all = the intersection" in description
    properties = spec.parameters.get("properties") or {}
    assert "speakers" in properties
    assert "tagLabels" in properties
    assert "match" in properties


def test_rerun_lexemes_by_tag_spec_requires_field() -> None:
    spec = TAG_FILTER_TOOL_SPECS["rerun_lexemes_by_tag"]
    required = set(spec.parameters.get("required") or [])
    assert {"speakers", "tagLabels", "field"}.issubset(required)
    properties = spec.parameters.get("properties") or {}
    field_enum = (properties.get("field") or {}).get("enum")
    assert set(field_enum or []) == {"ipa", "ortho", "both"}
    pad_enum = (properties.get("pad") or {}).get("enum")
    assert set(pad_enum or []) == {0.0, 0.2, 0.5}


# ----------------------------------------------------------------------
# list_concepts_by_tag — happy paths.
# ----------------------------------------------------------------------


def _make_tools(tmp_path: Path) -> _FakeTools:
    tools = _FakeTools(tmp_path)
    _seed_tags(
        tools,
        _vocab(
            {"id": "t-thesis", "label": "Thesis", "color": "#111111"},
            {"id": "t-list", "label": "WordList", "color": "#222222"},
        ),
    )
    return tools


def test_list_concepts_any_match_returns_per_speaker_payload(tmp_path: Path) -> None:
    tools = _make_tools(tmp_path)
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"], "c2": ["t-thesis", "t-list"]},
        intervals=[
            {"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"},
            {"start": 3.0, "end": 4.0, "text": "leaf", "concept_id": "c2"},
        ],
    )
    _seed_speaker(
        tools,
        "Khan02",
        concept_tags={"c3": ["t-list"]},
        intervals=[{"start": 5.0, "end": 6.0, "text": "twig", "concept_id": "c3"}],
    )

    result = tool_list_concepts_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01", "Khan02"], "tagLabels": ["Thesis", "WordList"]},
    )

    assert result["ok"] is True
    assert result["totalConcepts"] == 3
    assert result["unknownTags"] == []
    assert result["ambiguousTags"] == {}
    saha = result["perSpeaker"]["Saha01"]
    khan = result["perSpeaker"]["Khan02"]
    assert saha["conceptCount"] == 2
    assert {hit["conceptId"] for hit in saha["concepts"]} == {"c1", "c2"}
    assert khan["conceptCount"] == 1


def test_list_concepts_all_match_filters_to_intersection(tmp_path: Path) -> None:
    tools = _make_tools(tmp_path)
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"], "c2": ["t-thesis", "t-list"]},
        intervals=[
            {"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"},
            {"start": 3.0, "end": 4.0, "text": "leaf", "concept_id": "c2"},
        ],
    )
    result = tool_list_concepts_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis", "WordList"], "match": "all"},
    )
    assert result["ok"] is True
    assert [hit["conceptId"] for hit in result["perSpeaker"]["Saha01"]["concepts"]] == ["c2"]


def test_list_concepts_speakers_all_expands_to_workspace(tmp_path: Path) -> None:
    tools = _make_tools(tmp_path)
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"}],
    )
    _seed_speaker(
        tools,
        "Khan02",
        concept_tags={},
        intervals=[],
    )
    result = tool_list_concepts_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": "all", "tagLabels": ["Thesis"]},
    )
    assert result["ok"] is True
    assert set(result["perSpeaker"].keys()) == {"Saha01", "Khan02"}


def test_list_concepts_unknown_label_listed_under_match_any(tmp_path: Path) -> None:
    tools = _make_tools(tmp_path)
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"}],
    )
    result = tool_list_concepts_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis", "Mystery"]},
    )
    assert result["ok"] is True
    assert result["unknownTags"] == ["Mystery"]
    assert result["totalConcepts"] == 1


# ----------------------------------------------------------------------
# Strict 400/409 mirror of Lane A's fix-up cabc9a9.
# ----------------------------------------------------------------------


def test_list_concepts_all_match_400s_on_unknown(tmp_path: Path) -> None:
    """Mirrors Lane A 400 message format. If the resolver silently dropped
    an unknown label under match='all', AND semantics would degrade to
    intersection-over-the-resolved-subset, contradicting the caller's
    request.
    """
    tools = _make_tools(tmp_path)
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"}],
    )
    result = tool_list_concepts_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis", "Mystery"], "match": "all"},
    )
    assert result["ok"] is False
    assert result["status"] == int(HTTPStatus.BAD_REQUEST)
    assert "match='all' requires every tagLabel to resolve to exactly one tag" in result["error"]
    assert "Mystery" in result["error"]


def test_list_concepts_all_match_400s_on_ambiguous(tmp_path: Path) -> None:
    tools = _FakeTools(tmp_path)
    _seed_tags(
        tools,
        _vocab(
            {"id": "t1", "label": "Thesis", "color": "#111111"},
            {"id": "t2", "label": "thesis", "color": "#222222"},
            {"id": "t3", "label": "WordList", "color": "#333333"},
        ),
    )
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t1"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"}],
    )
    result = tool_list_concepts_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis", "WordList"], "match": "all"},
    )
    assert result["ok"] is False
    assert result["status"] == int(HTTPStatus.BAD_REQUEST)
    assert "match='all'" in result["error"]
    assert "Thesis" in result["error"]
    assert "t1" in result["error"] and "t2" in result["error"]


# ----------------------------------------------------------------------
# rerun_lexemes_by_tag — strictness, ordering, statusCode.
# ----------------------------------------------------------------------


def _stub_per_interval(tier_key: str) -> Callable[..., Any]:
    """A stub for build_post_run_<tier>_response that records call order."""
    from app.http.job_observability_handlers import JsonResponseSpec

    def runner(body: Dict[str, Any], **kwargs: Any) -> JsonResponseSpec:
        return JsonResponseSpec(
            status=HTTPStatus.OK,
            payload={tier_key: "stub-{0}".format(tier_key), "interval": {"start": body["start"], "end": body["end"]}, "source": "rerun"},
        )

    return runner


def test_rerun_field_both_runs_ortho_then_ipa_per_concept(tmp_path: Path, monkeypatch) -> None:
    tools = _FakeTools(tmp_path)
    _seed_tags(tools, _vocab({"id": "t-thesis", "label": "Thesis", "color": "#111111"}))
    _seed_concepts_csv(tools, ["c1", "c2"])
    _seed_audio(tools, "Saha01")
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"], "c2": ["t-thesis"]},
        intervals=[
            {"start": 1.0, "end": 2.0, "text": "c1", "concept_id": "c1"},
            {"start": 3.0, "end": 4.0, "text": "c2", "concept_id": "c2"},
        ],
    )

    calls: List[str] = []

    def fake_ortho(body, **kwargs):
        calls.append("ortho:" + body["concept_key"])
        return _stub_per_interval("ortho")(body, **kwargs)

    def fake_ipa(body, **kwargs):
        calls.append("ipa:" + body["concept_key"])
        return _stub_per_interval("ipa")(body, **kwargs)

    import ai.tools.tag_filter_tools as module

    monkeypatch.setattr(module, "build_post_run_ortho_response", fake_ortho)
    monkeypatch.setattr(module, "build_post_run_ipa_response", fake_ipa)

    result = tool_rerun_lexemes_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "both", "pad": 0.5},
    )

    assert result["ok"] is True
    assert result["jobId"] is None
    assert result["total"] == 4
    # ORTH runs before IPA per concept — observable contract.
    assert calls == ["ortho:c1", "ipa:c1", "ortho:c2", "ipa:c2"]
    fields = [r["field"] for r in result["results"]]
    assert fields == ["ortho", "ipa", "ortho", "ipa"]


def test_rerun_default_pad_is_0_2(tmp_path: Path, monkeypatch) -> None:
    tools = _FakeTools(tmp_path)
    _seed_tags(tools, _vocab({"id": "t-thesis", "label": "Thesis", "color": "#111111"}))
    _seed_concepts_csv(tools, ["c1"])
    _seed_audio(tools, "Saha01")
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "c1", "concept_id": "c1"}],
    )

    pads_seen: List[float] = []

    def capture(body, **kwargs):
        pads_seen.append(body["pad"])
        return _stub_per_interval("ortho")(body, **kwargs)

    import ai.tools.tag_filter_tools as module

    monkeypatch.setattr(module, "build_post_run_ortho_response", capture)
    monkeypatch.setattr(module, "build_post_run_ipa_response", _stub_per_interval("ipa"))

    tool_rerun_lexemes_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
    )
    assert pads_seen == [0.2]


def test_rerun_409s_on_ambiguous_under_any_match(tmp_path: Path) -> None:
    """Even under match='any', an ambiguous label must 409 — silently
    disambiguating would consume GPU and overwrite annotations on a
    concept set the caller didn't approve. Mirrors Lane A's 409.
    """
    tools = _FakeTools(tmp_path)
    _seed_tags(
        tools,
        _vocab(
            {"id": "t1", "label": "Thesis", "color": "#111111"},
            {"id": "t2", "label": "thesis", "color": "#222222"},
        ),
    )
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t1"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "c1", "concept_id": "c1"}],
    )
    result = tool_rerun_lexemes_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
    )
    assert result["ok"] is False
    assert result["status"] == int(HTTPStatus.CONFLICT)
    assert "rerun-by-tag refuses to disambiguate; ambiguous tagLabels:" in result["error"]
    assert "Thesis" in result["error"]
    assert "t1" in result["error"] and "t2" in result["error"]


def test_rerun_400s_on_all_match_with_unknown(tmp_path: Path) -> None:
    tools = _FakeTools(tmp_path)
    _seed_tags(tools, _vocab({"id": "t-thesis", "label": "Thesis", "color": "#111111"}))
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "c1", "concept_id": "c1"}],
    )
    result = tool_rerun_lexemes_by_tag(
        tools,  # type: ignore[arg-type]
        {
            "speakers": ["Saha01"],
            "tagLabels": ["Thesis", "Mystery"],
            "match": "all",
            "field": "ortho",
        },
    )
    assert result["ok"] is False
    assert result["status"] == int(HTTPStatus.BAD_REQUEST)
    assert "match='all'" in result["error"]
    assert "Mystery" in result["error"]


def test_rerun_per_concept_error_carries_status_code(tmp_path: Path, monkeypatch) -> None:
    """LexemeRerunHandlerError raised by the per-interval handler must
    surface as ``statusCode = int(exc.status)`` on the result entry —
    same contract Lane A pinned in fix-up cabc9a9.
    """
    from app.http.lexeme_rerun_handlers import LexemeRerunHandlerError

    tools = _FakeTools(tmp_path)
    _seed_tags(tools, _vocab({"id": "t-thesis", "label": "Thesis", "color": "#111111"}))
    _seed_concepts_csv(tools, ["c1"])
    _seed_audio(tools, "Saha01")
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "c1", "concept_id": "c1"}],
    )

    def fail_with_404(body, **kwargs):
        raise LexemeRerunHandlerError(HTTPStatus.NOT_FOUND, "concept not found")

    import ai.tools.tag_filter_tools as module

    monkeypatch.setattr(module, "build_post_run_ortho_response", fail_with_404)
    monkeypatch.setattr(module, "build_post_run_ipa_response", _stub_per_interval("ipa"))

    result = tool_rerun_lexemes_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
    )
    assert result["ok"] is True  # batch-level OK; per-concept is per-result
    entry = result["results"][0]
    assert entry["status"] == "error"
    assert entry["statusCode"] == 404
    assert isinstance(entry["statusCode"], int)
    assert entry["error"] == "concept not found"


def test_rerun_per_concept_generic_error_stamps_500(tmp_path: Path, monkeypatch) -> None:
    tools = _FakeTools(tmp_path)
    _seed_tags(tools, _vocab({"id": "t-thesis", "label": "Thesis", "color": "#111111"}))
    _seed_concepts_csv(tools, ["c1"])
    _seed_audio(tools, "Saha01")
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "c1", "concept_id": "c1"}],
    )

    def boom(body, **kwargs):
        raise RuntimeError("gpu died")

    import ai.tools.tag_filter_tools as module

    monkeypatch.setattr(module, "build_post_run_ortho_response", boom)
    monkeypatch.setattr(module, "build_post_run_ipa_response", _stub_per_interval("ipa"))

    result = tool_rerun_lexemes_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
    )
    entry = result["results"][0]
    assert entry["status"] == "error"
    assert entry["statusCode"] == 500
    assert entry["error"] == "gpu died"


def test_rerun_with_empty_tag_labels_is_400(tmp_path: Path) -> None:
    tools = _make_tools(tmp_path)
    result = tool_rerun_lexemes_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": "all", "tagLabels": [], "field": "ortho"},
    )
    assert result["ok"] is False
    assert result["status"] == int(HTTPStatus.BAD_REQUEST)


def test_rerun_with_unknown_speaker_is_404(tmp_path: Path) -> None:
    tools = _make_tools(tmp_path)
    _seed_speaker(
        tools,
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "c1", "concept_id": "c1"}],
    )
    result = tool_rerun_lexemes_by_tag(
        tools,  # type: ignore[arg-type]
        {"speakers": ["GhostSpeaker"], "tagLabels": ["Thesis"], "field": "ortho"},
    )
    assert result["ok"] is False
    assert result["status"] == int(HTTPStatus.NOT_FOUND)


# ----------------------------------------------------------------------
# Integration with ParseChatTools dispatch.
# ----------------------------------------------------------------------


def test_parse_chat_tools_get_all_tool_names_includes_new_tools() -> None:
    from ai.chat_tools import ParseChatTools

    names = set(ParseChatTools.get_all_tool_names())
    assert "list_concepts_by_tag" in names
    assert "rerun_lexemes_by_tag" in names


def test_parse_chat_tools_dispatch_routes_to_handlers(tmp_path: Path) -> None:
    """``execute('list_concepts_by_tag', args)`` must dispatch to the
    new handler. We seed a minimal workspace so the handler returns a
    real payload rather than erroring out.
    """
    from ai.chat_tools import ParseChatTools

    tools = ParseChatTools(project_root=tmp_path)
    _seed_tags(
        tools,  # type: ignore[arg-type]
        _vocab({"id": "t-thesis", "label": "Thesis", "color": "#111111"}),
    )
    _seed_speaker(
        tools,  # type: ignore[arg-type]
        "Saha01",
        concept_tags={"c1": ["t-thesis"]},
        intervals=[{"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"}],
    )

    response = tools.execute("list_concepts_by_tag", {"speakers": ["Saha01"], "tagLabels": ["Thesis"]})
    assert response["ok"] is True
    assert response["tool"] == "list_concepts_by_tag"
    payload = response["result"]
    assert payload["ok"] is True
    assert payload["totalConcepts"] == 1
