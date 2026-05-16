from __future__ import annotations

import csv
import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

import pytest

from ai.provider import ConfidenceScore
from ai.speaker_locks import SpeakerLockError
from app.http.lexeme_rerun_handlers import (
    LexemeRerunHandlerError,
    LexemeRerunSubprocessError,
    _parse_request,
    build_post_run_ipa_response,
    build_post_run_ortho_response,
)


def _write_workspace(root: Path, *, speaker: str = "Saha01") -> tuple[Path, Path]:
    (root / "annotations").mkdir(parents=True, exist_ok=True)
    (root / "audio" / "working" / speaker).mkdir(parents=True, exist_ok=True)
    audio_path = root / "audio" / "working" / speaker / "working.wav"
    audio_path.write_bytes(b"RIFFWAVEfake")

    with (root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "root", "source_item": "root", "source_survey": "KLQ", "custom_order": ""})

    annotation_path = root / "annotations" / f"{speaker}.parse.json"
    annotation_payload = {
        "project_id": "parse-test",
        "speaker": speaker,
        "source_audio": "audio/working/Saha01/working.wav",
        "source_audio_duration_sec": 10.0,
        "tiers": {
            "concept": {"type": "interval", "display_order": 3, "intervals": [{"start": 2795.918, "end": 2796.698, "text": "root", "concept_id": "1"}]},
            "ortho": {"type": "interval", "display_order": 2, "intervals": [{"start": 2795.918, "end": 2796.698, "text": "old ortho"}]},
            "ipa": {"type": "interval", "display_order": 1, "intervals": [{"start": 2795.918, "end": 2796.698, "text": "old ipa"}]},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
    }
    annotation_path.write_text(json.dumps(annotation_payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return annotation_path, audio_path


def _annotation_path(root: Path) -> Callable[[str], Path]:
    return lambda speaker: root / "annotations" / f"{speaker}.parse.json"


def _read_json_any(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_record(payload: Any, speaker: str) -> dict[str, Any]:
    assert isinstance(payload, dict)
    out = dict(payload)
    out.setdefault("speaker", speaker)
    return out


def _normalize_speaker(value: Any) -> str:
    speaker = str(value or "").strip()
    if not speaker:
        raise ValueError("speaker is required")
    return speaker


def _ortho_response(
    root: Path,
    body: dict[str, Any],
    *,
    runner: Callable[..., str] | None = None,
    acquire: Callable[[str, Path], Path] | None = None,
    release: Callable[[str, Path], None] | None = None,
):
    runner = runner or (lambda **kwargs: "")
    acquire = acquire or (lambda speaker, locks_dir: locks_dir / f"{speaker}.lock")
    release = release or (lambda speaker, locks_dir: None)
    _annotation_path_file, audio_path = _write_workspace(root)
    body = {"async": False, **body}
    return build_post_run_ortho_response(
        body,
        project_root=root,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_path(root),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
        resolve_audio_path_for_speaker=lambda speaker: audio_path,
        run_ortho_interval=runner,
        locks_dir=root / ".parse-locks",
        acquire_speaker_lock=acquire,
        release_speaker_lock=release,
    )


def _ipa_response(
    root: Path,
    body: dict[str, Any],
    *,
    runner: Callable[..., str] | None = None,
):
    runner = runner or (lambda **kwargs: "")
    _annotation_path_file, audio_path = _write_workspace(root)
    body = {"async": False, **body}
    return build_post_run_ipa_response(
        body,
        project_root=root,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_path(root),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
        resolve_audio_path_for_speaker=lambda speaker: audio_path,
        run_ipa_interval=runner,
        locks_dir=root / ".parse-locks",
        acquire_speaker_lock=lambda speaker, locks_dir: locks_dir / f"{speaker}.lock",
        release_speaker_lock=lambda speaker, locks_dir: None,
    )


def test_run_ortho_happy_path(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def fake_runner(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "ریشەم"

    response = _ortho_response(
        tmp_path,
        {"speaker": "Saha01", "concept_key": "root", "start": 2795.918, "end": 2796.698},
        runner=fake_runner,
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "ortho": "ریشەم",
        "interval": {"start": 2795.918, "end": 2796.698},
        "source": "rerun",
        "jobId": None,
    }
    assert calls and calls[0]["start"] == pytest.approx(2795.718)
    assert calls[0]["end"] == pytest.approx(2796.898)


def test_run_ipa_happy_path(tmp_path: Path) -> None:
    response = _ipa_response(
        tmp_path,
        {"speaker": "Saha01", "concept_key": "root", "start": 2795.918, "end": 2796.698},
        runner=lambda **kwargs: "ʃari:",
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "ipa": "ʃari:",
        "interval": {"start": 2795.918, "end": 2796.698},
        "source": "rerun",
        "jobId": None,
    }


def test_run_ortho_sync_response_forwards_typed_confidence_triplet(tmp_path: Path) -> None:
    response = _ortho_response(
        tmp_path,
        {"speaker": "Saha01", "concept_key": "root", "start": 2795.918, "end": 2796.698},
        runner=lambda **kwargs: {
            "text": "ریشەم",
            "confidence": ConfidenceScore(value=0.42, source="constant_fallback", n_tokens=0),
        },
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "ortho": "ریشەم",
        "interval": {"start": 2795.918, "end": 2796.698},
        "source": "rerun",
        "jobId": None,
        "confidence": 0.42,
        "confidence_source": "constant_fallback",
        "confidence_n_tokens": 0,
    }


def _async_dependencies(root: Path, tier: str = "ortho"):
    created: list[tuple[str, dict[str, Any]]] = []
    launched: list[tuple[str, str, dict[str, Any]]] = []

    def create_job(job_type: str, metadata: dict[str, Any]) -> str:
        created.append((job_type, metadata))
        return f"job-{tier}-1"

    def launch_compute_runner(job_id: str, compute_type: str, payload: dict[str, Any]) -> None:
        launched.append((job_id, compute_type, payload))

    return created, launched, create_job, launch_compute_runner


def test_run_ortho_default_starts_compute_job_without_running_subprocess(tmp_path: Path) -> None:
    _annotation_path_file, audio_path = _write_workspace(tmp_path)
    calls: list[dict[str, Any]] = []
    lock_calls: list[str] = []
    created, launched, create_job, launch_compute_runner = _async_dependencies(tmp_path, "ortho")

    response = build_post_run_ortho_response(
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0, "pad": 0.5},
        project_root=tmp_path,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_path(tmp_path),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
        resolve_audio_path_for_speaker=lambda speaker: audio_path,
        run_ortho_interval=lambda **kwargs: calls.append(kwargs) or "should-not-run",
        locks_dir=tmp_path / ".parse-locks",
        acquire_speaker_lock=lambda speaker, locks_dir: lock_calls.append(speaker) or locks_dir / f"{speaker}.lock",
        release_speaker_lock=lambda speaker, locks_dir: None,
        create_job=create_job,
        launch_compute_runner=launch_compute_runner,
    )

    assert response.status == HTTPStatus.ACCEPTED
    assert response.payload == {"jobId": "job-ortho-1"}
    assert calls == []
    assert lock_calls == []
    assert created == [("compute:lexeme_rerun_ortho", {
        "computeType": "lexeme_rerun_ortho",
        "speaker": "Saha01",
        "concept_key": "root",
        "tier": "ortho",
        "interval": {"start": 1.0, "end": 2.0},
        "pad": 0.5,
    })]
    assert launched == [("job-ortho-1", "lexeme_rerun_ortho", {
        "speaker": "Saha01",
        "concept_key": "root",
        "start": 1.0,
        "end": 2.0,
        "language": None,
        "pad": 0.5,
    })]


def test_run_ipa_default_starts_compute_job(tmp_path: Path) -> None:
    _annotation_path_file, audio_path = _write_workspace(tmp_path)
    created, launched, create_job, launch_compute_runner = _async_dependencies(tmp_path, "ipa")

    response = build_post_run_ipa_response(
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0},
        project_root=tmp_path,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_path(tmp_path),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
        resolve_audio_path_for_speaker=lambda speaker: audio_path,
        run_ipa_interval=lambda **kwargs: "should-not-run",
        locks_dir=tmp_path / ".parse-locks",
        create_job=create_job,
        launch_compute_runner=launch_compute_runner,
    )

    assert response.status == HTTPStatus.ACCEPTED
    assert response.payload == {"jobId": "job-ipa-1"}
    assert created[0][0] == "compute:lexeme_rerun_ipa"
    assert created[0][1]["computeType"] == "lexeme_rerun_ipa"
    assert launched[0][1] == "lexeme_rerun_ipa"


def test_run_ortho_async_false_retains_legacy_success_shape(tmp_path: Path) -> None:
    response = _ortho_response(
        tmp_path,
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0, "async": False},
        runner=lambda **kwargs: "ڕیشە",
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "ortho": "ڕیشە",
        "interval": {"start": 1.0, "end": 2.0},
        "source": "rerun",
        "jobId": None,
    }


def test_create_job_conflict_maps_to_409(tmp_path: Path) -> None:
    class Conflict(Exception):
        pass

    _write_workspace(tmp_path)

    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        build_post_run_ortho_response(
            {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0},
            project_root=tmp_path,
            normalize_speaker_id=_normalize_speaker,
            annotation_read_path_for_speaker=_annotation_path(tmp_path),
            read_json_any_file=_read_json_any,
            normalize_annotation_record=_normalize_record,
            resolve_audio_path_for_speaker=lambda speaker: tmp_path / "audio" / "working" / speaker / "working.wav",
            run_ortho_interval=lambda **kwargs: "unused",
            locks_dir=tmp_path / ".parse-locks",
            create_job=lambda _job_type, _metadata: (_ for _ in ()).throw(Conflict("speaker locked by job")),
            launch_compute_runner=lambda *_args: None,
            job_conflict_error_cls=Conflict,
        )

    assert exc_info.value.status == HTTPStatus.CONFLICT
    assert str(exc_info.value) == "speaker locked by job"


def test_run_ortho_invalid_interval(tmp_path: Path) -> None:
    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ortho_response(tmp_path, {"speaker": "Saha01", "concept_key": "root", "start": 2.0, "end": 2.0})

    assert getattr(exc_info.value, "status") == HTTPStatus.BAD_REQUEST
    assert "interval" in str(exc_info.value).lower()


def test_run_ortho_missing_speaker(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        build_post_run_ortho_response(
            {"speaker": "Missing", "concept_key": "root", "start": 1.0, "end": 2.0},
            project_root=tmp_path,
            normalize_speaker_id=_normalize_speaker,
            annotation_read_path_for_speaker=_annotation_path(tmp_path),
            read_json_any_file=_read_json_any,
            normalize_annotation_record=_normalize_record,
            resolve_audio_path_for_speaker=lambda speaker: tmp_path / "missing.wav",
            run_ortho_interval=lambda **kwargs: "unused",
            locks_dir=tmp_path / ".parse-locks",
            acquire_speaker_lock=lambda speaker, locks_dir: locks_dir / f"{speaker}.lock",
            release_speaker_lock=lambda speaker, locks_dir: None,
        )

    assert getattr(exc_info.value, "status") == HTTPStatus.NOT_FOUND
    assert str(exc_info.value) == "speaker not found"


def test_run_ortho_missing_concept_key_field(tmp_path: Path) -> None:
    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ortho_response(tmp_path, {"speaker": "Saha01", "start": 1.0, "end": 2.0})

    assert getattr(exc_info.value, "status") == HTTPStatus.BAD_REQUEST
    assert "concept_key" in str(exc_info.value)


def test_run_ortho_missing_concept_key(tmp_path: Path) -> None:
    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ortho_response(tmp_path, {"speaker": "Saha01", "concept_key": "unknown", "start": 1.0, "end": 2.0})

    assert getattr(exc_info.value, "status") == HTTPStatus.NOT_FOUND
    assert str(exc_info.value) == "concept not found"


def test_run_ortho_speaker_locked(tmp_path: Path) -> None:
    def locked(_speaker: str, _locks_dir: Path) -> Path:
        raise SpeakerLockError("speaker locked elsewhere")

    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ortho_response(
            tmp_path,
            {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0},
            acquire=locked,
        )

    assert getattr(exc_info.value, "status") == HTTPStatus.CONFLICT
    assert str(exc_info.value) == "speaker locked"


def test_run_ortho_provider_error(tmp_path: Path) -> None:
    def broken(**kwargs: Any) -> str:
        raise RuntimeError("model unavailable")

    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ortho_response(
            tmp_path,
            {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0},
            runner=broken,
        )

    assert getattr(exc_info.value, "status") == HTTPStatus.INTERNAL_SERVER_ERROR
    assert str(exc_info.value) == "model unavailable"


def test_run_ortho_interval_too_long(tmp_path: Path) -> None:
    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ortho_response(tmp_path, {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 62.0})

    assert getattr(exc_info.value, "status") == HTTPStatus.BAD_REQUEST
    assert "interval" in str(exc_info.value).lower()


def test_short_ipa_interval_returns_400_before_runner_starts(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ipa_response(
            tmp_path,
            {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 1.06, "pad": 0.0},
            runner=lambda **kwargs: calls.append(kwargs) or "should-not-run",
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert "interval_too_short" in str(exc_info.value)
    assert calls == []


def test_short_ortho_interval_returns_400_before_runner_starts(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ortho_response(
            tmp_path,
            {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 1.06, "pad": 0.0},
            runner=lambda **kwargs: calls.append(kwargs) or "should-not-run",
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert "interval_too_short" in str(exc_info.value)
    assert calls == []


def test_subprocess_error_maps_to_503_payload(tmp_path: Path) -> None:
    response = _ipa_response(
        tmp_path,
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 1.2, "pad": 0.0},
        runner=lambda **_kwargs: (_ for _ in ()).throw(
            LexemeRerunSubprocessError(
                code="subprocess_segfault",
                exit_code=139,
                message="lexeme IPA subprocess exited with code 139",
            )
        ),
    )

    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.payload == {
        "status": "error",
        "code": "subprocess_segfault",
        "exit_code": 139,
        "message": "lexeme IPA subprocess exited with code 139",
    }


def test_subprocess_error_maps_stderr_tail_to_503_payload(tmp_path: Path) -> None:
    response = _ipa_response(
        tmp_path,
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 1.2, "pad": 0.0},
        runner=lambda **_kwargs: (_ for _ in ()).throw(
            LexemeRerunSubprocessError(
                code="subprocess_segfault",
                exit_code=-11,
                message="lexeme IPA subprocess exited with code -11",
                stderr_tail="DIAGNOSTIC_SMOKE_TEST: about to crash on purpose",
            )
        ),
    )

    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.payload == {
        "status": "error",
        "code": "subprocess_segfault",
        "exit_code": -11,
        "message": "lexeme IPA subprocess exited with code -11",
        "stderr_tail": "DIAGNOSTIC_SMOKE_TEST: about to crash on purpose",
    }


def test_success_payload_does_not_include_stderr_tail(tmp_path: Path) -> None:
    response = _ipa_response(
        tmp_path,
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 1.2, "pad": 0.0},
        runner=lambda **_kwargs: "ʃari:",
    )

    assert response.status == HTTPStatus.OK
    assert "stderr_tail" not in response.payload


def test_ortho_subprocess_error_maps_to_503_payload(tmp_path: Path) -> None:
    response = _ortho_response(
        tmp_path,
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 1.2, "pad": 0.0},
        runner=lambda **_kwargs: (_ for _ in ()).throw(
            LexemeRerunSubprocessError(
                code="subprocess_oom",
                exit_code=137,
                message="lexeme ORTH subprocess was killed (likely OOM)",
            )
        ),
    )

    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.payload == {
        "status": "error",
        "code": "subprocess_oom",
        "exit_code": 137,
        "message": "lexeme ORTH subprocess was killed (likely OOM)",
    }


def test_run_ipa_does_not_mutate_record(tmp_path: Path) -> None:
    annotation_path, _audio_path = _write_workspace(tmp_path)
    before = annotation_path.read_bytes()

    response = build_post_run_ipa_response(
        {"speaker": "Saha01", "concept_key": "root", "start": 2795.918, "end": 2796.698, "async": False},
        project_root=tmp_path,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_path(tmp_path),
        read_json_any_file=_read_json_any,
        normalize_annotation_record=_normalize_record,
        resolve_audio_path_for_speaker=lambda speaker: tmp_path / "audio" / "working" / speaker / "working.wav",
        run_ipa_interval=lambda **kwargs: "ʃari:",
        locks_dir=tmp_path / ".parse-locks",
        acquire_speaker_lock=lambda speaker, locks_dir: locks_dir / f"{speaker}.lock",
        release_speaker_lock=lambda speaker, locks_dir: None,
    )

    assert response.status == HTTPStatus.OK
    assert annotation_path.read_bytes() == before


def _base_rerun_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0}
    body.update(overrides)
    return body


def test_pad_default_is_0_20(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    response = _ortho_response(
        tmp_path,
        _base_rerun_body(),
        runner=lambda **kwargs: calls.append(kwargs) or "ریشەم",
    )

    assert response.status == HTTPStatus.OK
    assert calls[0]["start"] == pytest.approx(0.8)
    assert calls[0]["end"] == pytest.approx(2.2)
    assert response.payload["interval"] == {"start": 1.0, "end": 2.0}


def test_pad_explicit_0_0_no_padding(tmp_path: Path) -> None:
    parsed = _parse_request(
        _base_rerun_body(pad=0.0),
        normalize_speaker_id=_normalize_speaker,
        record={"metadata": {"language_code": "ku"}},
    )
    assert parsed.pad == pytest.approx(0.0)
    calls: list[dict[str, Any]] = []

    _ortho_response(
        tmp_path,
        _base_rerun_body(pad=0.0),
        runner=lambda **kwargs: calls.append(kwargs) or "ریشەم",
    )

    assert calls[0]["start"] == pytest.approx(1.0)
    assert calls[0]["end"] == pytest.approx(2.0)


def test_pad_explicit_0_5_widens(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    _ipa_response(
        tmp_path,
        _base_rerun_body(pad=0.5),
        runner=lambda **kwargs: calls.append(kwargs) or "ʃari:",
    )

    assert calls[0]["start"] == pytest.approx(0.5)
    assert calls[0]["end"] == pytest.approx(2.5)


def test_pad_invalid_value_400(tmp_path: Path) -> None:
    with pytest.raises(LexemeRerunHandlerError) as exc_info:
        _ortho_response(tmp_path, _base_rerun_body(pad=0.123), runner=lambda **kwargs: "unused")

    assert getattr(exc_info.value, "status") == HTTPStatus.BAD_REQUEST
    message = str(exc_info.value)
    assert "pad must be one of" in message
    assert "0.0" in message and "0.2" in message and "0.5" in message


def test_pad_clamped_to_zero_at_start(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    _ortho_response(
        tmp_path,
        _base_rerun_body(start=0.1, end=0.5, pad=0.2),
        runner=lambda **kwargs: calls.append(kwargs) or "ریشەم",
    )

    assert calls[0]["start"] == pytest.approx(0.0)
    assert calls[0]["end"] == pytest.approx(0.7)
