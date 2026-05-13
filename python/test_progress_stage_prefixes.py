"""Regression coverage for stage context in pipeline progress messages."""
from __future__ import annotations

import inspect
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402
from server_routes import annotate, media  # noqa: E402

_TRIPWIRE_JOB_ID = "__progress_stage_prefix_tripwire__"
_TRIPWIRE_JOB = {"type": "test:tripwire", "status": "sentinel"}


@pytest.fixture(scope="module", autouse=True)
def _preserve_jobs_for_progress_stage_prefix_module():
    """Restore the process-global job registry after this module finishes."""
    snapshot = dict(server._jobs)
    server._jobs[_TRIPWIRE_JOB_ID] = dict(_TRIPWIRE_JOB)
    try:
        yield
    finally:
        server._jobs.clear()
        server._jobs.update(snapshot)


@pytest.fixture(autouse=True)
def _ensure_route_bindings_installed():
    """Install server route bindings during test execution, not collection."""
    if not getattr(server, "_ROUTE_BINDINGS_INSTALLED", False):
        server._install_route_bindings()
    yield


@pytest.fixture
def isolated_jobs():
    """Snapshot server._jobs around a test that needs an empty registry."""
    snapshot = dict(server._jobs)
    server._jobs.clear()
    try:
        yield
    finally:
        server._jobs.clear()
        server._jobs.update(snapshot)


class _ProgressingSttProvider:
    def transcribe(self, **kwargs):
        progress_callback = kwargs.get("progress_callback")
        if callable(progress_callback):
            progress_callback(16.0, 2)
        return [{"start": 0.0, "end": 1.0, "text": "baş"}]


def test_stt_progress_callback_emits_stt_prefix(tmp_path, monkeypatch):
    messages: list[str] = []
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "get_stt_provider", lambda: _ProgressingSttProvider())
    monkeypatch.setattr(media, "_stt_audio_duration_seconds", lambda _path: 1.0, raising=False)
    monkeypatch.setattr(server, "_write_stt_cache", lambda *args, **kwargs: None)

    audio_path = tmp_path / "short.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    job_id = server._create_job("compute:stt", {"speaker": "s", "sourceWav": "short.wav"})

    original = server._set_job_progress

    def spy(job_id, progress, *, message=None, **kwargs):
        if message:
            messages.append(str(message))
        return original(job_id, progress, message=message, **kwargs)

    monkeypatch.setattr(server, "_set_job_progress", spy)

    result = server._run_stt_job(job_id, "s", "short.wav", "ckb")

    assert result["segments"]
    assert messages
    assert all(message.startswith("STT") for message in messages), messages


def _literal_progress_messages(function) -> list[str]:
    source = inspect.getsource(function)
    return [line.strip() for line in source.splitlines() if "message='" in line or 'message="' in line]


def test_ortho_chunked_progress_emits_ortho_prefix():
    lines = _literal_progress_messages(annotate._compute_speaker_ortho)
    lines += _literal_progress_messages(annotate._compute_speaker_ortho_concept_windows)
    relevant = [line for line in lines if "message='Step " not in line]

    assert relevant
    assert all("message='ORTH " in line or 'message="ORTH ' in line for line in relevant), relevant


def test_ipa_subprocess_progress_emits_ipa_prefix():
    lines = _literal_progress_messages(annotate._compute_speaker_ipa)
    lines += _literal_progress_messages(annotate._compute_speaker_ipa_concept_windows)
    relevant = [line for line in lines if "message='Step " not in line]

    assert relevant
    assert all("message='IPA " in line or 'message="IPA ' in line for line in relevant), relevant


def test_orchestrator_step_header_unchanged(monkeypatch, isolated_jobs):
    messages: list[str] = []
    monkeypatch.setattr(server, "_ensure_host_memory_for_step", lambda _step: None)
    monkeypatch.setattr(server, "_latest_stt_segments_for_speaker", lambda _speaker: [{"text": "cached"}])
    monkeypatch.setattr(server, "_compute_speaker_ortho_in_subprocess", lambda _job_id, _payload: {"status": "ok"})
    monkeypatch.setattr(server, "_compute_full_pipeline_ipa_in_subprocess", lambda _job_id, _payload: {"status": "ok"})
    monkeypatch.setattr(server, "_collect_after_unload", lambda: None)
    monkeypatch.setattr(server, "_release_ipa_aligner", lambda: None, raising=False)

    original = server._set_job_progress

    def spy(job_id, progress, *, message=None, **kwargs):
        if message:
            messages.append(str(message))
        return original(job_id, progress, message=message, **kwargs)

    monkeypatch.setattr(server, "_set_job_progress", spy)
    job_id = server._create_job("compute:full_pipeline", {"speaker": "s"})

    result = server._compute_full_pipeline(
        job_id,
        {"speaker": "s", "steps": ["stt", "ortho", "ipa"], "overwrites": {"stt": False}},
    )

    assert result["steps_run"] == ["stt", "ortho", "ipa"]
    assert "Step 1/3: stt" in messages
    assert not any(message.startswith("STT Step") or message.startswith("ORTH Step") or message.startswith("IPA Step") for message in messages)


def test_zz_progress_stage_prefix_tests_do_not_leak_global_state():
    """Runs last as a trip-wire for job-registry clears in earlier tests."""
    assert server._jobs.get(_TRIPWIRE_JOB_ID) == _TRIPWIRE_JOB
