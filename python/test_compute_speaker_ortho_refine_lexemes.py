"""Tests for the ORTH short-clip fallback gated behind refine_lexemes."""
import json
import pathlib
import sys

import pytest

pytest.importorskip("numpy")  # short-clip fallback loads audio via numpy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


class _StubOrthoProvider:
    """Stub provider that also implements transcribe_clip for the fallback."""

    def __init__(self, segments, clip_text: str = "هیر", clip_conf: float = 0.88):
        self._segments = segments
        self._clip_text = clip_text
        self._clip_conf = clip_conf
        self.clip_calls: list[dict] = []
        self.refine_lexemes = False  # provider-level default; job can override

    def transcribe(self, audio_path, language=None, progress_callback=None):
        return list(self._segments)

    def transcribe_clip(self, audio_array, *, initial_prompt=None, language=None):
        self.clip_calls.append({
            "len": int(getattr(audio_array, "shape", [0])[0] or 0),
            "initial_prompt": initial_prompt,
            "language": language,
        })
        return (self._clip_text, self._clip_conf)


def _seed(tmp_path, speaker="Fail02", concept_intervals=None, source_audio="raw/Fail02.wav"):
    ann_dir = tmp_path / "annotations"
    ann_dir.mkdir(exist_ok=True)
    annotation = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": 3.0,
        "tiers": {
            "ipa":     {"type": "interval", "display_order": 1, "intervals": []},
            "ortho":   {"type": "interval", "display_order": 2, "intervals": []},
            "concept": {"type": "interval", "display_order": 3, "intervals": concept_intervals or []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "sdh"},
    }
    (ann_dir / f"{speaker}.parse.json").write_text(json.dumps(annotation), encoding="utf-8")


def _fake_wav(tmp_path, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    return p


def _load(tmp_path, speaker):
    return json.loads((tmp_path / "annotations" / f"{speaker}.parse.json").read_text("utf-8"))


def _patch_audio_loader(monkeypatch, duration_sec: float = 3.0):
    """Replace _load_audio_mono_16k with a synthetic tensor of N samples."""
    import numpy as np
    samples = int(duration_sec * 16000)
    fake_audio = np.zeros(samples, dtype="float32")

    class _FakeTensor:
        def __init__(self, arr):
            self._arr = arr
            self.shape = arr.shape
        def squeeze(self):
            return self
        def numpy(self):
            return self._arr

    import ai.forced_align as fa
    monkeypatch.setattr(fa, "_load_audio_mono_16k", lambda p: _FakeTensor(fake_audio))


def _patch_align(monkeypatch, aligned):
    import ai.forced_align as fa
    monkeypatch.setattr(fa, "align_segments", lambda audio_path, segments, **kw: aligned)


def test_refine_lexemes_disabled_skips_short_clip(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    segments = [{
        "start": 0.0, "end": 2.0, "text": "whole narrative",
        "words": [{"word": "whole", "start": 0.1, "end": 0.9, "prob": 0.8}],
    }]
    stub = _StubOrthoProvider(segments=segments)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)
    _patch_align(monkeypatch, [[
        {"word": "whole", "start": 0.1, "end": 0.9, "confidence": 0.8},
    ]])
    _patch_audio_loader(monkeypatch)

    concepts = [{"start": 1.0, "end": 1.2, "text": "hair"}]
    _seed(tmp_path, concept_intervals=concepts)
    _fake_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho("j", {"speaker": "Fail02"})

    assert result["refine_lexemes_enabled"] is False
    assert result["refined_lexemes"] == 0
    assert stub.clip_calls == []


def test_refine_lexemes_payload_override_enables_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    segments = [{
        "start": 0.0, "end": 2.0, "text": "whole narrative",
        "words": [{"word": "unrelated", "start": 0.0, "end": 0.2, "prob": 0.9}],
    }]
    stub = _StubOrthoProvider(segments=segments)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)
    # Aligned word is outside the concept anchor window → weak/no match →
    # fallback should fire for the "hair" concept at 1.0–1.2s.
    _patch_align(monkeypatch, [[
        {"word": "unrelated", "start": 0.0, "end": 0.2, "confidence": 0.9},
    ]])
    _patch_audio_loader(monkeypatch)

    concepts = [{"start": 1.0, "end": 1.2, "text": "hair"}]
    _seed(tmp_path, concept_intervals=concepts)
    _fake_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho(
        "j", {"speaker": "Fail02", "refine_lexemes": True},
    )

    assert result["refine_lexemes_enabled"] is True
    assert result["refined_lexemes"] == 1
    assert len(stub.clip_calls) == 1
    # Regression guard: English concept IDs/glosses like "hair" must not be
    # fed back to Whisper as an initial_prompt; that biases Razhan away from
    # Arabic-script Kurdish and can trigger prompt-token loops.
    assert stub.clip_calls[0]["initial_prompt"] is None
    assert stub.clip_calls[0]["language"] == "sdh"

    ann = _load(tmp_path, "Fail02")
    words = ann["tiers"]["ortho_words"]["intervals"]
    refined = [w for w in words if w.get("source") == "short_clip_fallback"]
    assert len(refined) == 1
    assert refined[0]["text"] == "هیر"
    assert refined[0]["start"] == pytest.approx(1.0)
    assert refined[0]["end"] == pytest.approx(1.2)


def test_refine_lexemes_strong_match_skipped(tmp_path, monkeypatch):
    """When forced-alignment confidence is already high on a concept span,
    the short-clip fallback must not re-transcribe — it's wasted compute."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    segments = [{
        "start": 0.0, "end": 2.0, "text": "hair",
        "words": [{"word": "hair", "start": 1.0, "end": 1.2, "prob": 0.99}],
    }]
    stub = _StubOrthoProvider(segments=segments)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)
    _patch_align(monkeypatch, [[
        {"word": "hair", "start": 1.0, "end": 1.2, "confidence": 0.95},
    ]])
    _patch_audio_loader(monkeypatch)

    concepts = [{"start": 1.0, "end": 1.2, "text": "hair"}]
    _seed(tmp_path, concept_intervals=concepts)
    _fake_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho(
        "j", {"speaker": "Fail02", "refine_lexemes": True},
    )

    assert result["refine_lexemes_enabled"] is True
    assert result["refined_lexemes"] == 0
    assert stub.clip_calls == []


class _ConceptWindowOrthoProvider:
    def __init__(self) -> None:
        self.clip_calls: list[dict] = []

    def transcribe(self, *args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("concept-window ORTH must not run full-file transcribe")

    def transcribe_clip(self, audio_array, *, initial_prompt=None, language=None):
        call_index = len(self.clip_calls) + 1
        self.clip_calls.append({
            "len": int(getattr(audio_array, "shape", [0])[0] or 0),
            "initial_prompt": initial_prompt,
            "language": language,
        })
        return (f"orth-window-{call_index}", 0.80 + call_index / 100.0)


def _seed_ortho_scoped_annotation(tmp_path, concept_intervals, ortho_intervals=None):
    _seed(tmp_path, concept_intervals=concept_intervals)
    path = tmp_path / "annotations" / "Fail02.parse.json"
    payload = json.loads(path.read_text("utf-8"))
    payload["tiers"]["ortho"]["intervals"] = list(ortho_intervals or [])
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_ortho_concept_windows_uses_shared_short_clip_helper_and_preserves_outside_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    stub = _ConceptWindowOrthoProvider()
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)
    _patch_audio_loader(monkeypatch, duration_sec=6.0)

    _seed_ortho_scoped_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2"},
        ],
        ortho_intervals=[{"start": 5.0, "end": 5.4, "text": "manual-outside"}],
    )
    _fake_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho(
        "j",
        {"speaker": "Fail02", "run_mode": "concept-windows", "overwrite": True, "language": "sd"},
    )

    assert result["run_mode"] == "concept-windows"
    assert result["concept_windows"] == 2
    assert result["filled"] == 2
    assert len(stub.clip_calls) == 2
    assert all(call["language"] == "sd" for call in stub.clip_calls)
    ann = _load(tmp_path, "Fail02")
    rows = ann["tiers"]["ortho"]["intervals"]
    assert [(row["start"], row["end"], row["text"], row.get("conceptId")) for row in rows] == [
        (1.0, 1.2, "orth-window-1", "1"),
        (2.0, 2.4, "orth-window-2", "2"),
        (5.0, 5.4, "manual-outside", None),
    ]


def test_ortho_edited_only_empty_is_structured_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        server,
        "get_ortho_provider",
        lambda: (_ for _ in ()).throw(AssertionError("edited-only empty must not load ORTH provider")),
    )
    _seed_ortho_scoped_annotation(
        tmp_path,
        concept_intervals=[
            {"start": 1.0, "end": 1.2, "text": "1"},
            {"start": 2.0, "end": 2.4, "text": "2"},
        ],
    )
    _fake_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho(
        "j",
        {"speaker": "Fail02", "run_mode": "edited-only"},
    )

    assert result["run_mode"] == "edited-only"
    assert result["skipped"] is True
    assert result["no_op"] is True
    assert result["concept_windows"] == 0
    assert "No edited concepts" in result["reason"]
