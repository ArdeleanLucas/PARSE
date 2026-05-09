"""Tests for ``POST /api/lexemes/rerun-by-tag`` handler.

Locked contract:
* Default requests return ``202`` + non-null ``jobId`` and launch the
  ``lexemes_rerun_by_tag`` compute job.
* ``async: false`` preserves the deprecated synchronous ``200`` shape with
  ``jobId: null`` for old integrations.
* The completed job result preserves the old ``resolved``/``total``/``results``
  shape so the batch-report modal can render it after polling.
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


def test_rerun_default_starts_compute_job_without_running_handlers(tmp_path: Path) -> None:
    _seed(tmp_path)
    launched: list[tuple[str, str, dict[str, Any]]] = []
    created: list[tuple[str, dict[str, Any]]] = []

    def create_job(job_type: str, metadata: dict[str, Any]) -> str:
        created.append((job_type, metadata))
        return "job-tagged-1"

    def launch(job_id: str, compute_type: str, payload: dict[str, Any]) -> None:
        launched.append((job_id, compute_type, payload))

    def fail_handler(*args, **kwargs):  # pragma: no cover - must not run before job start
        raise AssertionError("default async path must not run per-interval handlers")

    response = build_post_lexemes_rerun_by_tag_response(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
        project_root=tmp_path,
        load_tags_vocab=_vocab,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_read_path(tmp_path),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
        resolve_audio_path_for_speaker=lambda speaker: tmp_path / "audio" / "working" / speaker / "working.wav",
        run_ipa_interval=lambda **kwargs: "",
        run_ortho_interval=lambda **kwargs: "",
        build_post_run_ipa_response=fail_handler,
        build_post_run_ortho_response=fail_handler,
        locks_dir=tmp_path / ".parse-locks",
        create_job=create_job,
        launch_compute_runner=launch,
    )

    assert response.status == HTTPStatus.ACCEPTED
    assert response.payload == {"jobId": "job-tagged-1"}
    assert created == [(
        "compute:lexemes_rerun_by_tag",
        {
            "computeType": "lexemes_rerun_by_tag",
            "speakers": ["Saha01"],
            "speaker": "Saha01",
            "tagLabels": ["Thesis"],
            "match": "any",
            "field": "ortho",
            "totalConcepts": 2,
        },
    )]
    assert launched == [(
        "job-tagged-1",
        "lexemes_rerun_by_tag",
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
    )]


def test_rerun_default_maps_job_lock_conflict_to_409(tmp_path: Path) -> None:
    _seed(tmp_path)

    class FakeConflict(RuntimeError):
        pass

    def create_job(job_type: str, metadata: dict[str, Any]) -> str:
        raise FakeConflict("speaker is already locked")

    with pytest.raises(TagFilteredHandlerError) as exc:
        build_post_lexemes_rerun_by_tag_response(
            {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"},
            project_root=tmp_path,
            load_tags_vocab=_vocab,
            normalize_speaker_id=_normalize_speaker,
            annotation_read_path_for_speaker=_annotation_read_path(tmp_path),
            read_json_any_file=_read_json_any,
            normalize_annotation_record=_normalize_record,
            resolve_audio_path_for_speaker=lambda speaker: tmp_path / "audio" / "working" / speaker / "working.wav",
            run_ipa_interval=lambda **kwargs: "",
            run_ortho_interval=lambda **kwargs: "",
            build_post_run_ipa_response=_stub_per_interval_handler("ipa")[0],
            build_post_run_ortho_response=_stub_per_interval_handler("ortho")[0],
            locks_dir=tmp_path / ".parse-locks",
            create_job=create_job,
            launch_compute_runner=lambda *args, **kwargs: None,
            job_conflict_error_cls=FakeConflict,
        )

    assert exc.value.status == HTTPStatus.CONFLICT
    assert "already locked" in exc.value.message


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
            "async": False,
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
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ipa", "async": False},
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
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho", "async": False},
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
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho", "async": False},
        tmp_path,
        ortho_handler=ortho_handler,
    )
    assert calls == ["c1", "c2"]
    statuses = [r["status"] for r in response.payload["results"]]
    assert statuses == ["error", "ok"]
    assert response.payload["results"][0]["error"] == "boom"
    # Generic exceptions stamp 500 so the caller can treat it the same as any
    # other runner failure without parsing strings.
    assert response.payload["results"][0]["statusCode"] == 500
    assert isinstance(response.payload["results"][0]["statusCode"], int)


def test_rerun_per_concept_LexemeRerunHandlerError_preserves_status_code(tmp_path: Path) -> None:
    """A LexemeRerunHandlerError thrown by the per-interval handler must carry
    its HTTP status into the result entry as ``statusCode`` so the caller can
    distinguish 404 (concept not in concepts.csv) from 409 (speaker locked)
    from 500 (runner died).
    """
    from http import HTTPStatus as _HTTPStatus

    from app.http.lexeme_rerun_handlers import LexemeRerunHandlerError

    _seed(tmp_path)

    def ortho_handler(body, **kwargs):
        raise LexemeRerunHandlerError(_HTTPStatus.NOT_FOUND, "concept not found")

    response = _build(
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho", "async": False},
        tmp_path,
        ortho_handler=ortho_handler,
    )
    assert all(r["status"] == "error" for r in response.payload["results"])
    assert all(r["statusCode"] == 404 for r in response.payload["results"])
    assert all(r["error"] == "concept not found" for r in response.payload["results"])


def test_rerun_by_tag_409s_on_ambiguous_tag(tmp_path: Path) -> None:
    """Even under match='any', an ambiguous label must 409 — silently
    disambiguating to a subset would consume GPU and overwrite annotations
    on a concept set the caller didn't approve.
    """
    _seed(tmp_path)
    ambiguous_vocab = [
        {"id": "t1", "label": "Thesis", "color": "#111111", "concepts": [], "lexemeTargets": []},
        {"id": "t2", "label": "thesis", "color": "#222222", "concepts": [], "lexemeTargets": []},
    ]

    def _build_with_vocab(body):
        return build_post_lexemes_rerun_by_tag_response(
            body,
            project_root=tmp_path,
            load_tags_vocab=lambda: list(ambiguous_vocab),
            normalize_speaker_id=_normalize_speaker,
            annotation_read_path_for_speaker=_annotation_read_path(tmp_path),
            read_json_any_file=_read_json_any,
            normalize_annotation_record=_normalize_record,
            resolve_audio_path_for_speaker=lambda speaker: tmp_path / "audio" / "working" / speaker / "working.wav",
            run_ipa_interval=lambda **kwargs: "",
            run_ortho_interval=lambda **kwargs: "",
            build_post_run_ipa_response=_stub_per_interval_handler("ipa")[0],
            build_post_run_ortho_response=_stub_per_interval_handler("ortho")[0],
            locks_dir=tmp_path / ".parse-locks",
        )

    with pytest.raises(TagFilteredHandlerError) as exc:
        _build_with_vocab(
            {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "ortho"}
        )
    assert exc.value.status == HTTPStatus.CONFLICT
    assert "Thesis" in exc.value.message
    assert "t1" in exc.value.message and "t2" in exc.value.message


def test_rerun_by_tag_400s_on_all_match_with_unknown(tmp_path: Path) -> None:
    """match='all' on rerun must 400 before any GPU spend if any requested
    label is unknown.
    """
    _seed(tmp_path)
    with pytest.raises(TagFilteredHandlerError) as exc:
        _build(
            {
                "speakers": ["Saha01"],
                "tagLabels": ["Thesis", "Mystery"],
                "match": "all",
                "field": "ortho",
            },
            tmp_path,
        )
    assert exc.value.status == HTTPStatus.BAD_REQUEST
    assert "match='all'" in exc.value.message
    assert "Mystery" in exc.value.message


def test_rerun_by_tag_with_real_per_interval_handler(tmp_path: Path) -> None:
    """End-to-end style test that wires the REAL
    ``build_post_run_ortho_response`` / ``build_post_run_ipa_response`` from
    ``app.http.lexeme_rerun_handlers`` instead of stubs. The interval runners
    are still stubbed so no GPU is needed, but every other code path
    (concepts.csv lookup, annotation read, speaker lock acquire/release,
    pad-padded interval) is exercised. A regression that broke the
    conceptId-to-concept-key mapping would surface here.
    """
    import csv
    import json as _json

    from app.http.lexeme_rerun_handlers import (
        build_post_run_ipa_response,
        build_post_run_ortho_response,
    )

    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = tmp_path / "audio" / "working" / "Saha01"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / "working.wav"
    audio_path.write_bytes(b"RIFFWAVEfake")

    with (tmp_path / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "concept_en": "hair",
                "source_item": "hair",
                "source_survey": "KLQ",
                "custom_order": "",
            }
        )

    annotation = {
        "project_id": "parse-test",
        "speaker": "Saha01",
        "source_audio": "audio/working/Saha01/working.wav",
        "source_audio_duration_sec": 10.0,
        "concept_tags": {"1": ["t-thesis"]},
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [
                    {"start": 1.0, "end": 2.0, "text": "hair", "concept_id": "1"}
                ],
            },
            "ortho": {
                "type": "interval",
                "display_order": 2,
                "intervals": [{"start": 1.0, "end": 2.0, "text": "old"}],
            },
            "ipa": {
                "type": "interval",
                "display_order": 1,
                "intervals": [{"start": 1.0, "end": 2.0, "text": "old"}],
            },
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
    }
    (annotations_dir / "Saha01.parse.json").write_text(
        _json.dumps(annotation, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )

    response = build_post_lexemes_rerun_by_tag_response(
        {
            "speakers": ["Saha01"],
            "tagLabels": ["Thesis"],
            "field": "both",
            "pad": 0.2,
            "async": False,
        },
        project_root=tmp_path,
        load_tags_vocab=_vocab,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_read_path(tmp_path),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
        resolve_audio_path_for_speaker=lambda speaker: audio_path,
        run_ortho_interval=lambda **kwargs: "ORTHO_RESULT",
        run_ipa_interval=lambda **kwargs: "IPA_RESULT",
        build_post_run_ortho_response=build_post_run_ortho_response,
        build_post_run_ipa_response=build_post_run_ipa_response,
        locks_dir=tmp_path / ".parse-locks",
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["resolved"]["totalConcepts"] == 1
    assert response.payload["total"] == 2
    fields_seen = [(r["field"], r["status"], r.get("text")) for r in response.payload["results"]]
    assert fields_seen == [
        ("ortho", "ok", "ORTHO_RESULT"),
        ("ipa", "ok", "IPA_RESULT"),
    ]


def test_rerun_by_tag_speakers_all_with_real_workspace(tmp_path: Path) -> None:
    """Resolver-level coverage exists; this is a route-level smoke that
    `speakers="all"` enumerates the workspace correctly.
    """
    _seed(tmp_path)
    response = _build(
        {"speakers": "all", "tagLabels": ["Thesis"], "field": "ortho", "async": False},
        tmp_path,
    )
    assert response.status == HTTPStatus.OK
    assert "Saha01" in response.payload["resolved"]["perSpeaker"]
    assert response.payload["resolved"]["perSpeaker"]["Saha01"]["conceptCount"] == 2



def test_compute_lexemes_rerun_by_tag_caches_providers_reports_progress_and_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The tracked job runner loads expensive providers once per job, emits
    monotonic per-concept progress, keeps going after a concept-level failure,
    and unloads/collects after the loop.
    """
    import ai.ipa_transcribe as ipa_transcribe
    import ai.stt_pipeline as stt_pipeline
    import storage.tags_store as tags_store
    from app.http.job_observability_handlers import JsonResponseSpec
    from app.http import lexeme_rerun_handlers
    from server_routes import annotate
    import server_routes.lexeme_rerun as lexeme_rerun_route
    import server_routes.locks as locks_route

    _seed(tmp_path)
    audio_path = tmp_path / "audio" / "working" / "Saha01" / "working.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFF0000WAVE")

    progress: list[tuple[float, str]] = []
    collect_calls: list[str] = []
    provider_instances: list[Any] = []
    aligner_instances: list[Any] = []
    ortho_calls: list[dict[str, Any]] = []
    ipa_calls: list[dict[str, Any]] = []

    class FakeProvider:
        def __init__(self) -> None:
            self.unloaded = False

        def unload_model(self) -> None:
            self.unloaded = True

    class FakeAligner:
        pass

    def fake_ortho_response(body, **kwargs):
        text_value = kwargs["run_ortho_interval"](
            audio_path=audio_path,
            start=float(body["start"]),
            end=float(body["end"]),
            language=None,
        )
        return JsonResponseSpec(status=HTTPStatus.OK, payload={"ortho": text_value})

    def fake_ipa_response(body, **kwargs):
        text_value = kwargs["run_ipa_interval"](
            audio_path=audio_path,
            start=float(body["start"]),
            end=float(body["end"]),
            language=None,
        )
        return JsonResponseSpec(status=HTTPStatus.OK, payload={"ipa": text_value})

    def fake_run_ortho_on_interval(**kwargs):
        ortho_calls.append(kwargs)
        # Force a per-concept failure on the first concept only; the shared
        # rerun loop must convert it into a row and continue to c2.
        if len(ortho_calls) == 1:
            raise RuntimeError("orthographic concept failure")
        return "cached-ortho"

    def fake_transcribe_intervals(**kwargs):
        ipa_calls.append(kwargs)
        return [{"ipa": "cached-ipa"}]

    monkeypatch.setattr(tags_store, "fetch_all", lambda: {"tags": _vocab()})
    monkeypatch.setattr(annotate._server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(annotate._server, "_annotation_read_path_for_speaker", _annotation_read_path(tmp_path))
    monkeypatch.setattr(annotate._server, "_read_json_any_file", _read_json_any)
    monkeypatch.setattr(annotate._server, "_normalize_annotation_record", _normalize_record)
    monkeypatch.setattr(annotate._server, "_normalize_speaker_id", _normalize_speaker)
    monkeypatch.setattr(annotate._server, "_pipeline_audio_path_for_speaker", lambda speaker: audio_path)
    monkeypatch.setattr(annotate._server, "_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(annotate._server, "get_ortho_provider", lambda: provider_instances.append(FakeProvider()) or provider_instances[-1])
    monkeypatch.setattr(annotate._server, "_get_ipa_aligner", lambda: aligner_instances.append(FakeAligner()) or aligner_instances[-1])
    monkeypatch.setattr(annotate._server, "_release_ipa_aligner", lambda: aligner_instances.append("released"))
    monkeypatch.setattr(annotate._server, "_collect_after_unload", lambda: collect_calls.append("collect"))
    monkeypatch.setattr(annotate, "_set_compute_progress", lambda job_id, pct, message="", **kwargs: progress.append((float(pct), str(message))))
    monkeypatch.setattr(lexeme_rerun_route, "_wav2vec2_options_with_safe_fallback", lambda: ("cuda", True))
    monkeypatch.setattr(locks_route, "_locks_dir", lambda: tmp_path / ".parse-locks")
    monkeypatch.setattr(lexeme_rerun_handlers, "build_post_run_ortho_response", fake_ortho_response)
    monkeypatch.setattr(lexeme_rerun_handlers, "build_post_run_ipa_response", fake_ipa_response)
    monkeypatch.setattr(stt_pipeline, "run_ortho_on_interval", fake_run_ortho_on_interval)
    monkeypatch.setattr(ipa_transcribe, "transcribe_intervals", fake_transcribe_intervals)

    result = annotate._compute_lexemes_rerun_by_tag(
        "job-tagged",
        {"speakers": ["Saha01"], "tagLabels": ["Thesis"], "field": "both", "pad": 0.2},
    )

    assert len(provider_instances) == 1
    assert provider_instances[0].unloaded is True
    assert len([item for item in aligner_instances if isinstance(item, FakeAligner)]) == 1
    assert "released" in aligner_instances
    assert collect_calls == ["collect"]
    assert [call["provider"] for call in ortho_calls] == [provider_instances[0], provider_instances[0]]
    assert [call["aligner"] for call in ipa_calls] == [aligner_instances[0], aligner_instances[0]]
    assert result["resolved"]["totalConcepts"] == 2
    assert result["total"] == 4
    statuses = [(row["conceptId"], row["field"], row["status"]) for row in result["results"]]
    assert statuses == [
        ("c1", "ortho", "error"),
        ("c1", "ipa", "ok"),
        ("c2", "ortho", "ok"),
        ("c2", "ipa", "ok"),
    ]
    per_concept_progress = [pct for pct, message in progress if message.startswith("Tagged rerun ") and "/2:" in message]
    assert per_concept_progress == sorted(per_concept_progress)
    assert per_concept_progress == [50.0, 95.0]


def test_job_lock_resources_tracks_all_tagged_rerun_speakers() -> None:
    from server_routes import jobs

    resources = jobs._job_lock_resources(
        "compute:lexemes_rerun_by_tag",
        {"computeType": "lexemes_rerun_by_tag", "speakers": ["Saha01", "Saha02", "Saha01"]},
    )

    assert resources == [
        {"kind": "speaker", "id": "Saha01"},
        {"kind": "speaker", "id": "Saha02"},
    ]


def test_compute_dispatch_aliases_include_tagged_rerun(monkeypatch: pytest.MonkeyPatch) -> None:
    from server_routes import jobs

    calls: list[tuple[str, dict[str, Any]]] = []
    completions: list[tuple[str, dict[str, Any], str]] = []
    errors: list[str] = []
    monkeypatch.setattr(jobs._server, "_compute_checkpoint", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs._server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs._server, "_set_job_error", lambda job_id, error, **kwargs: errors.append(str(error)))
    monkeypatch.setattr(
        jobs._server,
        "_set_job_complete",
        lambda job_id, result, message="": completions.append((job_id, result, message)),
    )
    monkeypatch.setattr(
        jobs._server,
        "_compute_lexemes_rerun_by_tag",
        lambda job_id, payload: calls.append((job_id, payload)) or {"ok": True},
    )

    for alias in ("lexemes_rerun_by_tag", "lexemes-rerun-by-tag", "tagged_rerun", "tagged-rerun"):
        calls.clear()
        completions.clear()
        errors.clear()
        jobs._run_compute_job("job-1", alias, {"field": "ortho"})
        assert calls == [("job-1", {"field": "ortho"})]
        assert completions == [("job-1", {"ok": True}, "Compute complete")]
        assert errors == []
