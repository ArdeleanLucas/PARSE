"""Tests for _run_stt_job progress reporting and error wrapping.

_run_stt_job returns the result dict on success and raises on failure;
terminal job state (_set_job_complete / _set_job_error) is now the
dispatcher's responsibility. These tests verify that contract + the
in-progress behaviour (<1% initial splash, 98% mid-job cap, wrapped
error messages).
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
from ai import job_cancel
from server_routes import media

server._install_route_bindings()


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

    stub = _StubProvider(emit_progresses=[], emit_segments=[])
    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider=stub)

    result = server._run_stt_job(job_id, "s", "t.wav", "ckb")
    assert captured_progress, "no progress updates emitted"
    assert captured_progress[0] < 1.0, captured_progress
    # New contract: _run_stt_job returns the result dict; terminal state
    # (status=complete, progress=100) is the dispatcher's responsibility.
    assert result["speaker"] == "s"
    assert result["segments"] == []


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

    result = server._run_stt_job(job_id, "s", "t.wav", "ckb")
    # No mid-job progress reported by _run_stt_job should exceed 98.
    assert all(p <= 98.0 for p in captured), captured
    # Result dict is returned (dispatcher fills progress to 100 on complete).
    assert result["segments"] == []


def test_provider_init_failure_is_wrapped_with_context(tmp_path, monkeypatch):
    """get_stt_provider exceptions must surface as 'STT provider init failed:
    …' so the UI banner isn't stuck on the stale 'Initializing STT provider'
    message. _run_stt_job now raises instead of calling _set_job_error."""
    def factory():
        raise RuntimeError("no CUDA")

    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider_factory=factory)
    with pytest.raises(RuntimeError) as exc_info:
        server._run_stt_job(job_id, "s", "t.wav", "ckb")
    assert "STT provider init failed" in str(exc_info.value)
    assert "no CUDA" in str(exc_info.value)


def test_transcribe_failure_is_wrapped_with_context(tmp_path, monkeypatch):
    """Transcribe exceptions likewise must be labeled."""
    stub = _StubProvider(raise_on_transcribe=RuntimeError("out of memory"))
    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider=stub)
    with pytest.raises(RuntimeError) as exc_info:
        server._run_stt_job(job_id, "s", "t.wav", "ckb")
    assert "STT transcription failed" in str(exc_info.value)
    assert "out of memory" in str(exc_info.value)


def test_compute_stt_wrapper_unpacks_payload(tmp_path, monkeypatch):
    """_compute_stt adapts the HTTP payload shape to _run_stt_job args."""
    stub = _StubProvider(emit_progresses=[], emit_segments=[{"text": "hi"}])
    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider=stub)
    result = server._compute_stt(
        job_id,
        {"speaker": "s", "sourceWav": "t.wav", "language": "ckb"},
    )
    assert result["speaker"] == "s"
    assert result["language"] == "ckb"
    assert result["segments"] == [{"text": "hi"}]


def test_compute_stt_rejects_missing_speaker(tmp_path, monkeypatch):
    stub = _StubProvider(emit_progresses=[], emit_segments=[])
    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider=stub)
    with pytest.raises(ValueError, match="speaker"):
        server._compute_stt(job_id, {"sourceWav": "t.wav"})


def test_compute_stt_rejects_missing_source_wav(tmp_path, monkeypatch):
    stub = _StubProvider(emit_progresses=[], emit_segments=[])
    job_id, _ = _prepare_job(tmp_path, monkeypatch, provider=stub)
    with pytest.raises(ValueError, match="sourceWav"):
        server._compute_stt(job_id, {"speaker": "s"})


class _ChunkedProvider:
    def __init__(self, *, failures=None, after_call=None):
        self.calls = []
        self.failures = failures or {}
        self.after_call = after_call

    def transcribe(self, **kwargs):
        idx = len(self.calls)
        self.calls.append(dict(kwargs))
        if self.after_call is not None:
            self.after_call(idx)
        failure = self.failures.get(idx)
        if failure is not None:
            raise failure
        segment = {"start": 10.0, "end": 20.0, "text": f"chunk-{idx}", "words": [{"start": 10.5, "end": 11.0, "text": "w"}]}
        segment_callback = kwargs.get("segment_callback")
        if callable(segment_callback):
            segment_callback(dict(segment))
        return [segment]


def _prepare_chunked_job(tmp_path, monkeypatch, *, duration, provider, temp_paths=None, cached=None, progress_events=None):
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    audio_path = tmp_path / "long.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    monkeypatch.setattr(server, "get_stt_provider", lambda: provider)
    monkeypatch.setattr(media, "_stt_audio_duration_seconds", lambda _path: duration, raising=False)
    if temp_paths is not None:
        def fake_slice(_audio_path, start_sec, end_sec):
            path = tmp_path / f"stt-chunk-{len(temp_paths)}-{int(start_sec)}-{int(end_sec)}.wav"
            path.write_bytes(b"chunk")
            temp_paths.append(path)
            return str(path)
        monkeypatch.setattr(media, "_write_audio_slice_to_temp_wav", fake_slice, raising=False)
    else:
        monkeypatch.setattr(media, "_write_audio_slice_to_temp_wav", lambda _audio_path, _start, _end: str(audio_path), raising=False)
    if cached is not None:
        monkeypatch.setattr(server, "_write_stt_cache", lambda speaker, source, language, segments, **_kw: cached.append({"speaker": speaker, "source": source, "language": language, "segments": [dict(segment) for segment in segments]}))
    if progress_events is not None:
        original_progress = server._set_job_progress
        def spy(job_id, progress, **kwargs):
            progress_events.append({"job_id": job_id, "progress": float(progress), **kwargs})
            return original_progress(job_id, progress, **kwargs)
        monkeypatch.setattr(server, "_set_job_progress", spy)
    return server._create_job("stt", {"speaker": "s", "sourceWav": "long.wav"}), audio_path


def test_stt_long_audio_splits_into_adjacent_chunks_and_offsets_segments(tmp_path, monkeypatch):
    monkeypatch.delenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", raising=False)
    cached = []
    progress_events = []
    provider = _ChunkedProvider()
    job_id, _ = _prepare_chunked_job(tmp_path, monkeypatch, duration=1850.0, provider=provider, cached=cached, progress_events=progress_events)

    result = server._run_stt_job(job_id, "s", "long.wav", "ckb")

    assert len(provider.calls) == 4
    assert [chunk["span"] for chunk in result["chunks"]] == [
        {"idx": 0, "start": 0.0, "end": 600.0},
        {"idx": 1, "start": 600.0, "end": 1200.0},
        {"idx": 2, "start": 1200.0, "end": 1800.0},
        {"idx": 3, "start": 1800.0, "end": 1850.0},
    ]
    assert [chunk["status"] for chunk in result["chunks"]] == ["ok", "ok", "ok", "ok"]
    assert [segment["start"] for segment in result["segments"]] == [10.0, 610.0, 1210.0, 1810.0]
    assert result["segments"][1]["words"][0]["start"] == 610.5
    assert cached[0]["segments"] == result["segments"]
    assert "chunks" not in cached[0]
    chunk_messages = [event["message"] for event in progress_events if str(event.get("message", "")).startswith("STT chunk")]
    assert chunk_messages[0] == "STT chunk 1/4 (0s–600s)"


def test_stt_short_audio_uses_single_shot_and_empty_chunks(tmp_path, monkeypatch):
    provider = _ChunkedProvider()
    job_id, audio_path = _prepare_chunked_job(tmp_path, monkeypatch, duration=300.0, provider=provider)

    result = server._run_stt_job(job_id, "s", "long.wav", "ckb")

    assert len(provider.calls) == 1
    assert provider.calls[0]["audio_path"] == audio_path
    assert result["chunks"] == []


def test_stt_chunk_size_zero_disables_chunking(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", "0")
    provider = _ChunkedProvider()
    job_id, audio_path = _prepare_chunked_job(tmp_path, monkeypatch, duration=1850.0, provider=provider)

    result = server._run_stt_job(job_id, "s", "long.wav", "ckb")

    assert len(provider.calls) == 1
    assert provider.calls[0]["audio_path"] == audio_path
    assert result["chunks"] == []


def test_stt_invalid_chunk_size_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", "garbage")
    provider = _ChunkedProvider()
    job_id, _ = _prepare_chunked_job(tmp_path, monkeypatch, duration=1850.0, provider=provider)

    result = server._run_stt_job(job_id, "s", "long.wav", "ckb")

    assert len(provider.calls) == 4
    assert result["chunks"][-1]["span"] == {"idx": 3, "start": 1800.0, "end": 1850.0}


def test_stt_chunk_oom_error_code_and_continues_to_later_chunks(tmp_path, monkeypatch):
    provider = _ChunkedProvider(failures={2: MemoryError("CUDA out of memory")})
    job_id, _ = _prepare_chunked_job(tmp_path, monkeypatch, duration=2500.0, provider=provider)

    result = server._run_stt_job(job_id, "s", "long.wav", "ckb")

    assert len(provider.calls) == 5
    assert [chunk["status"] for chunk in result["chunks"]] == ["ok", "ok", "error", "ok", "ok"]
    assert result["chunks"][2]["error_code"] == "oom_suspect"
    assert [segment["text"] for segment in result["segments"]] == ["chunk-0", "chunk-1", "chunk-3", "chunk-4"]


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RuntimeError("CUDA out of memory"), "oom_suspect"),
        (RuntimeError("killed with code 137"), "oom_suspect"),
        (RuntimeError("provider timed out"), "timeout"),
        (RuntimeError("weird"), "provider_error"),
    ],
)
def test_stt_chunk_provider_error_classified(exc, expected):
    assert media._classify_stt_chunk_error(exc) == expected


def test_stt_cancel_between_chunks_returns_partial_with_cancelled_entries(tmp_path, monkeypatch):
    provider = _ChunkedProvider()
    job_id, _ = _prepare_chunked_job(tmp_path, monkeypatch, duration=2500.0, provider=provider)
    job_cancel.clear_cancel(job_id)

    def cancel_matching_after_second(idx):
        if idx == 1:
            job_cancel.request_cancel(job_id)
    provider.after_call = cancel_matching_after_second

    result = server._run_stt_job(job_id, "s", "long.wav", "ckb")

    assert len(provider.calls) == 2
    assert [chunk["status"] for chunk in result["chunks"]] == ["ok", "ok", "cancelled", "cancelled", "cancelled"]
    assert result["status"] == "cancelled"
    job_cancel.clear_cancel(job_id)


def test_stt_temp_wav_files_cleaned_up_on_success_and_chunk_errors(tmp_path, monkeypatch):
    for failures in ({}, {1: RuntimeError("weird")}):
        temp_paths = []
        provider = _ChunkedProvider(failures=failures)
        job_id, _ = _prepare_chunked_job(tmp_path, monkeypatch, duration=1250.0, provider=provider, temp_paths=temp_paths)

        server._run_stt_job(job_id, "s", "long.wav", "ckb")

        assert temp_paths
        assert all(not path.exists() for path in temp_paths)
        server._jobs.clear()
