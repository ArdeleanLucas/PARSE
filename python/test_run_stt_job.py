"""Tests for _run_stt_job progress reporting and error wrapping."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _StubProvider:
    """Controllable STT provider stub."""

    def __init__(self, emit_progresses=None, emit_segments=None, raise_on_transcribe=None):
        self.emit_progresses = emit_progresses or []
        self.emit_segments = emit_segments or []
        self.raise_on_transcribe = raise_on_transcribe

    def transcribe(self, audio_path, language=None, progress_callback=None):
        if self.raise_on_transcribe:
            raise self.raise_on_transcribe
        if progress_callback is not None:
            for p, n in self.emit_progresses:
                progress_callback(p, n)
        return self.emit_segments


def _prepare_job(tmp_path, monkeypatch, *, provider=None, provider_factory=None, wav_name="t.wav"):
    # Reset job store
    server._jobs.clear()
    # Create a dummy audio file under the project root
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    audio_path = tmp_path / wav_name
    audio_path.write_bytes(b"\0")
    if provider is not None:
        monkeypatch.setattr(server, "get_stt_provider", lambda: provider)
    if provider_factory is not None:
        monkeypatch.setattr(server, "get_stt_provider", provider_factory)
    job_id = server._create_job("stt", {"speaker": "s", "sourceWav": wav_name})
    return job_id, audio_path


def test_initial_progress_is_well_below_one_percent(tmp_path, monkeypatch):
    """Regression for the 100%-on-start bug: initial progress must be <1.0 so
    the frontend's normalizeProgress (which treats exactly 1.0 as 100%)
    never flashes a full bar before decoding starts."""
    captured_progress = []

    orig = server._set_job_progress

    def spy(job_id, progress, **kwargs):
        captured_progress.append(float(progress))
        return orig(job_id, progress, **kwargs)

    monkeypatch.setattr(server, "_set_job_progress", spy)

    # Provider that never calls the callback — so only the init splash shows.
    stub = _StubProvider(emit_progresses=[], emit_segments=[])
    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider=stub)

    server._run_stt_job(job_id, "s", "t.wav", "ckb")
    assert captured_progress, "no progress updates emitted"
    assert captured_progress[0] < 1.0, captured_progress
    assert server._jobs[job_id]["status"] == "complete"


def test_mid_job_progress_is_capped_at_98(tmp_path, monkeypatch):
    """faster-whisper can emit 100% mid-decode when VAD fuses a clip; the
    worker must clamp so the bar only fills on completion."""
    captured = []
    orig = server._set_job_progress

    def spy(job_id, progress, **kwargs):
        captured.append(float(progress))
        return orig(job_id, progress, **kwargs)

    monkeypatch.setattr(server, "_set_job_progress", spy)

    # Provider emits progress=100 mid-job (pre-fix this leaked to the UI).
    stub = _StubProvider(emit_progresses=[(100.0, 1), (100.0, 2)], emit_segments=[])
    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider=stub)

    server._run_stt_job(job_id, "s", "t.wav", "ckb")
    # Find the mid-job values (not the final 100 from _set_job_complete)
    job = server._jobs[job_id]
    assert job["status"] == "complete"
    # No mid-job progress should exceed 98
    mid = [p for p in captured]
    assert all(p <= 98.0 for p in mid), mid
    # And the final stored progress is 100 from _set_job_complete
    assert job["progress"] == 100.0


def test_provider_init_failure_is_wrapped_with_context(tmp_path, monkeypatch):
    """get_stt_provider exceptions must surface as 'STT provider init failed:
    …' so the UI banner isn't stuck on the stale 'Initializing STT provider'
    message."""
    def factory():
        raise RuntimeError("no CUDA")

    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider_factory=factory)
    server._run_stt_job(job_id, "s", "t.wav", "ckb")
    job = server._jobs[job_id]
    assert job["status"] == "error"
    assert "STT provider init failed" in job["error"]
    assert "no CUDA" in job["error"]


def test_transcribe_failure_is_wrapped_with_context(tmp_path, monkeypatch):
    """Transcribe exceptions likewise must be labeled."""
    stub = _StubProvider(raise_on_transcribe=RuntimeError("out of memory"))
    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider=stub)
    server._run_stt_job(job_id, "s", "t.wav", "ckb")
    job = server._jobs[job_id]
    assert job["status"] == "error"
    assert "STT transcription failed" in job["error"]
    assert "out of memory" in job["error"]
