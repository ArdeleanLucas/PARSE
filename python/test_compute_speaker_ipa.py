"""Unit tests for _compute_speaker_ipa (ipa_only compute type).

Tier 3: IPA is generated acoustically via wav2vec2 CTC on the speaker's
audio. These tests stub the Aligner + audio loader so they stay hermetic
(no torch, no real model), and verify the server-side wiring:

  - one Aligner invocation per ortho interval with non-empty text
  - overwrite flag semantics
  - skip when aligner returns empty string
  - dispatch through _run_compute_job for the "ipa_only" compute type
  - missing annotation raises
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _StubAligner:
    """Returns a deterministic marker so tests can assert exact output."""

    def __init__(self) -> None:
        self.calls: list = []

    def transcribe_window(self, window) -> str:
        self.calls.append(window)
        # Include the call index so tests can distinguish intervals.
        return "IPA_{0}".format(len(self.calls))


class _EmptyAligner:
    def __init__(self) -> None:
        self.calls: list = []

    def transcribe_window(self, window) -> str:
        self.calls.append(window)
        return ""


class _FakeTensor:
    """Minimal torch.Tensor stand-in for the slicing path in transcribe_slice."""

    def __init__(self, n: int = 16000 * 60) -> None:
        self._n = n

    def __getitem__(self, key: slice) -> "_FakeTensor":
        start, stop, _ = key.indices(self._n)
        return _FakeTensor(max(0, stop - start))

    def numel(self) -> int:
        return self._n

    @property
    def shape(self):
        return (self._n,)


def _seed_annotation(tmp_path: pathlib.Path, speaker: str, ortho: list, ipa: list):
    (tmp_path / "annotations").mkdir(exist_ok=True)
    annotation = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": "x.wav",
        "source_audio_duration_sec": 10.0,
        "tiers": {
            "ipa":     {"type": "interval", "display_order": 1, "intervals": ipa},
            "ortho":   {"type": "interval", "display_order": 2, "intervals": ortho},
            "concept": {"type": "interval", "display_order": 3, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "sdh", "created": "2026-01-01T00:00:00Z", "modified": "2026-01-01T00:00:00Z"},
    }
    (tmp_path / "annotations" / f"{speaker}.parse.json").write_text(
        json.dumps(annotation), encoding="utf-8",
    )
    (tmp_path / "x.wav").write_bytes(b"RIFFWAVEfmt ")  # faux header; audio loader is stubbed
    return annotation


def _load_canonical(tmp_path: pathlib.Path, speaker: str) -> dict:
    return json.loads((tmp_path / "annotations" / f"{speaker}.parse.json").read_text("utf-8"))


def _install_stubs(monkeypatch, tmp_path: pathlib.Path, aligner) -> None:
    """Point server at tmp_path + stub the aligner + audio loader."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_get_ipa_aligner", lambda: aligner)
    from ai import forced_align as fa
    monkeypatch.setattr(fa, "_load_audio_mono_16k", lambda path: _FakeTensor())


def test_fills_empty_ipa_slots_from_audio(tmp_path, monkeypatch):
    aligner = _StubAligner()
    _install_stubs(monkeypatch, tmp_path, aligner)

    ortho = [
        {"start": 1.0, "end": 1.5, "text": "hair"},
        {"start": 2.0, "end": 2.5, "text": "forehead"},
        {"start": 3.0, "end": 3.5, "text": ""},   # empty ortho — skipped (no audio call)
    ]
    ipa = [{"start": 1.0, "end": 1.5, "text": ""}]  # one empty slot; second absent
    _seed_annotation(tmp_path, "Fail02", ortho, ipa)

    result = server._compute_speaker_ipa("j1", {"speaker": "Fail02"})
    assert result["filled"] == 2
    assert result["skipped"] == 1
    assert result["total"] == 3

    ann = _load_canonical(tmp_path, "Fail02")
    ipa_by_start = {round(i["start"], 3): i["text"] for i in ann["tiers"]["ipa"]["intervals"]}
    assert ipa_by_start[1.0] == "IPA_1"
    assert ipa_by_start[2.0] == "IPA_2"
    # Empty-ortho interval must not trigger an aligner call.
    assert len(aligner.calls) == 2


def test_preserves_existing_ipa_unless_overwrite(tmp_path, monkeypatch):
    aligner = _StubAligner()
    _install_stubs(monkeypatch, tmp_path, aligner)

    ortho = [{"start": 1.0, "end": 1.5, "text": "hair"}]
    ipa = [{"start": 1.0, "end": 1.5, "text": "manual-keep"}]
    _seed_annotation(tmp_path, "Fail02", ortho, ipa)

    result = server._compute_speaker_ipa("j1", {"speaker": "Fail02"})
    assert result["filled"] == 0
    assert result["skipped"] == 1
    ann = _load_canonical(tmp_path, "Fail02")
    assert ann["tiers"]["ipa"]["intervals"][0]["text"] == "manual-keep"
    assert aligner.calls == []  # existing IPA short-circuits before audio call


def test_overwrite_true_replaces_existing_ipa(tmp_path, monkeypatch):
    aligner = _StubAligner()
    _install_stubs(monkeypatch, tmp_path, aligner)

    ortho = [{"start": 1.0, "end": 1.5, "text": "hair"}]
    ipa = [{"start": 1.0, "end": 1.5, "text": "manual-keep"}]
    _seed_annotation(tmp_path, "Fail02", ortho, ipa)

    result = server._compute_speaker_ipa("j1", {"speaker": "Fail02", "overwrite": True})
    assert result["filled"] == 1
    ann = _load_canonical(tmp_path, "Fail02")
    assert ann["tiers"]["ipa"]["intervals"][0]["text"] == "IPA_1"


def test_run_compute_job_dispatches_ipa_only(tmp_path, monkeypatch):
    """_run_compute_job should route compute_type='ipa_only' to _compute_speaker_ipa."""
    _install_stubs(monkeypatch, tmp_path, _StubAligner())
    _seed_annotation(
        tmp_path, "Fail02",
        [{"start": 1.0, "end": 1.5, "text": "hair"}], [],
    )

    captured: dict = {}

    def fake_complete(job_id, result, **kwargs):
        captured["result"] = result

    def fake_error(job_id, err):
        captured["error"] = err

    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_set_job_complete", fake_complete)
    monkeypatch.setattr(server, "_set_job_error", fake_error)

    server._run_compute_job("j1", "ipa_only", {"speaker": "Fail02"})
    assert "error" not in captured
    assert captured["result"]["filled"] == 1

    # Also try the hyphenated alias.
    captured.clear()
    _seed_annotation(
        tmp_path, "Fail03",
        [{"start": 2.0, "end": 2.5, "text": "ash"}], [],
    )
    server._run_compute_job("j2", "ipa-only", {"speaker": "Fail03"})
    assert captured["result"]["filled"] == 1


def test_missing_annotation_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    import pytest

    with pytest.raises(RuntimeError, match="No annotation"):
        server._compute_speaker_ipa("j1", {"speaker": "GhostSpeaker"})


def test_skips_when_aligner_returns_empty(tmp_path, monkeypatch):
    aligner = _EmptyAligner()
    _install_stubs(monkeypatch, tmp_path, aligner)
    _seed_annotation(
        tmp_path, "Fail02",
        [{"start": 1.0, "end": 1.5, "text": "hair"}], [],
    )
    result = server._compute_speaker_ipa("j1", {"speaker": "Fail02"})
    assert result["filled"] == 0
    assert result["skipped"] == 1
    assert len(aligner.calls) == 1  # audio *was* tried; just produced nothing
