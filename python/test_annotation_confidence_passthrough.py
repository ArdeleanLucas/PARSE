from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402


def _base_annotation(interval: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "project_id": "parse-test",
        "speaker": "Saha01",
        "source_audio": "audio/raw/Saha01.wav",
        "source_audio_duration_sec": 12.0,
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [{"start": 1.0, "end": 1.5, "text": "head", "concept_id": "101"}],
            },
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": [interval]},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "confirmed_anchors": {},
        "metadata": {"language_code": "sdh", "created": "2026-05-17T00:00:00Z", "modified": "2026-05-17T00:00:00Z"},
    }


def test_annotation_confidence_triplet_round_trips_through_normalizer_and_json_save(tmp_path: pathlib.Path) -> None:
    interval = {
        "start": 1.0,
        "end": 1.5,
        "text": "یەک",
        "confidence": 0.51,
        "confidence_source": "avg_logprob",
        "confidence_n_tokens": 4,
    }
    normalized = server._normalize_annotation_record(_base_annotation(interval), "Saha01")
    saved_interval = normalized["tiers"]["ortho"]["intervals"][0]

    assert saved_interval["confidence"] == 0.51
    assert saved_interval["confidence_source"] == "avg_logprob"
    assert saved_interval["confidence_n_tokens"] == 4

    path = tmp_path / "annotations" / "Saha01.parse.json"
    server._write_json_file(path, normalized)
    loaded = json.loads(path.read_text("utf-8"))
    reloaded = server._normalize_annotation_record(loaded, "Saha01")
    reloaded_interval = reloaded["tiers"]["ortho"]["intervals"][0]

    assert reloaded_interval["confidence"] == 0.51
    assert reloaded_interval["confidence_source"] == "avg_logprob"
    assert reloaded_interval["confidence_n_tokens"] == 4

    for overrides in (
        {"confidence": 1.01},
        {"confidence_source": "unknown_source"},
        {"confidence_n_tokens": -1},
    ):
        bad_interval = dict(interval)
        bad_interval.update(overrides)
        bad_normalized = server._normalize_annotation_record(_base_annotation(bad_interval), "Saha01")
        bad_saved_interval = bad_normalized["tiers"]["ortho"]["intervals"][0]
        assert "confidence" not in bad_saved_interval
        assert "confidence_source" not in bad_saved_interval
        assert "confidence_n_tokens" not in bad_saved_interval
