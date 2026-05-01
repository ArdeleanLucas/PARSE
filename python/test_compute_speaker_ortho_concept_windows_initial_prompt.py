"""Prompt-safety regression tests for ORTH concept-window transcription."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

pytest.importorskip("numpy")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


class _PromptRecordingProvider:
    def __init__(self) -> None:
        self.clip_calls: list[dict[str, object]] = []

    def transcribe(self, *args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("concept-window ORTH must not call full-file transcribe")

    def transcribe_clip(self, audio_array, *, initial_prompt=None, language=None):
        call_index = len(self.clip_calls) + 1
        self.clip_calls.append({"initial_prompt": initial_prompt, "language": language})
        return (f"window-{call_index}", 0.8)


class _CancellingConceptWindowProvider(_PromptRecordingProvider):
    def __init__(self, job_id: str) -> None:
        super().__init__()
        self.job_id = job_id

    def transcribe_clip(self, audio_array, *, initial_prompt=None, language=None):
        result = super().transcribe_clip(audio_array, initial_prompt=initial_prompt, language=language)
        if len(self.clip_calls) == 2:
            from ai.job_cancel import request_cancel

            request_cancel(self.job_id)
        return result


class _CancellingFullProvider:
    refine_lexemes = False

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.transcribe_calls: list[dict[str, object]] = []

    def transcribe(self, *args, **kwargs):
        from ai.job_cancel import request_cancel

        self.transcribe_calls.append(kwargs)
        should_cancel = kwargs.get("should_cancel")
        assert callable(should_cancel)
        request_cancel(self.job_id)
        return [
            {"start": 0.0, "end": 1.0, "text": "full-one", "confidence": 0.9},
            {"start": 1.0, "end": 2.0, "text": "full-two", "confidence": 0.8},
        ]

    def transcribe_clip(self, *args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("full ORTH must not call transcribe_clip")


def _seed_annotation(tmp_path: pathlib.Path, *, concept_count: int = 2) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    concept_intervals = [
        {"start": float(idx + 1), "end": float(idx + 1) + 0.3, "text": f"concept-{idx + 1}"}
        for idx in range(concept_count)
    ]
    payload = {
        "version": 1,
        "project_id": "t",
        "speaker": "Fail01",
        "source_audio": "raw/Fail01.wav",
        "source_audio_duration_sec": 10.0,
        "tiers": {
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": concept_intervals,
            },
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "ku"},
    }
    (annotations_dir / "Fail01.parse.json").write_text(json.dumps(payload), encoding="utf-8")
    audio_path = tmp_path / "raw" / "Fail01.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")


def _patch_audio_loader(monkeypatch, duration_sec: float = 5.0) -> None:
    import numpy as np
    import ai.forced_align as forced_align

    fake_audio = np.zeros(int(duration_sec * 16000), dtype=np.float32)
    monkeypatch.setattr(forced_align, "_load_audio_mono_16k", lambda _path: fake_audio)


def _patch_server_for_ortho_test(monkeypatch, tmp_path: pathlib.Path, provider: object) -> None:
    # Route bindings must be installed before monkeypatching server exports;
    # otherwise monkeypatch restores the lazy shim after installation and later
    # route-module tests can recurse through server._set_job_progress.
    server._install_route_bindings()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: provider)


def test_ortho_concept_windows_drops_english_gloss_initial_prompt(tmp_path, monkeypatch):
    provider = _PromptRecordingProvider()
    _patch_server_for_ortho_test(monkeypatch, tmp_path, provider)
    _patch_audio_loader(monkeypatch)
    _seed_annotation(tmp_path)

    result = server._compute_speaker_ortho(
        "job-ortho",
        {"speaker": "Fail01", "run_mode": "concept-windows", "overwrite": True},
    )

    assert result["filled"] == 2
    assert len(provider.clip_calls) == 2
    assert all(call["language"] == "ku" for call in provider.clip_calls)
    assert all(call["initial_prompt"] is None for call in provider.clip_calls)


def test_ortho_concept_windows_cancellation_persists_partial_rows_and_clears_flag(tmp_path, monkeypatch):
    from ai.job_cancel import clear_cancel, is_cancelled

    job_id = "job-ortho-concept-cancel"
    provider = _CancellingConceptWindowProvider(job_id)
    _patch_server_for_ortho_test(monkeypatch, tmp_path, provider)
    _patch_audio_loader(monkeypatch, duration_sec=10.0)
    _seed_annotation(tmp_path, concept_count=5)
    clear_cancel(job_id)

    result = server._compute_speaker_ortho(
        job_id,
        {"speaker": "Fail01", "run_mode": "concept-windows", "overwrite": True},
    )

    assert result["status"] == "partial_cancelled"
    assert result["cancelled_at_interval"] == 2
    assert result["filled"] == 2
    assert result["concept_windows"] == 5
    assert len(provider.clip_calls) == 2
    assert is_cancelled(job_id) is False
    annotation = json.loads((tmp_path / "annotations" / "Fail01.parse.json").read_text(encoding="utf-8"))
    assert [row["text"] for row in annotation["tiers"]["ortho"]["intervals"]] == ["window-1", "window-2"]


def test_ortho_full_cancellation_persists_partial_segments_and_skips_tier2(tmp_path, monkeypatch):
    from ai.job_cancel import clear_cancel, is_cancelled

    job_id = "job-ortho-full-cancel"
    provider = _CancellingFullProvider(job_id)
    _patch_server_for_ortho_test(monkeypatch, tmp_path, provider)
    monkeypatch.setattr(server, "_pipeline_audio_path_for_speaker", lambda speaker: tmp_path / "raw" / f"{speaker}.wav")

    def fail_tier2(*args, **kwargs):  # pragma: no cover - should not be reached
        raise AssertionError("cancelled ORTH must not continue into Tier-2 alignment")

    monkeypatch.setattr(server, "_ortho_tier2_align_to_words", fail_tier2)
    _seed_annotation(tmp_path, concept_count=2)
    clear_cancel(job_id)

    result = server._compute_speaker_ortho(
        job_id,
        {"speaker": "Fail01", "run_mode": "full", "overwrite": True},
    )

    assert result["status"] == "partial_cancelled"
    assert result["cancelled_at_interval"] == 2
    assert result["filled"] == 2
    assert result["ortho_words"] == 0
    assert result["refined_lexemes"] == 0
    assert is_cancelled(job_id) is False
    annotation = json.loads((tmp_path / "annotations" / "Fail01.parse.json").read_text(encoding="utf-8"))
    assert [row["text"] for row in annotation["tiers"]["ortho"]["intervals"]] == ["full-one", "full-two"]
