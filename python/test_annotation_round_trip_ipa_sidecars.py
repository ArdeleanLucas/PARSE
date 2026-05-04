from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402


def _base_annotation(speaker: str = "Saha01") -> dict[str, object]:
    return {
        "version": 1,
        "project_id": "parse-test",
        "speaker": speaker,
        "source_audio": "audio/raw/Saha01.wav",
        "source_audio_duration_sec": 12.0,
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [
                    {"start": 1.0, "end": 1.5, "text": "head", "concept_id": "101"},
                ],
            },
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "confirmed_anchors": {},
        "metadata": {"language_code": "sdh", "created": "2026-05-02T00:00:00Z", "modified": "2026-05-02T00:00:00Z"},
    }


def test_ipa_sidecars_round_trip_through_annotation_normalizer_and_json_save(tmp_path: pathlib.Path) -> None:
    key = "101::concept::0"
    candidate = {
        "candidate_id": "cand_xlsr_deadbeef",
        "model": "wav2vec2-xlsr-53-espeak-cv-ft",
        "model_version": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
        "raw_ipa": "  ðæɚ oʊ  ",
        "decoded_at": "2026-05-02T12:00:00Z",
        "timing_basis": "audition_cue",
        "confidence": None,
    }
    review_state = {
        "status": "accepted",
        "suggested_ipa": "dær",
        "resolution_type": "manual",
        "evidence_sources": ["speaker-review"],
        "notes": "accepted by fieldworker",
    }
    raw = _base_annotation()
    raw["ipa_candidates"] = {key: [candidate]}
    raw["ipa_review"] = {key: review_state}

    normalized = server._normalize_annotation_record(raw, "Saha01")

    assert normalized["ipa_candidates"] == {key: [candidate]}
    assert normalized["ipa_review"] == {key: review_state}

    path = tmp_path / "annotations" / "Saha01.parse.json"
    server._write_json_file(path, normalized)
    loaded = json.loads(path.read_text("utf-8"))
    reloaded = server._normalize_annotation_record(loaded, "Saha01")

    assert reloaded["ipa_candidates"] == {key: [candidate]}
    assert reloaded["ipa_review"] == {key: review_state}
    assert reloaded["ipa_candidates"][key][0]["timing_basis"] == "audition_cue"
    assert reloaded["ipa_candidates"][key][0]["raw_ipa"] == "  ðæɚ oʊ  "


def test_ipa_sidecars_remain_absent_when_missing() -> None:
    normalized = server._normalize_annotation_record(_base_annotation(), "Saha01")

    assert "ipa_candidates" not in normalized
    assert "ipa_review" not in normalized


def test_empty_annotation_record_includes_concept_tags_sidecar() -> None:
    empty = server._annotation_empty_record("Saha01", "audio/raw/Saha01.wav", 12.0, None)

    assert empty["concept_tags"] == {}


def test_concept_tags_round_trip_through_annotation_normalizer_and_json_save(tmp_path: pathlib.Path) -> None:
    concept_tags = {"1": ["confirmed"], "2": ["review", "problematic"]}
    raw = _base_annotation()
    raw["concept_tags"] = concept_tags

    normalized = server._normalize_annotation_record(raw, "Saha01")

    assert normalized["concept_tags"] == concept_tags

    path = tmp_path / "annotations" / "Saha01.parse.json"
    server._write_json_file(path, normalized)
    loaded = json.loads(path.read_text("utf-8"))
    reloaded = server._normalize_annotation_record(loaded, "Saha01")

    assert reloaded["concept_tags"] == concept_tags


def test_concept_tags_normalization_drops_empty_memberships() -> None:
    raw = _base_annotation()
    raw["concept_tags"] = {"1": [], "2": ["confirmed"]}

    normalized = server._normalize_annotation_record(raw, "Saha01")

    assert normalized["concept_tags"] == {"2": ["confirmed"]}


def test_concept_tags_normalization_coerces_keys_and_deduplicates_tag_lists() -> None:
    raw = _base_annotation()
    raw["concept_tags"] = {
        1: ["confirmed", "review", "confirmed"],
        "2": "confirmed",
        "3": [123, "problematic", "problematic"],
        "4": [None],
    }

    normalized = server._normalize_annotation_record(raw, "Saha01")

    assert normalized["concept_tags"] == {"1": ["confirmed", "review"], "3": ["problematic"]}


def test_concept_tags_are_speaker_local_on_disk(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    speaker_a = _base_annotation("Saha01")
    speaker_a["concept_tags"] = {"1": ["confirmed"]}
    speaker_b = _base_annotation("Saha02")
    speaker_b["source_audio"] = "audio/raw/Saha02.wav"
    speaker_b["concept_tags"] = {"1": ["problematic"], "2": ["review"]}

    path_a = server._annotation_record_path_for_speaker("Saha01")
    path_b = server._annotation_record_path_for_speaker("Saha02")
    server._write_json_file(path_a, server._normalize_annotation_record(speaker_a, "Saha01"))
    server._write_json_file(path_b, server._normalize_annotation_record(speaker_b, "Saha02"))

    speaker_a["concept_tags"] = {"1": ["confirmed", "review"]}
    server._write_json_file(path_a, server._normalize_annotation_record(speaker_a, "Saha01"))

    reloaded_a = json.loads(path_a.read_text("utf-8"))
    reloaded_b = json.loads(path_b.read_text("utf-8"))

    assert reloaded_a["concept_tags"] == {"1": ["confirmed", "review"]}
    assert reloaded_b["concept_tags"] == {"1": ["problematic"], "2": ["review"]}
