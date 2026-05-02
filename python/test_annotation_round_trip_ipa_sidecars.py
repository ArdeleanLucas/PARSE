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
