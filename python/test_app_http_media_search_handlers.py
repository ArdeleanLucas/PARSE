import json
import pathlib
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
from app.http.job_observability_handlers import JsonResponseSpec
from app.http.media_search_handlers import (
    BinaryResponseSpec,
    MediaSearchHandlerError,
    build_get_lexeme_search_response,
    build_get_spectrogram_response,
)


def test_build_get_spectrogram_response_uses_working_audio_and_preserves_binary_headers(tmp_path: pathlib.Path) -> None:
    audio_dir = tmp_path / "audio" / "working" / "Fail01"
    audio_dir.mkdir(parents=True)
    audio_path = audio_dir / "clip.wav"
    audio_path.write_bytes(b"wav")
    observed = {}

    def fake_cache_path(project_root: pathlib.Path, speaker: str, start: float, end: float) -> pathlib.Path:
        observed["cache_path_args"] = (project_root, speaker, start, end)
        return tmp_path / "spectrogram-cache.png"

    def fake_generate(audio_file: pathlib.Path, start: float, end: float, cache_file: pathlib.Path, force: bool = False) -> None:
        observed["generate_args"] = (audio_file, start, end, cache_file, force)
        cache_file.write_bytes(b"PNGDATA")

    response = build_get_spectrogram_response(
        "/api/spectrogram?speaker=Fail01&start=1.25&end=2.5&force=yes",
        spectro_module=SimpleNamespace(
            cache_path=fake_cache_path,
            generate_spectrogram_png=fake_generate,
        ),
        normalize_speaker_id=server._normalize_speaker_id,
        resolve_project_path=server._resolve_project_path,
        project_root=tmp_path,
        annotation_primary_source_wav=lambda speaker: None,
        cors_headers=server.CORS_HEADERS,
    )

    assert isinstance(response, BinaryResponseSpec)
    assert response.status == HTTPStatus.OK
    assert response.body == b"PNGDATA"
    assert response.headers["Content-Type"] == "image/png"
    assert response.headers["Cache-Control"] == "public, max-age=3600"
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert observed["cache_path_args"] == (tmp_path, "Fail01", 1.25, 2.5)
    assert observed["generate_args"] == (audio_path, 1.25, 2.5, tmp_path / "spectrogram-cache.png", True)


def test_build_get_spectrogram_response_rejects_invalid_time_ranges(tmp_path: pathlib.Path) -> None:
    with pytest.raises(MediaSearchHandlerError) as exc_info:
        build_get_spectrogram_response(
            "/api/spectrogram?speaker=Fail01&start=2&end=2",
            spectro_module=SimpleNamespace(cache_path=lambda *_args: tmp_path / "unused.png", generate_spectrogram_png=lambda *_args, **_kwargs: None),
            normalize_speaker_id=server._normalize_speaker_id,
            resolve_project_path=server._resolve_project_path,
            project_root=tmp_path,
            annotation_primary_source_wav=lambda speaker: None,
            cors_headers=server.CORS_HEADERS,
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "end must be greater than start"


def test_build_get_lexeme_search_response_returns_candidates_and_signal_metadata(tmp_path: pathlib.Path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    target_path = annotations_dir / "Fail01.parse.json"
    target_path.write_text(json.dumps({"speaker": "Fail01"}), encoding="utf-8")
    other_path = annotations_dir / "Fail02.json"
    other_path.write_text(json.dumps({"speaker": "Fail02"}), encoding="utf-8")

    records = {
        "Fail01": {
            "speaker": "Fail01",
            "tiers": {"ortho": {"intervals": [{"start": 0.0, "end": 0.5, "text": "yek"}]}}
        },
        "Fail02": {
            "speaker": "Fail02",
            "tiers": {},
            "confirmed_anchors": {"1": {"matched_text": "yek"}},
        },
    }
    observed = {}

    def fake_search(target_record, variants, **kwargs):
        observed["target_record"] = target_record
        observed["variants"] = list(variants)
        observed["kwargs"] = kwargs
        return [{"start": 0.0, "end": 0.5, "tier": "ortho", "matched_text": "yek", "matched_variant": "yek", "score": 0.99}]

    lex_module = SimpleNamespace(
        DEFAULT_LANGUAGE="ku",
        DEFAULT_LIMIT=10,
        DEFAULT_MAX_DISTANCE=0.55,
        search=fake_search,
        phonemize_variant=lambda text, language="ku": ["jek"] if text == "yek" else [],
        load_contact_variants=lambda concept_id, path: ["yak", "yek"],
    )

    response = build_get_lexeme_search_response(
        "/api/lexeme/search?speaker=Fail01&variants=yek&concept_id=1&language=ku&tiers=ortho&limit=5&max_distance=0.4",
        lex_module=lex_module,
        normalize_speaker_id=server._normalize_speaker_id,
        annotation_read_path_for_speaker=lambda speaker: target_path,
        read_json_any_file=server._read_json_any_file,
        normalize_annotation_record=lambda record, speaker: records[speaker],
        project_root=tmp_path,
        annotation_filename_suffix=server.ANNOTATION_FILENAME_SUFFIX,
        annotation_legacy_filename_suffix=server.ANNOTATION_LEGACY_FILENAME_SUFFIX,
        sil_config_path=server._sil_config_path,
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "speaker": "Fail01",
            "concept_id": "1",
            "variants": ["yek"],
            "language": "ku",
            "candidates": [{"start": 0.0, "end": 0.5, "tier": "ortho", "matched_text": "yek", "matched_variant": "yek", "score": 0.99}],
            "signals_available": {
                "phonemizer": True,
                "cross_speaker_anchors": 1,
                "contact_variants": ["yak", "yek"],
            },
        },
    )
    assert observed["target_record"] == records["Fail01"]
    assert observed["variants"] == ["yek", "yak"]
    assert observed["kwargs"] == {
        "concept_id": "1",
        "cross_speaker_records": [records["Fail02"]],
        "language": "ku",
        "limit": 5,
        "max_distance": 0.4,
        "tiers": ["ortho"],
    }


def test_build_get_lexeme_search_response_validates_variants_and_limit(tmp_path: pathlib.Path) -> None:
    with pytest.raises(MediaSearchHandlerError) as exc_info:
        build_get_lexeme_search_response(
            "/api/lexeme/search?speaker=Fail01&variants=&limit=999",
            lex_module=SimpleNamespace(DEFAULT_LANGUAGE="ku", DEFAULT_LIMIT=10, DEFAULT_MAX_DISTANCE=0.55, search=lambda *_args, **_kwargs: [], phonemize_variant=lambda *_args, **_kwargs: [], load_contact_variants=lambda *_args, **_kwargs: []),
            normalize_speaker_id=server._normalize_speaker_id,
            annotation_read_path_for_speaker=lambda speaker: tmp_path / "annotations" / f"{speaker}.parse.json",
            read_json_any_file=server._read_json_any_file,
            normalize_annotation_record=lambda record, speaker: record,
            project_root=tmp_path,
            annotation_filename_suffix=server.ANNOTATION_FILENAME_SUFFIX,
            annotation_legacy_filename_suffix=server.ANNOTATION_LEGACY_FILENAME_SUFFIX,
            sil_config_path=server._sil_config_path,
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "variants is required (comma or space separated)"
