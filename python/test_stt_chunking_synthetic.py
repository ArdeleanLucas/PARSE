"""Synthetic long-audio STT chunking regression tests for MC-384-I."""

from __future__ import annotations

import pathlib
import sys
import tempfile
from typing import Any, Callable

import pytest
import soundfile as sf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402
from ai import job_cancel  # noqa: E402
from server_routes import media  # noqa: E402
from tests.fixtures.audio_synth import build_synthetic_long_wav  # noqa: E402

LONG_DURATION_SEC = 70.0 * 60.0
DEFAULT_CHUNK_MINUTES = "10"
EXPECTED_LONG_CHUNKS = 7


class _MockSTTProvider:
    """Deterministic provider that emits one chunk-local segment per call."""

    def __init__(
        self,
        *,
        failures: dict[int, BaseException] | None = None,
        after_call: Callable[[int], None] | None = None,
    ) -> None:
        self.calls: list[pathlib.Path] = []
        self.failures = failures or {}
        self.after_call = after_call

    def transcribe(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        audio_path = kwargs.get("audio_path") if kwargs else None
        if audio_path is None and args:
            audio_path = args[0]
        path = pathlib.Path(audio_path)
        idx = len(self.calls)
        self.calls.append(path)
        if self.after_call is not None:
            self.after_call(idx)
        failure = self.failures.get(idx)
        if failure is not None:
            raise failure
        info = sf.info(str(path))
        duration = float(info.duration)
        return [
            {
                "start": 0.0,
                "end": duration,
                "text": f"chunk-{idx}",
                "confidence": 1.0,
                "words": [{"start": 0.0, "end": duration, "word": f"chunk-{idx}"}],
            }
        ]


@pytest.fixture(autouse=True)
def _install_routes_and_reset(monkeypatch: pytest.MonkeyPatch):
    server._install_route_bindings()
    server._jobs.clear()
    monkeypatch.setattr(server, "_ensure_host_memory_for_step", lambda _step: None)
    yield
    server._jobs.clear()
    for job_id in (
        "job-short",
        "job-long-default",
        "job-long-disabled",
        "job-long-invalid-env",
        "job-long-failure",
        "job-long-cancel",
        "job-long-absolute",
        "job-long-temp-cleanup",
    ):
        job_cancel.clear_cancel(job_id)


@pytest.fixture(scope="session")
def long_wav_workspace(tmp_path_factory: pytest.TempPathFactory) -> tuple[pathlib.Path, pathlib.Path]:
    root = tmp_path_factory.mktemp("stt_chunking_workspace")
    wav_path = root / "audio" / "working" / "Synth01" / "long.wav"
    build_synthetic_long_wav(LONG_DURATION_SEC, speech_pattern="tile", output_path=wav_path)
    return root, wav_path


def _relative_to_workspace(root: pathlib.Path, wav_path: pathlib.Path) -> str:
    return str(wav_path.relative_to(root))


def _run_stt_with_provider(
    monkeypatch: pytest.MonkeyPatch,
    root: pathlib.Path,
    wav_path: pathlib.Path,
    provider: _MockSTTProvider,
    *,
    job_id: str,
) -> dict[str, Any]:
    monkeypatch.setattr(server, "_project_root", lambda: root)
    monkeypatch.setattr(media._server, "get_stt_provider", lambda: provider)
    return media._run_stt_job(
        job_id=job_id,
        speaker="Synth01",
        source_wav=_relative_to_workspace(root, wav_path),
        language=None,
    )


def _require_chunked_stt_contract(result: dict[str, Any]) -> list[dict[str, Any]]:
    if "chunks" not in result:
        if not hasattr(media, "_stt_default_chunk_seconds"):
            pytest.skip("waiting for MC-384-H")
        pytest.fail("MC-384-H STT chunking contract missing result['chunks']")
    chunks = result["chunks"]
    assert isinstance(chunks, list)
    return chunks


def test_audio_synth_tile_writes_expected_duration(tmp_path: pathlib.Path) -> None:
    wav_path, intervals = build_synthetic_long_wav(12.5, speech_pattern="tile", output_path=tmp_path / "tile.wav")

    assert wav_path == tmp_path / "tile.wav"
    assert intervals == [{"start": 0.0, "end": 12.5, "kind": "speech"}]
    assert pytest.approx(sf.info(str(wav_path)).duration, abs=0.001) == 12.5


def test_audio_synth_speech_then_silence_intervals(tmp_path: pathlib.Path) -> None:
    wav_path, intervals = build_synthetic_long_wav(
        1200.0,
        speech_pattern="speech_then_silence",
        output_path=tmp_path / "speech_then_silence.wav",
    )

    assert pytest.approx(sf.info(str(wav_path)).duration, abs=0.001) == 1200.0
    assert intervals == [
        {"start": 0.0, "end": 900.0, "kind": "speech"},
        {"start": 900.0, "end": 1200.0, "kind": "silence"},
    ]


def test_audio_synth_rejects_unknown_pattern(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="Unknown speech_pattern"):
        build_synthetic_long_wav(1.0, speech_pattern="bogus", output_path=tmp_path / "bad.wav")


def test_short_audio_single_shot_no_chunks(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    wav_path = tmp_path / "audio" / "working" / "Synth01" / "short.wav"
    build_synthetic_long_wav(60.0, speech_pattern="tile", output_path=wav_path)
    provider = _MockSTTProvider()

    result = _run_stt_with_provider(monkeypatch, tmp_path, wav_path, provider, job_id="job-short")
    chunks = _require_chunked_stt_contract(result)

    assert chunks == []
    assert len(provider.calls) == 1
    assert result["segments"] == [
        {
            "start": 0.0,
            "end": 60.0,
            "text": "chunk-0",
            "confidence": 1.0,
            "words": [{"start": 0.0, "end": 60.0, "word": "chunk-0"}],
        }
    ]


def test_long_audio_chunked_default(
    monkeypatch: pytest.MonkeyPatch,
    long_wav_workspace: tuple[pathlib.Path, pathlib.Path],
) -> None:
    root, wav_path = long_wav_workspace
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", DEFAULT_CHUNK_MINUTES)
    provider = _MockSTTProvider()

    result = _run_stt_with_provider(monkeypatch, root, wav_path, provider, job_id="job-long-default")
    chunks = _require_chunked_stt_contract(result)

    assert len(chunks) == EXPECTED_LONG_CHUNKS
    assert all(chunk["status"] == "ok" for chunk in chunks)
    assert len(provider.calls) == EXPECTED_LONG_CHUNKS
    assert all(call != wav_path for call in provider.calls)
    assert result["segments"][0]["start"] == 0.0
    assert result["segments"][-1]["end"] == pytest.approx(LONG_DURATION_SEC, abs=0.001)


def test_long_audio_chunking_disabled(
    monkeypatch: pytest.MonkeyPatch,
    long_wav_workspace: tuple[pathlib.Path, pathlib.Path],
) -> None:
    root, wav_path = long_wav_workspace
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", "0")
    provider = _MockSTTProvider()

    result = _run_stt_with_provider(monkeypatch, root, wav_path, provider, job_id="job-long-disabled")
    chunks = _require_chunked_stt_contract(result)

    assert chunks == []
    assert provider.calls == [wav_path]
    assert result["segments"][-1]["end"] == pytest.approx(LONG_DURATION_SEC, abs=0.001)


def test_long_audio_invalid_env_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    long_wav_workspace: tuple[pathlib.Path, pathlib.Path],
) -> None:
    root, wav_path = long_wav_workspace
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", "abc")
    provider = _MockSTTProvider()

    with caplog.at_level("WARNING", logger="server_routes.media"):
        result = _run_stt_with_provider(monkeypatch, root, wav_path, provider, job_id="job-long-invalid-env")
    chunks = _require_chunked_stt_contract(result)

    assert len(chunks) == EXPECTED_LONG_CHUNKS
    assert len(provider.calls) == EXPECTED_LONG_CHUNKS
    assert "Invalid PARSE_STT_DEFAULT_CHUNK_MINUTES" in caplog.text


def test_chunk_failure_continues_loop(
    monkeypatch: pytest.MonkeyPatch,
    long_wav_workspace: tuple[pathlib.Path, pathlib.Path],
) -> None:
    root, wav_path = long_wav_workspace
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", DEFAULT_CHUNK_MINUTES)
    provider = _MockSTTProvider(failures={2: MemoryError("CUDA out of memory")})

    result = _run_stt_with_provider(monkeypatch, root, wav_path, provider, job_id="job-long-failure")
    chunks = _require_chunked_stt_contract(result)

    assert len(provider.calls) == EXPECTED_LONG_CHUNKS
    assert chunks[2]["status"] == "error"
    assert chunks[2]["error_code"] == "oom_suspect"
    assert [chunk["status"] for chunk in chunks[:2]] == ["ok", "ok"]
    assert [chunk["status"] for chunk in chunks[3:]] == ["ok"] * 4
    assert {segment["text"] for segment in result["segments"]} == {
        "chunk-0",
        "chunk-1",
        "chunk-3",
        "chunk-4",
        "chunk-5",
        "chunk-6",
    }
    assert result["segments"][-1]["end"] == pytest.approx(LONG_DURATION_SEC, abs=0.001)


def test_cancel_between_chunks(
    monkeypatch: pytest.MonkeyPatch,
    long_wav_workspace: tuple[pathlib.Path, pathlib.Path],
) -> None:
    root, wav_path = long_wav_workspace
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", DEFAULT_CHUNK_MINUTES)
    job_id = "job-long-cancel"

    def cancel_after_first_chunk(idx: int) -> None:
        if idx == 0:
            job_cancel.request_cancel(job_id)

    provider = _MockSTTProvider(after_call=cancel_after_first_chunk)

    result = _run_stt_with_provider(monkeypatch, root, wav_path, provider, job_id=job_id)
    chunks = _require_chunked_stt_contract(result)

    assert len(provider.calls) == 1
    assert chunks[0]["status"] == "ok"
    assert [chunk["status"] for chunk in chunks[1:]] == ["cancelled"] * (EXPECTED_LONG_CHUNKS - 1)
    assert result["status"] == "cancelled"


def test_timestamps_are_absolute_after_merge(
    monkeypatch: pytest.MonkeyPatch,
    long_wav_workspace: tuple[pathlib.Path, pathlib.Path],
) -> None:
    root, wav_path = long_wav_workspace
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", DEFAULT_CHUNK_MINUTES)
    provider = _MockSTTProvider()

    result = _run_stt_with_provider(monkeypatch, root, wav_path, provider, job_id="job-long-absolute")
    _require_chunked_stt_contract(result)

    second_segment = result["segments"][1]
    assert second_segment["text"] == "chunk-1"
    assert second_segment["start"] == pytest.approx(600.0, abs=0.001)
    assert second_segment["end"] == pytest.approx(1200.0, abs=0.001)
    assert second_segment["words"] == [{"start": 600.0, "end": 1200.0, "word": "chunk-1"}]


def test_temp_files_cleaned_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    long_wav_workspace: tuple[pathlib.Path, pathlib.Path],
) -> None:
    root, wav_path = long_wav_workspace
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", DEFAULT_CHUNK_MINUTES)
    temp_root = tmp_path / "chunk-temp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    before = set(temp_root.glob("*.wav"))
    provider = _MockSTTProvider()

    result = _run_stt_with_provider(monkeypatch, root, wav_path, provider, job_id="job-long-temp-cleanup")
    _require_chunked_stt_contract(result)

    after = set(temp_root.glob("*.wav"))
    assert after == before
    assert provider.calls
    assert {call.parent for call in provider.calls} == {temp_root}
    assert all(not call.exists() for call in provider.calls)
