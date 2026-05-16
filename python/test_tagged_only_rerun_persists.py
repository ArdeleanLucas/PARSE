"""Verify tagged-only rerun persists transcribed text to annotation files.

Regression evidence from 2026-05-10: tagged-only ORTH/IPA runs reported
``ok: N`` but left the speaker annotation mtime unchanged because the batch
loop reused preview-only per-concept rerun helpers without a write step.
"""
from __future__ import annotations

import csv
import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from ai.provider import ConfidenceScore
from app.http.job_observability_handlers import JsonResponseSpec
from app.http.lexeme_rerun_handlers import LexemeRerunHandlerError, build_post_run_ortho_response
from app.http.tag_filtered_rerun_handlers import build_post_lexemes_rerun_by_tag_response
from server_routes import annotate


_OLD_MODIFIED = "2000-01-01T00:00:00Z"


def _vocab() -> list[dict[str, Any]]:
    return [
        {"id": "t-thesis", "label": "Thesis", "color": "#111111", "concepts": [], "lexemeTargets": []},
    ]


def _annotation_read_path(tmp_path: Path) -> Callable[[str], Path]:
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


def _seed_concepts_csv(tmp_path: Path) -> None:
    with (tmp_path / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"],
        )
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "hair", "source_item": "hair", "source_survey": "KLQ", "custom_order": ""})
        writer.writerow({"id": "2", "concept_en": "leaf", "source_item": "leaf", "source_survey": "KLQ", "custom_order": ""})


def _seed_audio(tmp_path: Path) -> Path:
    audio_dir = tmp_path / "audio" / "working" / "Saha01"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / "working.wav"
    audio_path.write_bytes(b"RIFFWAVEfake")
    return audio_path


def _seed_annotation(tmp_path: Path, *, include_legacy: bool = False) -> tuple[Path, Path]:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    annotation = {
        "project_id": "parse-test",
        "speaker": "Saha01",
        "source_audio": "audio/working/Saha01/working.wav",
        "source_audio_duration_sec": 10.0,
        "concept_tags": {"1": ["t-thesis"], "2": ["t-thesis"]},
        "metadata": {"created": "1999-01-01T00:00:00Z", "modified": _OLD_MODIFIED, "language_code": "und"},
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [
                    {"start": 1.0, "end": 2.0, "text": "hair", "concept_id": "1"},
                    {"start": 3.0, "end": 4.0, "text": "leaf", "concept_id": "2"},
                ],
            },
            "ortho": {
                "type": "interval",
                "display_order": 2,
                "intervals": [
                    {"start": 1.0, "end": 2.0, "text": "OLD_HAIR"},
                    {"start": 3.0, "end": 4.0, "text": "OLD_LEAF"},
                ],
            },
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho_words": {
                "type": "interval",
                "display_order": 4,
                "intervals": [
                    {"start": 0.2, "end": 0.4, "text": "OUTSIDE_BEFORE", "source": "seed"},
                    {"start": 1.0, "end": 1.5, "text": "OLD", "source": "seed"},
                    {"start": 1.5, "end": 2.0, "text": "HAIR", "source": "seed"},
                    {"start": 3.0, "end": 3.5, "text": "OLD", "source": "seed"},
                    {"start": 3.5, "end": 4.0, "text": "LEAF", "source": "seed"},
                    {"start": 4.5, "end": 4.7, "text": "OUTSIDE_AFTER", "source": "seed"},
                ],
            },
            "speaker": {"type": "interval", "display_order": 5, "intervals": []},
        },
    }
    canonical_path = annotations_dir / "Saha01.parse.json"
    legacy_path = annotations_dir / "Saha01.json"
    canonical_path.write_text(json.dumps(annotation, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    if include_legacy:
        legacy_path.write_text(json.dumps(annotation, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return canonical_path, legacy_path


def _run_tagged_ortho(
    tmp_path: Path,
    audio_path: Path,
    *,
    ortho_response_builder: Callable[..., Any] = build_post_run_ortho_response,
    **extra_dependencies: Any,
):
    return build_post_lexemes_rerun_by_tag_response(
        {
            "speakers": ["Saha01"],
            "tagLabels": ["Thesis"],
            "field": "ortho",
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
        run_ortho_interval=lambda **kwargs: f"RERUN_TEXT_{kwargs['start'] + 0.2:.1f}_{kwargs['end'] - 0.2:.1f}",
        run_ipa_interval=lambda **kwargs: "",
        build_post_run_ortho_response=ortho_response_builder,
        build_post_run_ipa_response=lambda *a, **kw: None,
        locks_dir=tmp_path / ".parse-locks",
        pick_lexeme_word=annotate._pick_lexeme_word_for_concept,
        **extra_dependencies,
    )


def _ortho_by_window(annotation_path: Path) -> dict[tuple[float, float], str]:
    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    return {
        (round(float(iv["start"]), 3), round(float(iv["end"]), 3)): iv["text"]
        for iv in persisted["tiers"]["ortho"]["intervals"]
    }


def _ortho_words(annotation_path: Path) -> list[dict[str, Any]]:
    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    return list(persisted["tiers"]["ortho_words"]["intervals"])


def _split_words(_audio_path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        tokens = str(row["text"]).split("_")
        start = float(row["start"])
        end = float(row["end"])
        step = (end - start) / max(len(tokens), 1)
        for idx, token in enumerate(tokens):
            out.append(
                {
                    "start": start + idx * step,
                    "end": start + (idx + 1) * step,
                    "text": token,
                    "source": "test-aligner",
                }
            )
    return out


def test_rerun_by_tag_response_forwards_typed_confidence_triplet(tmp_path: Path) -> None:
    _seed_concepts_csv(tmp_path)
    audio_path = _seed_audio(tmp_path)
    _annotation_path, _legacy_path = _seed_annotation(tmp_path)

    response = build_post_lexemes_rerun_by_tag_response(
        {
            "speakers": ["Saha01"],
            "tagLabels": ["Thesis"],
            "field": "ortho",
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
        run_ortho_interval=lambda **kwargs: {
            "text": f"RERUN_TEXT_{kwargs['start'] + 0.2:.1f}_{kwargs['end'] - 0.2:.1f}",
            "confidence": ConfidenceScore(value=0.42, source="constant_fallback", n_tokens=0),
        },
        run_ipa_interval=lambda **kwargs: "",
        build_post_run_ortho_response=build_post_run_ortho_response,
        build_post_run_ipa_response=lambda *a, **kw: None,
        locks_dir=tmp_path / ".parse-locks",
    )

    assert response.status == HTTPStatus.OK
    first = response.payload["results"][0]
    assert first["confidence"] == 0.42
    assert first["confidence_source"] == "constant_fallback"
    assert first["confidence_n_tokens"] == 0


def test_rerun_by_tag_rebuilds_ortho_words_for_successful_windows(tmp_path: Path) -> None:
    """Tagged-only ORTH persistence must refresh word-click targets inside rerun windows only."""
    _seed_concepts_csv(tmp_path)
    audio_path = _seed_audio(tmp_path)
    annotation_path, _legacy_path = _seed_annotation(tmp_path)
    before_words = _ortho_words(annotation_path)
    outside_before = [iv for iv in before_words if float(iv["end"]) <= 1.0 or float(iv["start"]) >= 4.0]

    response = _run_tagged_ortho(tmp_path, audio_path, align_ortho_words=_split_words)

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"]["ok"] == 2
    after_words = _ortho_words(annotation_path)
    inside_first = [iv["text"] for iv in after_words if 1.0 <= float(iv["start"]) and float(iv["end"]) <= 2.0]
    assert "_".join(inside_first) == "RERUN_TEXT_1.0_2.0"
    outside_after = [iv for iv in after_words if float(iv["end"]) <= 1.0 or float(iv["start"]) >= 4.0]
    assert outside_after == outside_before



def test_rerun_by_tag_writes_picked_lexeme_to_ortho_tier(tmp_path: Path) -> None:
    _seed_concepts_csv(tmp_path)
    audio_path = _seed_audio(tmp_path)
    annotation_path, _legacy_path = _seed_annotation(tmp_path)

    def align_words(_audio_path: Path, _rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"start": 1.0, "end": 1.3, "text": "the", "source": "test-aligner"},
            {"start": 1.35, "end": 1.65, "text": "hair", "source": "test-aligner"},
            {"start": 1.7, "end": 2.0, "text": "is", "source": "test-aligner"},
            {"start": 3.0, "end": 3.3, "text": "a", "source": "test-aligner"},
            {"start": 3.35, "end": 3.65, "text": "leaf", "source": "test-aligner"},
            {"start": 3.7, "end": 4.0, "text": "there", "source": "test-aligner"},
        ]

    response = _run_tagged_ortho(tmp_path, audio_path, align_ortho_words=align_words)

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"]["ok"] == 2
    assert _ortho_by_window(annotation_path) == {
        (1.0, 2.0): "hair",
        (3.0, 4.0): "leaf",
    }
    assert [iv["text"] for iv in _ortho_words(annotation_path) if iv["source"] == "test-aligner"] == [
        "the",
        "hair",
        "is",
        "a",
        "leaf",
        "there",
    ]

def test_rerun_by_tag_handles_ortho_word_align_failure_gracefully(tmp_path: Path) -> None:
    """Tagged-only ORTH must persist text even when secondary word alignment fails."""
    _seed_concepts_csv(tmp_path)
    audio_path = _seed_audio(tmp_path)
    annotation_path, _legacy_path = _seed_annotation(tmp_path)
    before_words = _ortho_words(annotation_path)

    def fail_align(_audio_path: Path, _rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise RuntimeError("wav2vec2 unavailable")

    response = _run_tagged_ortho(tmp_path, audio_path, align_ortho_words=fail_align)

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"]["ok"] == 2
    by_window = _ortho_by_window(annotation_path)
    assert by_window[(1.0, 2.0)].startswith("RERUN_TEXT"), by_window
    assert by_window[(3.0, 4.0)].startswith("RERUN_TEXT"), by_window
    assert _ortho_words(annotation_path) == before_words


def test_rerun_by_tag_loop_persists_text_to_annotation_file(tmp_path: Path) -> None:
    """Ortho transcripts produced by tagged-only batch must hit disk."""
    _seed_concepts_csv(tmp_path)
    audio_path = _seed_audio(tmp_path)
    annotation_path, _legacy_path = _seed_annotation(tmp_path)

    response = _run_tagged_ortho(tmp_path, audio_path)

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"]["ok"] == 2

    by_window = _ortho_by_window(annotation_path)
    assert by_window[(1.0, 2.0)].startswith("RERUN_TEXT"), by_window
    assert by_window[(3.0, 4.0)].startswith("RERUN_TEXT"), by_window
    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    assert persisted["metadata"]["modified"] > _OLD_MODIFIED


def test_rerun_by_tag_writes_canonical_and_legacy_mirrors_with_same_metadata(tmp_path: Path) -> None:
    """Production writer must keep .parse.json and legacy .json mirrors synchronized."""
    _seed_concepts_csv(tmp_path)
    audio_path = _seed_audio(tmp_path)
    canonical_path, legacy_path = _seed_annotation(tmp_path, include_legacy=True)

    def write_both(_speaker: str, annotation_path: Path, record: dict[str, Any]) -> None:
        annotate._write_annotation_to_canonical_and_legacy(
            annotation_path,
            canonical_path,
            legacy_path,
            record,
        )

    response = _run_tagged_ortho(
        tmp_path,
        audio_path,
        annotation_writer=write_both,
        annotation_touch_metadata=annotate._annotation_touch_metadata,
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"]["ok"] == 2
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert canonical == legacy
    assert canonical["metadata"]["modified"] > _OLD_MODIFIED
    assert canonical["metadata"]["modified"] == legacy["metadata"]["modified"]
    assert _ortho_by_window(canonical_path)[(1.0, 2.0)].startswith("RERUN_TEXT")
    assert _ortho_by_window(legacy_path)[(3.0, 4.0)].startswith("RERUN_TEXT")


def test_rerun_by_tag_keeps_existing_text_for_failed_windows(tmp_path: Path) -> None:
    """Persisting successful rows must not erase intervals whose rerun failed."""
    _seed_concepts_csv(tmp_path)
    audio_path = _seed_audio(tmp_path)
    annotation_path, _legacy_path = _seed_annotation(tmp_path)

    def fail_first_concept(body: dict[str, Any], **_kwargs: Any) -> JsonResponseSpec:
        if body["concept_key"] == "1":
            raise LexemeRerunHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, "gpu died")
        return JsonResponseSpec(
            status=HTTPStatus.OK,
            payload={"ortho": f"RERUN_TEXT_{body['start']:.1f}_{body['end']:.1f}"},
        )

    response = _run_tagged_ortho(
        tmp_path,
        audio_path,
        ortho_response_builder=fail_first_concept,
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"] == {"ok": 1, "skipped": 0, "error": 1}
    by_window = _ortho_by_window(annotation_path)
    assert by_window[(1.0, 2.0)] == "OLD_HAIR"
    assert by_window[(3.0, 4.0)].startswith("RERUN_TEXT")
