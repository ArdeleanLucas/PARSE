from __future__ import annotations

import json
import pathlib
import sys
from http import HTTPStatus

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


class _CaptureJsonResponse:
    status: HTTPStatus | int | None = None
    payload: object | None = None

    def _send_json(self, status: HTTPStatus | int, payload: object) -> None:
        self.status = status
        self.payload = payload


def test_get_annotation_serves_audio_less_flag_only_for_audio_less_speakers(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    source_index = {
        "speakers": {
            "Lex01": {"source_wavs": [], "audio_less": True},
            "False01": {"source_wavs": [], "audio_less": False},
            "Saha01": {
                "source_wavs": [
                    {
                        "filename": "audio/working/Saha01/working.wav",
                        "duration_sec": 12.0,
                        "is_primary": True,
                    },
                ],
            },
        },
    }
    (tmp_path / "source_index.json").write_text(json.dumps(source_index), encoding="utf-8")
    lexical_record = _base_annotation("Lex01")
    lexical_record["source_audio"] = ""
    lexical_record["metadata"] = {"language_code": "sdh", "audio_less": True}
    metadata_only_record = _base_annotation("Meta01")
    metadata_only_record["source_audio"] = ""
    metadata_only_record["metadata"] = {"language_code": "sdh", "audio_less": True}
    false_index_record = _base_annotation("False01")
    false_index_record["source_audio"] = ""
    false_index_record["metadata"] = {"language_code": "sdh", "audio_less": True}
    normal_record = _base_annotation("Saha01")
    normal_record["source_audio"] = ""
    (annotations_dir / "Lex01.parse.json").write_text(json.dumps(lexical_record), encoding="utf-8")
    (annotations_dir / "Meta01.parse.json").write_text(json.dumps(metadata_only_record), encoding="utf-8")
    (annotations_dir / "False01.parse.json").write_text(json.dumps(false_index_record), encoding="utf-8")
    (annotations_dir / "Saha01.parse.json").write_text(json.dumps(normal_record), encoding="utf-8")

    lexical_response = _CaptureJsonResponse()
    server._api_get_annotation(lexical_response, "Lex01")
    metadata_only_response = _CaptureJsonResponse()
    server._api_get_annotation(metadata_only_response, "Meta01")
    false_index_response = _CaptureJsonResponse()
    server._api_get_annotation(false_index_response, "False01")
    normal_response = _CaptureJsonResponse()
    server._api_get_annotation(normal_response, "Saha01")

    assert lexical_response.status == HTTPStatus.OK
    assert isinstance(lexical_response.payload, dict)
    assert lexical_response.payload["audio_less"] is True
    assert lexical_response.payload["source_audio"] == ""
    assert metadata_only_response.status == HTTPStatus.OK
    assert isinstance(metadata_only_response.payload, dict)
    assert metadata_only_response.payload["audio_less"] is True
    assert false_index_response.status == HTTPStatus.OK
    assert isinstance(false_index_response.payload, dict)
    assert "audio_less" not in false_index_response.payload
    assert normal_response.status == HTTPStatus.OK
    assert isinstance(normal_response.payload, dict)
    assert "audio_less" not in normal_response.payload
    assert normal_response.payload["source_audio"] == "audio/working/Saha01/working.wav"


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


def test_empty_annotation_record_leaves_concept_tags_sidecar_absent() -> None:
    empty = server._annotation_empty_record("Saha01", "audio/raw/Saha01.wav", 12.0, None)

    assert "concept_tags" not in empty


def test_concept_tags_remain_absent_when_missing() -> None:
    normalized = server._normalize_annotation_record(_base_annotation(), "Saha01")

    assert "concept_tags" not in normalized


def test_concept_tags_sidecar_is_omitted_when_all_memberships_normalize_empty() -> None:
    raw = _base_annotation()
    raw["concept_tags"] = {"1": [], "2": "confirmed", "3": [None, 123]}

    normalized = server._normalize_annotation_record(raw, "Saha01")

    assert "concept_tags" not in normalized


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


def test_workflow_concept_tags_are_exclusive_when_confirmed_replaces_problematic() -> None:
    raw = _base_annotation()
    raw["concept_tags"] = {"322": ["custom-sk-concept-list", "problematic", "confirmed"]}

    normalized = server._normalize_annotation_record(raw, "Saha01")

    assert normalized["concept_tags"] == {"322": ["custom-sk-concept-list", "confirmed"]}


def test_workflow_concept_tags_leave_non_workflow_tags_alone() -> None:
    raw = _base_annotation()
    raw["concept_tags"] = {"322": ["custom-sk-concept-list", "problematic"]}

    normalized = server._normalize_annotation_record(raw, "Saha01")

    assert normalized["concept_tags"] == {"322": ["custom-sk-concept-list", "problematic"]}


def test_workflow_concept_tags_are_exclusive_when_review_needed_replaces_confirmed() -> None:
    raw = _base_annotation()
    raw["concept_tags"] = {"322": ["custom-sk-concept-list", "confirmed", "review-needed"]}

    normalized = server._normalize_annotation_record(raw, "Saha01")

    assert normalized["concept_tags"] == {"322": ["custom-sk-concept-list", "review-needed"]}
