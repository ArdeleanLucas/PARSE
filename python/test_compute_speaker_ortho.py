"""Unit tests for _compute_speaker_ortho and the full-pipeline sequencer."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402
from ai.provider import get_ortho_provider  # noqa: E402
from ai.providers.local_whisper import LocalWhisperProvider  # noqa: E402


class _StubOrthoProvider:
    """Returns a fixed set of razhan-style segments so tests can assert exact output."""

    def __init__(self, segments=None):
        # Default segmentation: three intervals, mid-file, Kurdish-ish placeholders.
        self._segments = segments or [
            {"start": 0.5, "end": 1.2, "text": "بەش", "confidence": 0.9},
            {"start": 1.3, "end": 2.0, "text": "سەرە", "confidence": 0.85},
            {"start": 2.1, "end": 2.8, "text": "", "confidence": 0.1},  # empty → dropped
        ]
        self.calls: list[dict] = []

    def transcribe(self, audio_path, language=None, progress_callback=None):
        self.calls.append({"audio_path": str(audio_path), "language": language})
        # Exercise progress callback to mirror the real provider contract.
        if progress_callback is not None:
            progress_callback(50.0, 1)
            progress_callback(100.0, len(self._segments))
        return list(self._segments)


def _seed_annotation(tmp_path, speaker, ortho=None, source_audio="x.wav"):
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    annotation = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": source_audio,
        "source_audio_duration_sec": 10.0,
        "tiers": {
            "ipa":     {"type": "interval", "display_order": 1, "intervals": []},
            "ortho":   {"type": "interval", "display_order": 2, "intervals": ortho or []},
            "concept": {"type": "interval", "display_order": 3, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {
            "language_code": "sdh",
            "created": "2026-01-01T00:00:00Z",
            "modified": "2026-01-01T00:00:00Z",
        },
    }
    (annotations_dir / f"{speaker}.parse.json").write_text(
        json.dumps(annotation), encoding="utf-8",
    )
    return annotation


def _write_fake_source_wav(tmp_path, rel_path):
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")  # not real audio — we stub the provider
    return path


def _load_canonical(tmp_path, speaker):
    return json.loads((tmp_path / "annotations" / f"{speaker}.parse.json").read_text("utf-8"))


def test_ortho_writes_razhan_segments_to_empty_tier(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    stub = _StubOrthoProvider()
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho("j1", {"speaker": "Fail02"})

    assert result["filled"] == 2  # empty segment dropped
    assert result["skipped"] is False
    assert result["replaced_existing"] is False
    assert len(stub.calls) == 1

    ann = _load_canonical(tmp_path, "Fail02")
    intervals = ann["tiers"]["ortho"]["intervals"]
    assert [iv["text"] for iv in intervals] == ["بەش", "سەرە"]
    assert intervals[0]["start"] == pytest.approx(0.5)
    assert intervals[1]["end"] == pytest.approx(2.0)
    # ortho_words tier is always written, even when segments carry no word spans
    assert "ortho_words" in ann["tiers"]
    assert isinstance(ann["tiers"]["ortho_words"]["intervals"], list)



def test_ortho_skips_if_tier_populated_without_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    stub = _StubOrthoProvider()
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)

    existing = [{"start": 5.0, "end": 5.5, "text": "manual-edit"}]
    _seed_annotation(tmp_path, "Fail02", ortho=existing, source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho("j1", {"speaker": "Fail02"})

    assert result["skipped"] is True
    assert result["existing_intervals"] == 1
    # Provider was never invoked — skip happens before model load.
    assert stub.calls == []

    ann = _load_canonical(tmp_path, "Fail02")
    assert ann["tiers"]["ortho"]["intervals"] == existing


def test_ortho_overwrite_true_replaces_tier(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    stub = _StubOrthoProvider()
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)

    existing = [{"start": 5.0, "end": 5.5, "text": "manual-edit"}]
    _seed_annotation(tmp_path, "Fail02", ortho=existing, source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho(
        "j1", {"speaker": "Fail02", "overwrite": True},
    )

    assert result["skipped"] is False
    assert result["replaced_existing"] is True
    assert result["filled"] == 2

    ann = _load_canonical(tmp_path, "Fail02")
    texts = [iv["text"] for iv in ann["tiers"]["ortho"]["intervals"]]
    assert "manual-edit" not in texts
    assert texts == ["بەش", "سەرە"]


def test_ortho_prefers_normalized_working_wav(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    stub = _StubOrthoProvider()
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)

    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    normalized = _write_fake_source_wav(tmp_path, "audio/working/Fail02/Fail02.wav")

    server._compute_speaker_ortho("j1", {"speaker": "Fail02"})

    assert len(stub.calls) == 1
    assert stub.calls[0]["audio_path"] == str(normalized)


def test_ortho_missing_annotation_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: _StubOrthoProvider())

    with pytest.raises(RuntimeError, match="No annotation"):
        server._compute_speaker_ortho("j1", {"speaker": "GhostSpeaker"})


def test_run_compute_job_dispatches_ortho(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: _StubOrthoProvider())
    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    captured = {}
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)
    monkeypatch.setattr(
        server, "_set_job_complete",
        lambda jid, result, **kw: captured.setdefault("result", result),
    )
    monkeypatch.setattr(
        server, "_set_job_error",
        lambda jid, err: captured.setdefault("error", err),
    )

    server._run_compute_job("j1", "ortho", {"speaker": "Fail02"})
    assert "error" not in captured
    assert captured["result"]["filled"] == 2


def test_ortho_backend_factory_selects_hf_by_default() -> None:
    from ai.providers.hf_whisper import HFWhisperProvider

    provider = get_ortho_provider(config={"ortho": {}})

    assert isinstance(provider, HFWhisperProvider)
    assert provider.model_path == "razhan/whisper-base-sdh"


def test_ortho_backend_factory_selects_legacy_faster_whisper() -> None:
    provider = get_ortho_provider(
        config={
            "ortho": {
                "backend": "faster-whisper",
                "model_path": "/tmp/razhan-sdh-ct2",
            }
        }
    )

    assert isinstance(provider, LocalWhisperProvider)


def test_ortho_backend_factory_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unknown ortho.backend"):
        get_ortho_provider(config={"ortho": {"backend": "mystery"}})


# --------------------------------------------------------------------------
# Pipeline state probe
# --------------------------------------------------------------------------


def test_ortho_writes_ortho_words_from_forced_alignment(tmp_path, monkeypatch):
    """When Whisper produces word-level timestamps, Tier-2 forced alignment
    flattens them into tiers.ortho_words — coarse ortho tier stays intact."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    segments_with_words = [
        {
            "start": 0.0,
            "end": 1.5,
            "text": "بەش سەرە",
            "words": [
                {"word": "بەش", "start": 0.05, "end": 0.55, "prob": 0.95},
                {"word": "سەرە", "start": 0.60, "end": 1.20, "prob": 0.90},
            ],
        },
    ]
    stub = _StubOrthoProvider(segments=segments_with_words)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)

    # Stub the wav2vec2 aligner so the test doesn't pull the 1.2 GB model.
    # Input shape matches align_segments: List[Segment] → List[List[AlignedWord]].
    fake_aligned = [[
        {"word": "بەش", "start": 0.08, "end": 0.52, "confidence": 0.97,
         "method": "wav2vec2"},
        {"word": "سەرە", "start": 0.62, "end": 1.18, "confidence": 0.93,
         "method": "wav2vec2"},
    ]]

    def _fake_align_segments(audio_path, segments, **kwargs):
        assert len(segments) == 1 and segments[0]["words"]
        return fake_aligned

    import ai.forced_align as fa
    monkeypatch.setattr(fa, "align_segments", _fake_align_segments)

    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho("j1", {"speaker": "Fail02"})

    assert result["filled"] == 1  # one coarse segment
    assert result["ortho_words"] == 2  # two word-level entries

    ann = _load_canonical(tmp_path, "Fail02")
    coarse = ann["tiers"]["ortho"]["intervals"]
    assert [iv["text"] for iv in coarse] == ["بەش سەرە"]

    words = ann["tiers"]["ortho_words"]["intervals"]
    assert [iv["text"] for iv in words] == ["بەش", "سەرە"]
    assert words[0]["start"] == pytest.approx(0.08)
    assert words[0]["end"] == pytest.approx(0.52)
    assert words[0]["source"] == "forced_align"
    assert words[0]["confidence"] == pytest.approx(0.97)


def test_ortho_words_empty_when_segments_have_no_word_level_data(tmp_path, monkeypatch):
    """Tier-2 is a no-op (empty ortho_words) when segments lack words[]."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    stub = _StubOrthoProvider()  # default: no words[]
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)

    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho("j1", {"speaker": "Fail02"})
    assert result["ortho_words"] == 0

    ann = _load_canonical(tmp_path, "Fail02")
    assert ann["tiers"]["ortho_words"]["intervals"] == []


def test_ortho_words_survives_alignment_exception(tmp_path, monkeypatch):
    """align_segments raising shouldn't fail the ortho job — fall through
    with an empty ortho_words tier so the coarse pass still lands."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    segments_with_words = [
        {
            "start": 0.0, "end": 1.0, "text": "hi",
            "words": [{"word": "hi", "start": 0.0, "end": 1.0, "prob": 0.9}],
        },
    ]
    stub = _StubOrthoProvider(segments=segments_with_words)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: stub)

    import ai.forced_align as fa
    def _boom(*a, **kw):
        raise RuntimeError("wav2vec2 unavailable")
    monkeypatch.setattr(fa, "align_segments", _boom)

    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    result = server._compute_speaker_ortho("j1", {"speaker": "Fail02"})
    assert result["filled"] == 1
    assert result["ortho_words"] == 0

    ann = _load_canonical(tmp_path, "Fail02")
    assert ann["tiers"]["ortho_words"]["intervals"] == []


def test_pipeline_state_reports_all_steps_empty_for_fresh_speaker(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    state = server._pipeline_state_for_speaker("Fail02")

    assert state["speaker"] == "Fail02"
    assert state["normalize"]["done"] is False
    assert state["stt"]["done"] is False
    assert state["ortho"]["done"] is False
    assert state["ipa"]["done"] is False


def test_pipeline_state_detects_existing_ortho_and_normalized(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    ortho = [{"start": 1.0, "end": 1.5, "text": "hair"}]
    _seed_annotation(tmp_path, "Fail02", ortho=ortho, source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "audio/working/Fail02/Fail02.wav")

    state = server._pipeline_state_for_speaker("Fail02")

    assert state["normalize"]["done"] is True
    assert state["normalize"]["path"].endswith("Fail02.wav")
    assert state["ortho"]["done"] is True
    assert state["ortho"]["intervals"] == 1
    assert state["ipa"]["done"] is False


# --------------------------------------------------------------------------
# full_pipeline sequencer
# --------------------------------------------------------------------------


def test_full_pipeline_runs_only_selected_steps(tmp_path, monkeypatch):
    """Unchecked steps must not invoke their compute functions."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    called: list[str] = []

    def fake_ortho(job_id, payload):
        called.append("ortho")
        return {"speaker": payload["speaker"], "filled": 3, "skipped": False}

    def fake_ipa(job_id, payload):
        called.append("ipa")
        return {"speaker": payload["speaker"], "filled": 2, "skipped": 0, "total": 2}

    def fake_normalize(*a, **kw):
        called.append("normalize")
        raise AssertionError("normalize should not run when unchecked")

    def fake_stt(*a, **kw):
        called.append("stt")
        raise AssertionError("stt should not run when unchecked")

    monkeypatch.setattr(server, "_compute_speaker_ortho", fake_ortho)
    monkeypatch.setattr(server, "_compute_speaker_ipa", fake_ipa)
    monkeypatch.setattr(server, "_run_normalize_job", fake_normalize)
    monkeypatch.setattr(server, "_run_stt_job", fake_stt)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    result = server._compute_full_pipeline(
        "j1",
        {
            "speaker": "Fail02",
            "steps": ["ortho", "ipa"],
            "overwrites": {"ortho": True},
        },
    )

    assert called == ["ortho", "ipa"]
    assert result["steps_run"] == ["ortho", "ipa"]
    assert result["results"]["ortho"]["filled"] == 3
    assert result["results"]["ipa"]["filled"] == 2


def test_full_pipeline_enforces_canonical_order(tmp_path, monkeypatch):
    """Even if steps are submitted in the wrong order, run normalize → stt → ortho → ipa."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    called: list[str] = []
    monkeypatch.setattr(server, "_compute_speaker_ortho", lambda *a, **kw: called.append("ortho") or {"filled": 0})
    monkeypatch.setattr(server, "_compute_speaker_ipa", lambda *a, **kw: called.append("ipa") or {"filled": 0})
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    server._compute_full_pipeline(
        "j1",
        {
            "speaker": "Fail02",
            "steps": ["ipa", "ortho"],   # deliberately reversed
        },
    )

    assert called == ["ortho", "ipa"]


def test_full_pipeline_stt_step_uses_normalized_working_wav(tmp_path, monkeypatch):
    """The STT branch must resolve audio via _pipeline_audio_path_for_speaker —
    i.e. prefer ``audio/working/<speaker>/<name>.wav`` over the bare source
    filename, which fails to resolve when the raw file has been cleaned up
    post-normalization. Regression guard for an error surfaced in prod where
    the pipeline looked for ``SK_Faili_F_1968.wav`` at the project root even
    though the normalized copy sat under ``audio/working/Fail02/``.
    """
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="SK_Faili_F_1968.wav")
    # Deliberately NOT writing the raw source at project root — only the
    # normalized working copy exists, mirroring the failure mode.
    normalized = _write_fake_source_wav(
        tmp_path, "audio/working/Fail02/SK_Faili_F_1968.wav",
    )

    observed: dict = {}

    def fake_stt(job_id, speaker, source_wav, language):
        observed["source_wav"] = source_wav
        observed["speaker"] = speaker

    monkeypatch.setattr(server, "_run_stt_job", fake_stt)
    monkeypatch.setattr(server, "_latest_stt_segments_for_speaker", lambda s: None)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)
    # After _run_stt_job returns (no-op in this stub), the sequencer checks
    # the job snapshot for errors and resets it to running. Return a running
    # snapshot so the sequencer doesn't treat the no-op as a failure.
    monkeypatch.setattr(server, "_get_job_snapshot", lambda jid: {"status": "running"})
    monkeypatch.setattr(server, "_reset_job_to_running", lambda jid: None)

    server._compute_full_pipeline(
        "j1",
        {"speaker": "Fail02", "steps": ["stt"], "overwrites": {"stt": True}},
    )

    # The audio path handed to _run_stt_job must resolve — it's the
    # normalized working copy, not the bare filename.
    assert observed["source_wav"] == str(normalized)


def test_full_pipeline_stt_captures_missing_audio_error(tmp_path, monkeypatch):
    """If neither normalized nor raw source exists, STT must record an
    error in results['stt'] (not raise) so the rest of the pipeline can
    still attempt to run for that speaker."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="SK_Faili_F_1968.wav")
    # No audio file written anywhere — simulate the prod-error condition.

    monkeypatch.setattr(server, "_run_stt_job", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_latest_stt_segments_for_speaker", lambda s: None)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    result = server._compute_full_pipeline(
        "j1",
        {"speaker": "Fail02", "steps": ["stt"], "overwrites": {"stt": True}},
    )
    assert result["results"]["stt"]["status"] == "error"
    assert "Cannot run STT" in result["results"]["stt"]["error"]
    assert result["results"]["stt"]["traceback"]


def test_full_pipeline_step_failure_is_captured_not_raised(tmp_path, monkeypatch):
    """A step raising must be captured in results[step]['error']/['traceback'],
    not propagated — and the next step must still run. This is the
    walk-away-friendly contract: a batch of 10 speakers shouldn't be
    aborted because one speaker's razhan load hit a stale cache.
    """
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    def broken_ortho(*a, **kw):
        raise RuntimeError("razhan exploded")

    ipa_called = {"count": 0}

    def fake_ipa(*a, **kw):
        ipa_called["count"] += 1
        return {"speaker": "Fail02", "filled": 0, "skipped": 0, "total": 0}

    monkeypatch.setattr(server, "_compute_speaker_ortho", broken_ortho)
    monkeypatch.setattr(server, "_compute_speaker_ipa", fake_ipa)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    result = server._compute_full_pipeline(
        "j1",
        {"speaker": "Fail02", "steps": ["ortho", "ipa"]},
    )

    # ORTH captured the error — no raise.
    assert result["results"]["ortho"]["status"] == "error"
    assert "razhan exploded" in result["results"]["ortho"]["error"]
    assert result["results"]["ortho"]["traceback"]  # non-empty
    # IPA STILL ran after ORTH failed — that's the whole point.
    assert ipa_called["count"] == 1
    assert result["results"]["ipa"]["status"] in {"ok", "skipped"}
    # Summary roll-up reflects the outcome.
    assert result["summary"]["error"] == 1
    assert result["summary"]["ok"] + result["summary"]["skipped"] == 1


# --------------------------------------------------------------------------
# Preflight (can_run / reason) — drives the pre-run speaker grid in the UI
# --------------------------------------------------------------------------


def test_preflight_all_steps_can_run_when_audio_and_annotation_present(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(
        tmp_path, "Fail02",
        ortho=[{"start": 0.0, "end": 1.0, "text": "x"}],  # ortho present → IPA unlocked
        source_audio="raw/Fail02.wav",
    )
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "audio/working/Fail02/Fail02.wav")

    state = server._pipeline_state_for_speaker("Fail02")
    for step in ("normalize", "stt", "ortho", "ipa"):
        assert state[step]["can_run"] is True, f"{step} should be runnable: {state[step]}"
        assert state[step]["reason"] is None


def test_preflight_blocks_when_audio_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    # Deliberately write NO audio file anywhere.

    state = server._pipeline_state_for_speaker("Fail02")
    assert state["normalize"]["can_run"] is False
    assert "Source audio not found" in state["normalize"]["reason"]
    assert state["stt"]["can_run"] is False
    assert "No audio file" in state["stt"]["reason"]
    assert state["ortho"]["can_run"] is False
    assert "No audio file" in state["ortho"]["reason"]


def test_preflight_ipa_blocked_when_no_ortho(tmp_path, monkeypatch):
    """IPA cannot run if ortho tier is empty (nothing to phonemize from).
    The reason text should hint that running ORTH first unblocks it."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    state = server._pipeline_state_for_speaker("Fail02")
    assert state["ipa"]["can_run"] is False
    assert "ORTH" in state["ipa"]["reason"]
    # ORTH itself can still run (audio exists) — it's the unblocker.
    assert state["ortho"]["can_run"] is True


def test_preflight_handles_missing_annotation(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    # No _seed_annotation call — speaker has no annotation file.

    state = server._pipeline_state_for_speaker("GhostSpeaker")
    for step in ("normalize", "stt", "ortho", "ipa"):
        assert state[step]["can_run"] is False
        assert "No annotation" in state[step]["reason"]


# --------------------------------------------------------------------------
# Full-file coverage — the signal that distinguishes "tier has intervals"
# from "the entire WAV was actually processed". A tier can have 128
# intervals that only cover the first 30 seconds of a 6-minute recording;
# the user needs to know this so they can decide whether to re-run.
# --------------------------------------------------------------------------


def _write_fake_wav(tmp_path, rel_path, duration_sec):
    """Create a tiny but valid PCM WAV with the given duration so the
    ``wave.open`` path in _audio_duration_sec picks it up."""
    import wave
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 1000
    frames = int(rate * duration_sec)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)
    return path


def test_tier_coverage_full_file_when_intervals_span_duration(tmp_path, monkeypatch):
    """ORTH ran full-file → last interval end is close to audio duration
    → full_coverage is true and coverage_fraction is ~1.0."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    ortho = [
        {"start": 0.2, "end": 2.5, "text": "a"},
        {"start": 3.0, "end": 5.8, "text": "b"},
        {"start": 6.0, "end": 9.9, "text": "c"},  # last end ~ duration
    ]
    _seed_annotation(tmp_path, "Fail02", ortho=ortho, source_audio="raw/Fail02.wav")
    _write_fake_wav(tmp_path, "raw/Fail02.wav", duration_sec=10.0)

    state = server._pipeline_state_for_speaker("Fail02")
    assert state["duration_sec"] == pytest.approx(10.0, abs=0.05)
    assert state["ortho"]["full_coverage"] is True
    assert state["ortho"]["coverage_end_sec"] == pytest.approx(9.9, abs=0.01)
    assert state["ortho"]["coverage_fraction"] > 0.95


def test_tier_coverage_partial_file_when_intervals_cluster_early(tmp_path, monkeypatch):
    """ORTH was only run on the first slice (e.g. stale concept
    timestamps) → last interval end is far short of audio duration →
    full_coverage is false even though done is true."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    # 60-second file, but ortho only covers the first 10 seconds.
    ortho = [
        {"start": 1.0, "end": 3.0, "text": "a"},
        {"start": 4.0, "end": 6.0, "text": "b"},
        {"start": 7.0, "end": 10.0, "text": "c"},
    ]
    _seed_annotation(tmp_path, "Fail02", ortho=ortho, source_audio="raw/Fail02.wav")
    _write_fake_wav(tmp_path, "raw/Fail02.wav", duration_sec=60.0)

    state = server._pipeline_state_for_speaker("Fail02")
    assert state["ortho"]["done"] is True
    assert state["ortho"]["full_coverage"] is False
    assert state["ortho"]["coverage_fraction"] == pytest.approx(10.0 / 60.0, abs=0.01)
    assert state["ortho"]["coverage_end_sec"] == pytest.approx(10.0, abs=0.01)


def test_tier_coverage_empty_tier_is_not_full_coverage(tmp_path, monkeypatch):
    """Empty tier with known duration → full_coverage explicitly false
    (not null) so agents can distinguish from 'duration unknown'."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", ortho=[], source_audio="raw/Fail02.wav")
    _write_fake_wav(tmp_path, "raw/Fail02.wav", duration_sec=60.0)

    state = server._pipeline_state_for_speaker("Fail02")
    assert state["ortho"]["done"] is False
    assert state["ortho"]["full_coverage"] is False
    assert state["ortho"]["coverage_fraction"] == 0.0


def test_tier_coverage_null_when_duration_unknown(tmp_path, monkeypatch):
    """No audio file, no duration metadata → coverage_fraction and
    full_coverage are null (not guessed)."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    # Seed with source that doesn't exist + no duration metadata.
    ann_dir = tmp_path / "annotations"
    ann_dir.mkdir(exist_ok=True)
    (ann_dir / "Fail02.parse.json").write_text(json.dumps({
        "version": 1,
        "speaker": "Fail02",
        "source_audio": "missing.wav",
        # No source_audio_duration_sec key at all.
        "tiers": {
            "ortho": {"type": "interval", "display_order": 2,
                      "intervals": [{"start": 1.0, "end": 5.0, "text": "x"}]},
        },
    }), encoding="utf-8")

    state = server._pipeline_state_for_speaker("Fail02")
    assert state["duration_sec"] is None
    assert state["ortho"]["full_coverage"] is None
    assert state["ortho"]["coverage_fraction"] is None
    assert state["ortho"]["coverage_end_sec"] == pytest.approx(5.0)


def test_tier_coverage_absolute_tolerance_for_short_clips(tmp_path, monkeypatch):
    """A 30-second clip with ortho ending at 28.5s is effectively full-
    coverage (within 3-second absolute tolerance), even though the
    fraction is only 0.95. Regression guard for the short-clip edge
    of the threshold heuristic."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    ortho = [{"start": 0.5, "end": 28.5, "text": "x"}]
    _seed_annotation(tmp_path, "Fail02", ortho=ortho, source_audio="raw/Fail02.wav")
    _write_fake_wav(tmp_path, "raw/Fail02.wav", duration_sec=30.0)

    state = server._pipeline_state_for_speaker("Fail02")
    assert state["ortho"]["full_coverage"] is True


def test_tier_coverage_falls_back_to_annotation_duration_when_audio_missing(tmp_path, monkeypatch):
    """If the WAV isn't on disk but the annotation records
    ``source_audio_duration_sec``, the preflight still reports
    coverage_fraction + full_coverage using the hint."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    ann_dir = tmp_path / "annotations"
    ann_dir.mkdir(exist_ok=True)
    (ann_dir / "Fail02.parse.json").write_text(json.dumps({
        "version": 1,
        "speaker": "Fail02",
        "source_audio": "missing.wav",
        "source_audio_duration_sec": 100.0,
        "tiers": {
            "ortho": {"type": "interval", "display_order": 2,
                      "intervals": [{"start": 0.0, "end": 50.0, "text": "x"}]},
        },
    }), encoding="utf-8")

    state = server._pipeline_state_for_speaker("Fail02")
    assert state["duration_sec"] == pytest.approx(100.0)
    assert state["ortho"]["coverage_fraction"] == pytest.approx(0.5, abs=0.01)
    assert state["ortho"]["full_coverage"] is False
