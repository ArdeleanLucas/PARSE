from __future__ import annotations

import csv
import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

import pytest

from ai.speaker_locks import SpeakerLockError
from app.http.lexeme_rerun_handlers import (
    LexemeRerunHandlerError,
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
    }
    assert calls and calls[0]["start"] == 2795.918 and calls[0]["end"] == 2796.698


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
    }


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


def test_run_ipa_does_not_mutate_record(tmp_path: Path) -> None:
    annotation_path, _audio_path = _write_workspace(tmp_path)
    before = annotation_path.read_bytes()

    response = build_post_run_ipa_response(
        {"speaker": "Saha01", "concept_key": "root", "start": 2795.918, "end": 2796.698},
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
