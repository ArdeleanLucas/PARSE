import json
import pathlib
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from app.http.job_observability_handlers import JsonResponseSpec
from app.http.speech_annotation_handlers import (
    SpeechAnnotationHandlerError,
    build_get_stt_segments_response,
    build_post_normalize_response,
    build_post_normalize_status_response,
    build_post_stt_start_response,
    build_post_stt_status_response,
    build_post_suggest_response,
)


class _DummyConflictError(Exception):
    pass


def test_build_get_stt_segments_response_returns_empty_segments_when_cache_missing(tmp_path: pathlib.Path) -> None:
    response = build_get_stt_segments_response(
        "Fail01",
        normalize_speaker_id=lambda raw: str(raw).strip(),
        stt_cache_path=lambda speaker: tmp_path / f"{speaker}.json",
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"speaker": "Fail01", "segments": []},
    )



def test_build_get_stt_segments_response_preserves_cached_metadata(tmp_path: pathlib.Path) -> None:
    cache_path = tmp_path / "Fail01.json"
    cache_path.write_text(
        json.dumps(
            {
                "source_wav": "audio/original/Fail01/input.wav",
                "language": "ku",
                "segments": [{"start": 0.0, "end": 0.4, "text": "yek"}],
            }
        ),
        encoding="utf-8",
    )

    response = build_get_stt_segments_response(
        "Fail01",
        normalize_speaker_id=lambda raw: str(raw).strip(),
        stt_cache_path=lambda speaker: cache_path,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "speaker": "Fail01",
            "source_wav": "audio/original/Fail01/input.wav",
            "language": "ku",
            "segments": [{"start": 0.0, "end": 0.4, "text": "yek"}],
        },
    )



def test_build_post_normalize_response_uses_source_alias_fallback_and_callback() -> None:
    created = []
    launched = []

    response = build_post_normalize_response(
        {"speaker": " Fail01 "},
        callback_url="https://example.test/hooks/normalize",
        normalize_speaker_id=lambda raw: str(raw).strip(),
        annotation_primary_source_wav=lambda speaker: f"audio/original/{speaker}/input.wav",
        create_job=lambda job_type, metadata: created.append((job_type, metadata)) or "job-norm-1",
        launch_normalize_job=lambda job_id, speaker, source_wav: launched.append((job_id, speaker, source_wav)),
        job_conflict_error_cls=_DummyConflictError,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"job_id": "job-norm-1", "jobId": "job-norm-1", "status": "running"},
    )
    assert created == [
        (
            "normalize",
            {
                "speaker": "Fail01",
                "sourceWav": "audio/original/Fail01/input.wav",
                "callbackUrl": "https://example.test/hooks/normalize",
            },
        )
    ]
    assert launched == [("job-norm-1", "Fail01", "audio/original/Fail01/input.wav")]



def test_build_post_normalize_status_response_accepts_job_id_alias() -> None:
    response = build_post_normalize_status_response(
        {"job_id": "job-55"},
        get_job_snapshot=lambda job_id: {"jobId": job_id, "type": "normalize", "status": "running"},
        job_response_payload=lambda job: {"jobId": job["jobId"], "status": job["status"]},
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": "job-55", "status": "running"},
    )



def test_build_post_normalize_status_response_rejects_wrong_job_type() -> None:
    with pytest.raises(SpeechAnnotationHandlerError) as exc_info:
        build_post_normalize_status_response(
            {"jobId": "job-55"},
            get_job_snapshot=lambda job_id: {"jobId": job_id, "type": "stt", "status": "running"},
            job_response_payload=lambda job: job,
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "job_id is not a normalize job"



def test_build_post_stt_start_response_preserves_language_blank_and_callback() -> None:
    created = []
    launched = []

    response = build_post_stt_start_response(
        {"speaker": "Fail02", "source_wav": "audio/original/Fail02/input.wav", "language": " "},
        callback_url="https://example.test/hooks/stt",
        create_job=lambda job_type, metadata: created.append((job_type, metadata)) or "job-stt-1",
        launch_compute_runner=lambda job_id, compute_type, payload: launched.append((job_id, compute_type, payload)),
        job_conflict_error_cls=_DummyConflictError,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": "job-stt-1", "status": "running"},
    )
    assert created == [
        (
            "stt",
            {
                "speaker": "Fail02",
                "sourceWav": "audio/original/Fail02/input.wav",
                "language": None,
                "callbackUrl": "https://example.test/hooks/stt",
            },
        )
    ]
    assert launched == [
        (
            "job-stt-1",
            "stt",
            {"speaker": "Fail02", "sourceWav": "audio/original/Fail02/input.wav", "language": None},
        )
    ]



def test_build_post_stt_status_response_requires_job_id() -> None:
    with pytest.raises(SpeechAnnotationHandlerError) as exc_info:
        build_post_stt_status_response(
            {},
            get_job_snapshot=lambda job_id: None,
            job_response_payload=lambda job: job,
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "jobId is required"



def test_build_post_suggest_response_uses_provider_first_and_aliases() -> None:
    observed = {}

    class _Provider:
        def suggest_concepts(self, transcript_windows, reference_forms):
            observed["transcript_windows"] = transcript_windows
            observed["reference_forms"] = reference_forms
            return [{"conceptId": "1", "suggestions": ["yek"]}]

    response = build_post_suggest_response(
        {
            "speaker": "Fail03",
            "conceptIds": ["1"],
            "transcript_windows": [{"start": 0.0, "end": 0.5, "text": "yek"}],
            "reference_forms": ["yek"],
        },
        get_llm_provider=lambda: _Provider(),
        load_cached_suggestions=lambda speaker, concept_ids: (_ for _ in ()).throw(AssertionError("cache fallback should not run")),
        coerce_concept_id_list=lambda raw: [str(value) for value in raw],
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"suggestions": [{"conceptId": "1", "suggestions": ["yek"]}]},
    )
    assert observed == {
        "transcript_windows": [{"start": 0.0, "end": 0.5, "text": "yek"}],
        "reference_forms": ["yek"],
    }



def test_build_post_suggest_response_falls_back_to_cached_on_provider_failure() -> None:
    class _Provider:
        def suggest_concepts(self, transcript_windows, reference_forms):
            raise RuntimeError("provider down")

    response = build_post_suggest_response(
        {"speaker": "Fail03", "concept_ids": ["1", "2"]},
        get_llm_provider=lambda: _Provider(),
        load_cached_suggestions=lambda speaker, concept_ids: [{"speaker": speaker, "concept_ids": concept_ids}],
        coerce_concept_id_list=lambda raw: [str(value) for value in raw],
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"suggestions": [{"speaker": "Fail03", "concept_ids": ["1", "2"]}]},
    )
