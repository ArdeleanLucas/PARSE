"""Regression tests for IPA language fallback from annotation metadata."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


class _FakeTensor:
    """Minimal torch.Tensor stand-in for full-speaker and concept-window IPA paths."""

    def __init__(self, n: int = 16000 * 10) -> None:
        self._n = n

    def __getitem__(self, key: slice) -> "_FakeTensor":
        start, stop, _ = key.indices(self._n)
        return _FakeTensor(max(0, stop - start))

    def squeeze(self) -> "_FakeTensor":
        return self

    def detach(self) -> "_FakeTensor":
        return self

    def cpu(self) -> "_FakeTensor":
        return self

    def numpy(self):
        import numpy as np

        return np.zeros(self._n, dtype=np.float32)

    def numel(self) -> int:
        return self._n

    @property
    def shape(self):
        return (self._n,)


class _RecordingIpaProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def transcribe_window_structured(self, window, language=None):
        self.calls.append({"window": window, "language": language})
        return {
            "raw_ipa": "IPA_{0}".format(len(self.calls)),
            "model": "test-ipa-provider",
            "model_version": "test",
        }


def _seed_annotation(
    tmp_path: pathlib.Path,
    *,
    speaker: str = "Fail01",
    language_code: str | None = "sdh",
    ortho: list[dict[str, object]] | None = None,
    concept: list[dict[str, object]] | None = None,
) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    metadata: dict[str, object] = {}
    if language_code is not None:
        metadata["language_code"] = language_code
    payload = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": "x.wav",
        "source_audio_duration_sec": 10.0,
        "tiers": {
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": ortho or []},
            "concept": {"type": "interval", "display_order": 3, "intervals": concept or []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": metadata,
    }
    (annotations_dir / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "x.wav").write_bytes(b"RIFFWAVEfmt ")


def _install_provider(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_read_stt_cache", lambda speaker: [])
    provider = _RecordingIpaProvider()
    monkeypatch.setattr(server, "_get_ipa_aligner", lambda: provider)
    from ai import forced_align as fa

    monkeypatch.setattr(fa, "_load_audio_mono_16k", lambda path: _FakeTensor())
    return provider


def test_compute_speaker_ipa_uses_language_code_from_annotation_metadata(tmp_path, monkeypatch):
    provider = _install_provider(tmp_path, monkeypatch)
    _seed_annotation(
        tmp_path,
        language_code="sdh",
        ortho=[{"start": 1.0, "end": 1.5, "text": "سەر"}],
    )

    server._compute_speaker_ipa("job-ipa", {"speaker": "Fail01"})

    assert provider.calls[0]["language"] == "sdh"


def test_compute_speaker_ipa_payload_language_overrides_metadata(tmp_path, monkeypatch):
    provider = _install_provider(tmp_path, monkeypatch)
    _seed_annotation(
        tmp_path,
        language_code="sdh",
        ortho=[{"start": 1.0, "end": 1.5, "text": "سەر"}],
    )

    server._compute_speaker_ipa("job-ipa", {"speaker": "Fail01", "language": "ku"})

    assert provider.calls[0]["language"] == "ku"


def test_compute_speaker_ipa_concept_windows_uses_language_fallback(tmp_path, monkeypatch):
    provider = _install_provider(tmp_path, monkeypatch)
    _seed_annotation(
        tmp_path,
        language_code="sdh",
        concept=[{"start": 1.0, "end": 1.5, "text": "head", "concept_id": "101"}],
    )

    server._compute_speaker_ipa("job-ipa", {"speaker": "Fail01", "run_mode": "concept-windows"})

    assert provider.calls[0]["language"] == "sdh"
