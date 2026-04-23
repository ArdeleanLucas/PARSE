"""Unit tests for _compute_speaker_ortho and the full-pipeline sequencer."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402


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


# --------------------------------------------------------------------------
# Pipeline state probe
# --------------------------------------------------------------------------


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


def test_full_pipeline_stt_raises_when_no_audio_reachable(tmp_path, monkeypatch):
    """If neither normalized nor raw source exists, STT must abort cleanly."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="SK_Faili_F_1968.wav")
    # No audio file written anywhere — simulate the prod-error condition.

    monkeypatch.setattr(server, "_run_stt_job", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_latest_stt_segments_for_speaker", lambda s: None)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    with pytest.raises(RuntimeError, match="Cannot run STT"):
        server._compute_full_pipeline(
            "j1",
            {"speaker": "Fail02", "steps": ["stt"], "overwrites": {"stt": True}},
        )


def test_full_pipeline_propagates_step_failure(tmp_path, monkeypatch):
    """A step raising should abort the pipeline and propagate the error."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_annotation(tmp_path, "Fail02", source_audio="raw/Fail02.wav")
    _write_fake_source_wav(tmp_path, "raw/Fail02.wav")

    def broken_ortho(*a, **kw):
        raise RuntimeError("razhan exploded")

    ipa_called = {"count": 0}

    def fake_ipa(*a, **kw):
        ipa_called["count"] += 1
        return {"filled": 0}

    monkeypatch.setattr(server, "_compute_speaker_ortho", broken_ortho)
    monkeypatch.setattr(server, "_compute_speaker_ipa", fake_ipa)
    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)

    with pytest.raises(RuntimeError, match="razhan exploded"):
        server._compute_full_pipeline(
            "j1",
            {"speaker": "Fail02", "steps": ["ortho", "ipa"]},
        )
    # IPA must not run after ORTHO fails.
    assert ipa_called["count"] == 0
