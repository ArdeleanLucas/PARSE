"""Regression tests for concept-scoped acoustic IPA compute modes."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

pytest.importorskip("numpy")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


class _StubAligner:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def transcribe_window(self, window) -> str:
        self.calls.append(window)
        return f"IPA_WINDOW_{len(self.calls)}"


def _seed_annotation(
    tmp_path: pathlib.Path,
    *,
    speaker: str = "Fail02",
    concept_intervals: list[dict[str, object]] | None = None,
    ipa_intervals: list[dict[str, object]] | None = None,
    source_audio: str = "raw/Fail02.wav",
) -> None:
    (tmp_path / "annotations").mkdir(exist_ok=True)
    payload = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": 8.0,
        "tiers": {
            "concept": {"type": "interval", "display_order": 3, "intervals": concept_intervals or []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "ipa": {"type": "interval", "display_order": 1, "intervals": ipa_intervals or []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "sdh"},
    }
    (tmp_path / "annotations" / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")
    audio_path = tmp_path / source_audio
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFFWAVEfake")


def _patch_runtime(monkeypatch, tmp_path: pathlib.Path, aligner: _StubAligner, duration_sec: float = 8.0) -> None:
    import numpy as np
    import ai.forced_align as forced_align

    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_get_ipa_aligner", lambda: aligner)
    fake_audio = np.zeros(int(duration_sec * 16000), dtype=np.float32)
    monkeypatch.setattr(forced_align, "_load_audio_mono_16k", lambda _path: fake_audio)


def _load_annotation(tmp_path: pathlib.Path, speaker: str = "Fail02") -> dict[str, object]:
    return json.loads((tmp_path / "annotations" / f"{speaker}.parse.json").read_text("utf-8"))


def test_compute_speaker_ipa_concept_windows_writes_only_matching_concept_rows(tmp_path, monkeypatch):
    aligner = _StubAligner()
    _patch_runtime(monkeypatch, tmp_path, aligner)
    _seed_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2"},
        ],
        ipa_intervals=[{"start": 6.0, "end": 6.5, "text": "manual-outside"}],
    )

    result = server._compute_speaker_ipa(
        "job-ipa",
        {"speaker": "Fail02", "run_mode": "concept-windows", "overwrite": True},
    )

    assert result["run_mode"] == "concept-windows"
    assert result["concept_windows"] == 2
    assert result["filled"] == 2
    assert len(aligner.calls) == 2

    annotation = _load_annotation(tmp_path)
    ipa = annotation["tiers"]["ipa"]["intervals"]
    assert [(row["start"], row["end"], row["text"], row.get("conceptId")) for row in ipa] == [
        (1.0, 1.2, "IPA_WINDOW_1", "1"),
        (2.0, 2.4, "IPA_WINDOW_2", "2"),
        (6.0, 6.5, "manual-outside", None),
    ]


def test_compute_speaker_ipa_edited_only_filters_to_manually_adjusted_concepts(tmp_path, monkeypatch):
    aligner = _StubAligner()
    _patch_runtime(monkeypatch, tmp_path, aligner)
    _seed_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2", "manuallyAdjusted": True},
            {"start": 4.0, "end": 4.5, "text": "3"},
        ],
    )

    result = server._compute_speaker_ipa(
        "job-ipa",
        {"speaker": "Fail02", "run_mode": "edited-only", "overwrite": True},
    )

    assert result["run_mode"] == "edited-only"
    assert result["concept_windows"] == 1
    assert result["filled"] == 1
    assert len(aligner.calls) == 1
    annotation = _load_annotation(tmp_path)
    assert [(row["conceptId"], row["text"]) for row in annotation["tiers"]["ipa"]["intervals"]] == [
        ("2", "IPA_WINDOW_1"),
    ]


def test_compute_speaker_ipa_edited_only_empty_is_structured_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        server,
        "_get_ipa_aligner",
        lambda: (_ for _ in ()).throw(AssertionError("edited-only empty must not load IPA aligner")),
    )
    _seed_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2"},
        ],
    )

    result = server._compute_speaker_ipa(
        "job-ipa",
        {"speaker": "Fail02", "run_mode": "edited-only"},
    )

    assert result["run_mode"] == "edited-only"
    assert result["skipped"] is True
    assert result["no_op"] is True
    assert result["concept_windows"] == 0
    assert "No edited concepts" in result["reason"]
    annotation = _load_annotation(tmp_path)
    assert annotation["tiers"]["ipa"]["intervals"] == []
