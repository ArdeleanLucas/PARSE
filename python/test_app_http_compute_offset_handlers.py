import pathlib
import sys
from http import HTTPStatus
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.http.compute_offset_handlers import (
    ComputeOffsetHandlerError,
    JsonResponseSpec,
    build_post_compute_start_response,
    build_post_compute_status_response,
    build_post_offset_apply_response,
    build_post_offset_detect_from_pair_response,
    build_post_offset_detect_response,
)


class _DummyConflictError(Exception):
    pass



def test_build_post_offset_detect_response_normalizes_speaker_and_launches_job() -> None:
    created: list[tuple[str, dict[str, Any]]] = []
    launched: list[tuple[str, str, dict[str, Any]]] = []

    response = build_post_offset_detect_response(
        {
            "speaker": " Fail01 ",
            "nAnchors": 5,
            "bucket_sec": 0.75,
            "minMatchScore": 0.8,
            "anchorDistribution": "earliest",
            "stt_job_id": "stt-7",
            "sttSegments": [{"start": 0.1, "end": 0.5}],
        },
        normalize_speaker_id=lambda raw: str(raw).strip(),
        create_job=lambda job_type, metadata: created.append((job_type, metadata)) or "job-offset-1",
        launch_compute_runner=lambda job_id, compute_type, payload: launched.append((job_id, compute_type, payload)),
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": "job-offset-1", "status": "running"},
    )
    assert created == [("compute:offset_detect", {"speaker": "Fail01"})]
    assert launched == [
        (
            "job-offset-1",
            "offset_detect",
            {
                "speaker": "Fail01",
                "nAnchors": 5,
                "bucketSec": 0.75,
                "minMatchScore": 0.8,
                "distribution": "earliest",
                "sttJobId": "stt-7",
                "sttSegments": [{"start": 0.1, "end": 0.5}],
            },
        )
    ]



def test_build_post_offset_detect_response_rejects_invalid_speaker() -> None:
    def boom(_raw: Any) -> str:
        raise ValueError("Invalid speaker id")

    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_offset_detect_response(
            {"speaker": "../bad"},
            normalize_speaker_id=boom,
            create_job=lambda *_args, **_kwargs: "unused",
            launch_compute_runner=lambda *_args, **_kwargs: None,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "Invalid speaker id"



def test_build_post_offset_detect_from_pair_supports_single_pair_aliases() -> None:
    created: list[tuple[str, dict[str, Any]]] = []
    launched: list[tuple[str, str, dict[str, Any]]] = []

    response = build_post_offset_detect_from_pair_response(
        {
            "speaker": " Fail02 ",
            "audio_time_sec": 1.25,
            "csvTimeSec": 0.75,
            "concept_id": "sun",
        },
        normalize_speaker_id=lambda raw: str(raw).strip(),
        create_job=lambda job_type, metadata: created.append((job_type, metadata)) or "job-offset-pair-1",
        launch_compute_runner=lambda job_id, compute_type, payload: launched.append((job_id, compute_type, payload)),
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": "job-offset-pair-1", "status": "running"},
    )
    assert created == [("compute:offset_detect_from_pair", {"speaker": "Fail02"})]
    assert launched == [
        (
            "job-offset-pair-1",
            "offset_detect_from_pair",
            {
                "speaker": "Fail02",
                "pairs": [
                    {
                        "audioTimeSec": 1.25,
                        "csvTimeSec": 0.75,
                        "conceptId": "sun",
                    }
                ],
            },
        )
    ]



def test_build_post_offset_detect_from_pair_rejects_empty_pairs() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_offset_detect_from_pair_response(
            {"speaker": "Fail02", "pairs": []},
            normalize_speaker_id=lambda raw: str(raw).strip(),
            create_job=lambda *_args, **_kwargs: "unused",
            launch_compute_runner=lambda *_args, **_kwargs: None,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "pairs must be a non-empty array"



def test_build_post_offset_apply_response_shifts_annotation_and_counts_protected_lexemes() -> None:
    touched: list[dict[str, Any]] = []
    writes: list[tuple[pathlib.Path, dict[str, Any]]] = []
    project_annotation = {
        "speaker": "Fail03",
        "tiers": {
            "concept": {
                "intervals": [
                    {"text": "sun", "manuallyAdjusted": True},
                    {"text": "moon", "manuallyAdjusted": False},
                    {"text": "star", "manuallyAdjusted": True},
                ]
            }
        },
    }

    response = build_post_offset_apply_response(
        {"speaker": " Fail03 ", "offset_sec": -0.5},
        normalize_speaker_id=lambda raw: str(raw).strip(),
        annotation_read_path_for_speaker=lambda speaker: pathlib.Path(f"/tmp/{speaker}.parse.json"),
        read_json_any_file=lambda _path: project_annotation,
        normalize_annotation_record=lambda record, speaker: {**record, "speaker": speaker},
        annotation_shift_intervals=lambda record, offset: (4, 9),
        annotation_touch_metadata=lambda record, preserve_created: touched.append({"record": record, "preserve_created": preserve_created}),
        annotation_record_path_for_speaker=lambda speaker: pathlib.Path(f"/write/{speaker}.parse.json"),
        write_json_file=lambda path, record: writes.append((path, record)),
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "speaker": "Fail03",
            "appliedOffsetSec": -0.5,
            "shiftedIntervals": 4,
            "protectedIntervals": 9,
            "protectedLexemes": 2,
        },
    )
    assert touched == [{"record": {**project_annotation, "speaker": "Fail03"}, "preserve_created": True}]
    assert writes == [(pathlib.Path("/write/Fail03.parse.json"), {**project_annotation, "speaker": "Fail03"})]



def test_build_post_offset_apply_response_rejects_missing_offset() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_offset_apply_response(
            {"speaker": "Fail03"},
            normalize_speaker_id=lambda raw: str(raw).strip(),
            annotation_read_path_for_speaker=lambda speaker: pathlib.Path(f"/tmp/{speaker}.parse.json"),
            read_json_any_file=lambda _path: {},
            normalize_annotation_record=lambda record, speaker: {**record, "speaker": speaker},
            annotation_shift_intervals=lambda record, offset: (0, 0),
            annotation_touch_metadata=lambda record, preserve_created: None,
            annotation_record_path_for_speaker=lambda speaker: pathlib.Path(f"/write/{speaker}.parse.json"),
            write_json_file=lambda path, record: None,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "offsetSec is required"



def test_build_post_offset_apply_response_rejects_zero_offset() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_offset_apply_response(
            {"speaker": "Fail03", "offsetSec": 0},
            normalize_speaker_id=lambda raw: str(raw).strip(),
            annotation_read_path_for_speaker=lambda speaker: pathlib.Path(f"/tmp/{speaker}.parse.json"),
            read_json_any_file=lambda _path: {},
            normalize_annotation_record=lambda record, speaker: {**record, "speaker": speaker},
            annotation_shift_intervals=lambda record, offset: (0, 0),
            annotation_touch_metadata=lambda record, preserve_created: None,
            annotation_record_path_for_speaker=lambda speaker: pathlib.Path(f"/write/{speaker}.parse.json"),
            write_json_file=lambda path, record: None,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "offsetSec is effectively zero — nothing to apply"



def test_build_post_offset_apply_response_rejects_non_finite_offset() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_offset_apply_response(
            {"speaker": "Fail03", "offsetSec": float("inf")},
            normalize_speaker_id=lambda raw: str(raw).strip(),
            annotation_read_path_for_speaker=lambda speaker: pathlib.Path(f"/tmp/{speaker}.parse.json"),
            read_json_any_file=lambda _path: {},
            normalize_annotation_record=lambda record, speaker: {**record, "speaker": speaker},
            annotation_shift_intervals=lambda record, offset: (0, 0),
            annotation_touch_metadata=lambda record, preserve_created: None,
            annotation_record_path_for_speaker=lambda speaker: pathlib.Path(f"/write/{speaker}.parse.json"),
            write_json_file=lambda path, record: None,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "offsetSec must be a finite number"



def test_build_post_offset_apply_response_rejects_when_nothing_was_shifted() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_offset_apply_response(
            {"speaker": "Fail03", "offsetSec": 1.0},
            normalize_speaker_id=lambda raw: str(raw).strip(),
            annotation_read_path_for_speaker=lambda speaker: pathlib.Path(f"/tmp/{speaker}.parse.json"),
            read_json_any_file=lambda _path: {},
            normalize_annotation_record=lambda record, speaker: {**record, "speaker": speaker},
            annotation_shift_intervals=lambda record, offset: (0, 0),
            annotation_touch_metadata=lambda record, preserve_created: None,
            annotation_record_path_for_speaker=lambda speaker: pathlib.Path(f"/write/{speaker}.parse.json"),
            write_json_file=lambda path, record: None,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "No intervals were shifted"



def test_build_post_compute_start_response_preserves_callback_and_speaker_metadata() -> None:
    created: list[tuple[str, dict[str, Any]]] = []
    launched: list[tuple[str, str, dict[str, Any]]] = []
    body = {"speaker": "Fail04", "extra": True}

    response = build_post_compute_start_response(
        " Full_Pipeline ",
        body,
        callback_url="https://example.com/callback",
        create_job=lambda job_type, metadata: created.append((job_type, metadata)) or "job-compute-1",
        launch_compute_runner=lambda job_id, compute_type, payload: launched.append((job_id, compute_type, payload)),
        job_conflict_error_cls=_DummyConflictError,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": "job-compute-1", "status": "running"},
    )
    assert created == [
        (
            "compute:full_pipeline",
            {
                "computeType": "full_pipeline",
                "payload": {"speaker": "Fail04", "extra": True},
                "callbackUrl": "https://example.com/callback",
                "speaker": "Fail04",
            },
        )
    ]
    assert launched == [("job-compute-1", "full_pipeline", {"speaker": "Fail04", "extra": True})]



def test_build_post_compute_start_response_maps_job_conflicts_to_409() -> None:
    def create_job(_job_type: str, _metadata: dict[str, Any]) -> str:
        raise _DummyConflictError("speaker Fail04 already locked")

    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_compute_start_response(
            "similarity",
            {},
            callback_url=None,
            create_job=create_job,
            launch_compute_runner=lambda *_args, **_kwargs: None,
            job_conflict_error_cls=_DummyConflictError,
        )

    assert excinfo.value.status == HTTPStatus.CONFLICT
    assert excinfo.value.message == "speaker Fail04 already locked"



def test_build_post_compute_start_response_rejects_missing_compute_type() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_compute_start_response(
            " status ",
            {},
            callback_url=None,
            create_job=lambda *_args, **_kwargs: "unused",
            launch_compute_runner=lambda *_args, **_kwargs: None,
            job_conflict_error_cls=_DummyConflictError,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "Compute type is required"



def test_build_post_compute_status_response_accepts_job_id_aliases_and_typed_match() -> None:
    response = build_post_compute_status_response(
        "offset_detect",
        {"job_id": "job-17"},
        get_job_snapshot=lambda job_id: {"jobId": job_id, "type": "compute:offset_detect", "status": "running"},
        job_response_payload=lambda job: {"jobId": job["jobId"], "status": job["status"]},
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"jobId": "job-17", "status": "running"},
    )



def test_build_post_compute_status_response_rejects_type_mismatch() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_compute_status_response(
            "similarity",
            {"jobId": "job-99"},
            get_job_snapshot=lambda _job_id: {"jobId": "job-99", "type": "compute:stt", "status": "running"},
            job_response_payload=lambda job: {"jobId": job["jobId"], "status": job["status"]},
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "jobId does not match compute type"



def test_build_post_compute_status_response_rejects_missing_job_id() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_compute_status_response(
            None,
            {},
            get_job_snapshot=lambda _job_id: None,
            job_response_payload=lambda job: job,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "jobId is required"



def test_build_post_compute_status_response_rejects_unknown_job_id() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_compute_status_response(
            None,
            {"jobId": "missing-job"},
            get_job_snapshot=lambda _job_id: None,
            job_response_payload=lambda job: job,
        )

    assert excinfo.value.status == HTTPStatus.NOT_FOUND
    assert excinfo.value.message == "Unknown jobId"



def test_build_post_compute_status_response_rejects_non_compute_jobs() -> None:
    with pytest.raises(ComputeOffsetHandlerError) as excinfo:
        build_post_compute_status_response(
            None,
            {"jobId": "job-22"},
            get_job_snapshot=lambda _job_id: {"jobId": "job-22", "type": "stt", "status": "running"},
            job_response_payload=lambda job: job,
        )

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "jobId is not a compute job"
