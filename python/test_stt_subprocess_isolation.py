from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402
from server_routes import media  # noqa: E402


server._install_route_bindings()


class _FakeProcess:
    def __init__(self, *, exitcode: int = 0, result_payload: dict[str, object] | None = None, alive: bool = False) -> None:
        self.exitcode = exitcode
        self.result_payload = result_payload
        self.alive = alive
        self.pid = os.getpid() + 17
        self.started = False
        self.terminated = False
        self.args: tuple[object, ...] = ()
        self.target = None
        self.name = ""

    def start(self) -> None:
        self.started = True
        if self.result_payload is not None:
            result_path = pathlib.Path(str(self.args[2]))
            result_path.write_text(json.dumps(self.result_payload), encoding="utf-8")

    def join(self, timeout: float | None = None) -> None:
        return None

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False
        self.exitcode = -15


class _FakeContext:
    def __init__(self, process: _FakeProcess) -> None:
        self.process = process

    def Process(self, *, target, name, args, daemon):  # noqa: N802 - mirrors multiprocessing API
        assert daemon is True
        self.process.target = target
        self.process.name = name
        self.process.args = args
        return self.process


def _patch_spawn(monkeypatch: pytest.MonkeyPatch, process: _FakeProcess) -> None:
    import multiprocessing

    monkeypatch.setattr(multiprocessing, "get_context", lambda method: _FakeContext(process))


class _Provider:
    def __init__(self, segments: list[dict[str, object]] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.segments = segments if segments is not None else [{"start": 1.0, "end": 2.5, "text": "hello"}]

    def transcribe(self, **kwargs):
        self.calls.append(dict(kwargs))
        segment_callback = kwargs.get("segment_callback")
        if callable(segment_callback):
            for segment in self.segments:
                segment_callback(dict(segment))
        return [dict(segment) for segment in self.segments]


def _prepare_job(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, *, provider: _Provider, duration: float = 60.0) -> str:
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "get_stt_provider", lambda: provider)
    monkeypatch.setattr(media, "_stt_audio_duration_seconds", lambda _path: duration, raising=False)
    audio_path = tmp_path / "speaker.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    return server._create_job("stt", {"speaker": "Khan01", "sourceWav": "speaker.wav"})


def test_stt_coverage_end_sec_ignores_empty_text_and_bad_ends() -> None:
    assert media._stt_coverage_end_sec(
        [
            {"start": 0, "end": 7, "text": ""},
            {"start": 0, "end": "bad", "text": "kept"},
            {"start": 0, "end": 3.5, "text": "first"},
            {"start": 0, "end": 9.25, "text": " last "},
        ]
    ) == pytest.approx(9.25)


def test_summary_log_fires_on_completion(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", "10")
    provider = _Provider()
    job_id = _prepare_job(tmp_path, monkeypatch, provider=provider, duration=1250.0)
    monkeypatch.setattr(media, "_write_audio_slice_to_temp_wav", lambda _audio_path, _start, _end: str(tmp_path / "speaker.wav"), raising=False)

    with caplog.at_level("INFO", logger="server_routes.media"):
        result = server._run_stt_job(job_id, "Khan01", "speaker.wav", "ckb")

    stt_records = [record for record in caplog.records if record.getMessage().startswith("[STT] job=")]
    assert len(stt_records) == 1
    message = stt_records[0].getMessage()
    assert "job=" + job_id in message
    assert "speaker=Khan01" in message
    assert "chunked=true" in message
    assert "chunk_count=3" in message
    assert "total_duration_sec=1250.00" in message
    assert "coverage_end_sec=1202.50" in message
    assert "segments=3" in message
    assert len(result["chunks"]) == 3


def test_summary_log_fires_on_single_shot_path(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    provider = _Provider()
    job_id = _prepare_job(tmp_path, monkeypatch, provider=provider, duration=60.0)

    with caplog.at_level("INFO", logger="server_routes.media"):
        server._run_stt_job(job_id, "Khan01", "speaker.wav", "ckb")

    messages = [record.getMessage() for record in caplog.records if record.getMessage().startswith("[STT] job=")]
    assert len(messages) == 1
    assert "chunked=false" in messages[0]
    assert "chunk_count=0" in messages[0]
    assert "total_duration_sec=60.00" in messages[0]
    assert "coverage_end_sec=2.50" in messages[0]


def test_subprocess_wrap_short_audio_passes_through(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    expected = {
        "speaker": "Khan01",
        "sourceWav": str(tmp_path / "speaker.wav"),
        "language": "ckb",
        "segments": [{"start": 1.0, "end": 2.0, "text": "short"}],
        "chunks": [],
        "duration_sec": 60.0,
    }
    process = _FakeProcess(result_payload={"ok": True, "result": expected})
    _patch_spawn(monkeypatch, process)
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))

    result = server._run_stt_job_in_subprocess("job-short", "Khan01", str(tmp_path / "speaker.wav"), "ckb")

    assert process.started is True
    assert process.pid != os.getpid()
    assert process.target.__module__ == "server_routes.media"
    assert process.target.__name__ == "_run_stt_job_subprocess_entry"
    assert process.name == "parse-stt"
    assert result == expected


def test_subprocess_wrap_long_audio_chunks(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    expected = {
        "speaker": "Khan01",
        "sourceWav": str(tmp_path / "speaker.wav"),
        "language": "ckb",
        "segments": [{"start": 601.0, "end": 602.0, "text": "long"}],
        "chunks": [
            {"idx": 0, "span": {"idx": 0, "start": 0.0, "end": 600.0}, "status": "ok"},
            {"idx": 1, "span": {"idx": 1, "start": 600.0, "end": 1200.0}, "status": "ok"},
        ],
        "duration_sec": 4200.0,
    }
    process = _FakeProcess(result_payload={"ok": True, "result": expected})
    _patch_spawn(monkeypatch, process)
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))

    result = server._run_stt_job_in_subprocess("job-long", "Khan01", str(tmp_path / "speaker.wav"), "ckb")

    assert process.started is True
    assert process.pid != os.getpid()
    assert result["chunks"] == expected["chunks"]
    assert result["segments"] == expected["segments"]


def test_subprocess_crash_caught_and_classified(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    process = _FakeProcess(
        result_payload={
            "ok": False,
            "error": "simulated STT crash",
            "traceback": "Traceback (most recent call last):\nMemoryError: CUDA out of memory\n",
        }
    )
    _patch_spawn(monkeypatch, process)
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))
    parent_pid = os.getpid()

    result = server._run_stt_job_in_subprocess("job-oom", "Khan01", str(tmp_path / "speaker.wav"), "ckb")

    assert os.getpid() == parent_pid
    assert process.started is True
    assert result["status"] == "error"
    assert result["error_code"] == "oom_suspect"
    assert "simulated STT crash" in result["error"]


def test_subprocess_timeout_classified(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    process = _FakeProcess(alive=True)
    _patch_spawn(monkeypatch, process)
    monkeypatch.setenv("PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC", "1")
    monkeypatch.setattr(server, "_compute_checkpoint_path", lambda: str(tmp_path / "checkpoint.log"))

    result = server._run_stt_job_in_subprocess("job-timeout", "Khan01", str(tmp_path / "speaker.wav"), "ckb")

    assert process.started is True
    assert process.terminated is True
    assert result["status"] == "error"
    assert result["error_code"] == "timeout"
    assert "STT" in result["error"] or "stt" in result["error"].lower()


def test_full_pipeline_stt_step_routes_through_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_ensure_host_memory_for_step", lambda step: None)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_run_stt_job", lambda *_args, **_kwargs: pytest.fail("full-pipeline STT must be subprocess-isolated"))
    audio_path = tmp_path / "audio" / "working" / "Khan01" / "speaker.wav"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    calls: list[tuple[str, str, str, str | None]] = []

    def fake_subprocess(job_id: str, speaker: str, source_wav: str, language: str | None) -> dict[str, object]:
        calls.append((job_id, speaker, source_wav, language))
        return {"speaker": speaker, "segments": [{"text": "ok"}], "chunks": []}

    monkeypatch.setattr(server, "_pipeline_audio_path_for_speaker", lambda speaker: audio_path)
    monkeypatch.setattr(server, "_latest_stt_segments_for_speaker", lambda speaker: [])
    monkeypatch.setattr(server, "_run_stt_job_in_subprocess", fake_subprocess)

    result = server._compute_full_pipeline("job-pipeline", {"speaker": "Khan01", "steps": ["stt"], "language": "ckb"})

    assert calls == [("job-pipeline", "Khan01", str(audio_path), "ckb")]
    assert result["results"]["stt"] == {"status": "ok", "segments": 1, "done": True}


def test_compute_stt_full_mode_routes_through_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str, str | None]] = []
    monkeypatch.setattr(server, "_run_stt_job", lambda *_args, **_kwargs: pytest.fail("standalone full STT must use wrapper"))

    def fake_subprocess(job_id: str, speaker: str, source_wav: str, language: str | None) -> dict[str, object]:
        calls.append((job_id, speaker, source_wav, language))
        return {"speaker": speaker, "sourceWav": source_wav, "language": language, "segments": [], "chunks": []}

    monkeypatch.setattr(server, "_run_stt_job_in_subprocess", fake_subprocess)

    result = server._compute_stt("job-stt", {"speaker": "Khan01", "sourceWav": "audio/working/Khan01/speaker.wav", "language": "ckb"})

    assert calls == [("job-stt", "Khan01", "audio/working/Khan01/speaker.wav", "ckb")]
    assert result["chunks"] == []


def test_stt_subprocess_entry_forwards_env_and_writes_result(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", "99")
    result_path = tmp_path / "result.json"
    checkpoint_path = tmp_path / "checkpoint.log"
    seen: dict[str, object] = {}

    def fake_run(job_id: str, speaker: str, source_wav: str, language: str | None) -> dict[str, object]:
        seen.update(
            {
                "job_id": job_id,
                "speaker": speaker,
                "source_wav": source_wav,
                "language": language,
                "chunk_minutes": os.environ.get("PARSE_STT_DEFAULT_CHUNK_MINUTES"),
            }
        )
        return {"speaker": speaker, "segments": [], "chunks": [], "duration_sec": 0.0}

    monkeypatch.setattr(media, "_run_stt_job", fake_run)
    monkeypatch.setattr(server, "_compute_checkpoint", lambda *args, **kwargs: None)

    media._run_stt_job_subprocess_entry(
        "child-job",
        {
            "speaker": "Khan01",
            "source_wav": "speaker.wav",
            "language": "ckb",
            "env": {"PARSE_STT_DEFAULT_CHUNK_MINUTES": "7"},
        },
        str(result_path),
        str(checkpoint_path),
    )

    assert seen == {
        "job_id": "child-job",
        "speaker": "Khan01",
        "source_wav": "speaker.wav",
        "language": "ckb",
        "chunk_minutes": "7",
    }
    assert json.loads(result_path.read_text("utf-8")) == {
        "ok": True,
        "result": {"speaker": "Khan01", "segments": [], "chunks": [], "duration_sec": 0.0},
    }
