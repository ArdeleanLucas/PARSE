from __future__ import annotations

import json
import pathlib
import sys

import pytest

pytest.importorskip("numpy")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402


class _StructuredAligner:
    def __init__(self, raw_ipa: str = "  ðæɚ oʊ  ") -> None:
        self.calls: list[object] = []
        self.raw_ipa = raw_ipa

    def transcribe_window(self, window) -> str:
        self.calls.append(window)
        return self.raw_ipa.strip()

    def transcribe_window_structured(self, window) -> dict[str, object]:
        self.calls.append(window)
        return {
            "raw_ipa": self.raw_ipa,
            "model": "wav2vec2-xlsr-53-espeak-cv-ft",
            "model_version": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
            "decoded_at": "2026-05-02T12:00:00Z",
        }


def _seed_annotation(tmp_path: pathlib.Path, *, speaker: str = "Saha01") -> None:
    (tmp_path / "annotations").mkdir(parents=True, exist_ok=True)
    (tmp_path / "audio" / "raw").mkdir(parents=True, exist_ok=True)
    (tmp_path / "audio" / "raw" / "Saha01.wav").write_bytes(b"RIFFWAVEfake")
    payload = {
        "version": 1,
        "project_id": "parse-test",
        "speaker": speaker,
        "source_audio": "audio/raw/Saha01.wav",
        "source_audio_duration_sec": 8.0,
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [{"start": 1.0, "end": 1.2, "text": "head", "concept_id": "101"}],
            },
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "sdh"},
    }
    (tmp_path / "annotations" / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")


def test_compute_speaker_ipa_concept_windows_appends_verbatim_candidate_sidecar(tmp_path: pathlib.Path, monkeypatch) -> None:
    import numpy as np
    import ai.forced_align as forced_align

    aligner = _StructuredAligner()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_get_ipa_aligner", lambda: aligner)
    monkeypatch.setattr(forced_align, "_load_audio_mono_16k", lambda _path: np.zeros(8 * 16000, dtype=np.float32))
    _seed_annotation(tmp_path)

    result = server._compute_speaker_ipa(
        "job-ipa",
        {"speaker": "Saha01", "run_mode": "concept-windows", "overwrite": True},
    )

    assert result["filled"] == 1
    assert len(aligner.calls) == 1
    annotation = json.loads((tmp_path / "annotations" / "Saha01.parse.json").read_text("utf-8"))
    assert annotation["tiers"]["ipa"]["intervals"][0]["text"] == "ðæɚ oʊ"
    candidates = annotation["ipa_candidates"]
    assert set(candidates) == {"101::concept::0"}
    assert len(candidates["101::concept::0"]) == 1
    candidate = candidates["101::concept::0"][0]
    assert candidate["candidate_id"].startswith("cand_xlsr_")
    assert candidate["model"] == "wav2vec2-xlsr-53-espeak-cv-ft"
    assert candidate["model_version"] == "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
    assert candidate["raw_ipa"] == "  ðæɚ oʊ  "
    assert candidate["decoded_at"] == "2026-05-02T12:00:00Z"
    assert candidate["timing_basis"] == "audition_cue"
    assert candidate["confidence"] is None
