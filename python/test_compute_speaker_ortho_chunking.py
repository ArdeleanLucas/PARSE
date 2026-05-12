from __future__ import annotations

import json
import pathlib
import resource
import sys
import time
from typing import Any, Callable

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402
from ai import job_cancel  # noqa: E402
from server_routes import annotate  # noqa: E402


class _FakeProvider:
    refine_lexemes = False

    def __init__(
        self,
        *,
        response_factory: Callable[[int, dict[str, Any]], list[dict[str, Any]]] | None = None,
        failures: dict[int, BaseException] | None = None,
        after_call: Callable[[int], None] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response_factory = response_factory or self._default_response
        self.failures = failures or {}
        self.after_call = after_call

    def _default_response(self, idx: int, _kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"start": 10.0, "end": 20.0, "text": f"chunk-{idx}"}]

    def transcribe(self, **kwargs: Any) -> list[dict[str, Any]]:
        idx = len(self.calls)
        self.calls.append(dict(kwargs))
        if self.after_call is not None:
            self.after_call(idx)
        failure = self.failures.get(idx)
        if failure is not None:
            raise failure
        return self.response_factory(idx, kwargs)


@pytest.fixture(autouse=True)
def _install_routes_and_clear_cancel(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    server._install_route_bindings()
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(annotate, "_set_compute_progress", lambda *args, **kwargs: None)
    yield
    server._jobs.clear()
    job_cancel.clear_cancel("job-ortho")
    job_cancel.clear_cancel("job-khan")


def _seed_workspace(root: pathlib.Path, speaker: str = "Khan01") -> pathlib.Path:
    audio_path = root / "audio" / "working" / speaker / "synthetic.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    annotations_dir = root / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    (annotations_dir / f"{speaker}.parse.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "parse-test",
                "speaker": speaker,
                "source_audio": f"audio/working/{speaker}/synthetic.wav",
                "source_audio_duration_sec": 10.0,
                "tiers": {
                    "concept": {"type": "interval", "display_order": 3, "intervals": []},
                    "ortho": {"type": "interval", "display_order": 2, "intervals": []},
                    "ortho_words": {"type": "interval", "display_order": 4, "intervals": []},
                    "ipa": {"type": "interval", "display_order": 1, "intervals": []},
                    "speaker": {"type": "interval", "display_order": 5, "intervals": []},
                },
                "metadata": {"language_code": "sdh"},
            }
        ),
        encoding="utf-8",
    )
    return audio_path


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    *,
    duration: float,
    provider: _FakeProvider,
    tier2_calls: list[list[dict[str, Any]]] | None = None,
    temp_paths: list[pathlib.Path] | None = None,
) -> pathlib.Path:
    audio_path = _seed_workspace(tmp_path)
    monkeypatch.setattr(server, "_pipeline_audio_path_for_speaker", lambda _speaker: audio_path)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: provider)
    monkeypatch.setattr(annotate, "_ortho_audio_duration_seconds", lambda _path: duration)
    if temp_paths is not None:
        def fake_slice(_audio_path: pathlib.Path, start_sec: float, end_sec: float) -> str:
            path = tmp_path / f"chunk-{len(temp_paths)}-{int(start_sec)}-{int(end_sec)}.wav"
            path.write_bytes(b"chunk")
            temp_paths.append(path)
            return str(path)
        monkeypatch.setattr(annotate, "_write_audio_slice_to_temp_wav", fake_slice)
    else:
        monkeypatch.setattr(annotate, "_write_audio_slice_to_temp_wav", lambda _audio_path, start_sec, end_sec: str(audio_path))

    if tier2_calls is not None:
        def fake_tier2(_audio_path: pathlib.Path, segments: list[dict[str, Any]], **_kwargs: Any) -> list[dict[str, Any]]:
            tier2_calls.append([dict(segment) for segment in segments])
            return [{"start": segment["start"], "end": segment["end"], "text": segment["text"]} for segment in segments]
        monkeypatch.setattr(server, "_ortho_tier2_align_to_words", fake_tier2)
    else:
        monkeypatch.setattr(server, "_ortho_tier2_align_to_words", lambda _audio_path, segments, **_kwargs: list(segments))
    return audio_path


def _run_ortho(provider: _FakeProvider, *, overwrite: bool = True) -> dict[str, Any]:
    return server._compute_speaker_ortho("job-ortho", {"speaker": "Khan01", "overwrite": overwrite}, provider=provider)


def test_short_audio_skips_chunking(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider()
    _patch_common(monkeypatch, tmp_path, duration=300.0, provider=provider)

    result = _run_ortho(provider)

    assert len(provider.calls) == 1
    assert provider.calls[0]["audio_path"].name == "synthetic.wav"
    assert result["chunks"] == []


def test_long_audio_splits_into_adjacent_chunks(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider()
    temp_paths: list[pathlib.Path] = []
    _patch_common(monkeypatch, tmp_path, duration=1850.0, provider=provider, temp_paths=temp_paths)

    result = _run_ortho(provider)

    assert len(provider.calls) == 4
    assert [chunk["span"] for chunk in result["chunks"]] == [
        {"idx": 0, "start": 0.0, "end": 600.0},
        {"idx": 1, "start": 600.0, "end": 1200.0},
        {"idx": 2, "start": 1200.0, "end": 1800.0},
        {"idx": 3, "start": 1800.0, "end": 1850.0},
    ]
    assert [chunk["status"] for chunk in result["chunks"]] == ["ok", "ok", "ok", "ok"]


def test_chunk_local_timestamps_offset_to_global(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider(response_factory=lambda idx, _kwargs: [{"start": 10.0, "end": 20.0, "text": f"chunk-{idx}"}])
    tier2_calls: list[list[dict[str, Any]]] = []
    _patch_common(monkeypatch, tmp_path, duration=1250.0, provider=provider, tier2_calls=tier2_calls)

    _run_ortho(provider)

    assert tier2_calls[0][1]["start"] == 610.0
    assert tier2_calls[0][1]["end"] == 620.0


def test_chunk_oom_error_code_oom_suspect_other_chunks_continue(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider(failures={2: MemoryError("CUDA out of memory")})
    tier2_calls: list[list[dict[str, Any]]] = []
    _patch_common(monkeypatch, tmp_path, duration=2500.0, provider=provider, tier2_calls=tier2_calls)

    result = _run_ortho(provider)

    assert len(provider.calls) == 5
    assert [chunk["status"] for chunk in result["chunks"]] == ["ok", "ok", "error", "ok", "ok"]
    assert result["chunks"][2]["error_code"] == "oom_suspect"
    assert [segment["text"] for segment in tier2_calls[0]] == ["chunk-0", "chunk-1", "chunk-3", "chunk-4"]


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RuntimeError("CUDA out of memory"), "oom_suspect"),
        (RuntimeError("connection timed out"), "timeout"),
        (RuntimeError("weird"), "provider_error"),
    ],
)
def test_chunk_provider_error_classified(exc: BaseException, expected: str) -> None:
    assert annotate._classify_chunk_error(exc) == expected


def test_cancel_between_chunks_stops_loop(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def cancel_after_second(idx: int) -> None:
        if idx == 1:
            job_cancel.request_cancel("job-ortho")

    provider = _FakeProvider(after_call=cancel_after_second)
    _patch_common(monkeypatch, tmp_path, duration=2500.0, provider=provider)

    result = _run_ortho(provider)

    assert len(provider.calls) == 2
    assert [chunk["status"] for chunk in result["chunks"]] == ["ok", "ok", "cancelled", "cancelled", "cancelled"]
    assert result["status"] == "cancelled"


def test_tier2_runs_over_merged_segments_unchanged(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider()
    tier2_calls: list[list[dict[str, Any]]] = []
    _patch_common(monkeypatch, tmp_path, duration=1250.0, provider=provider, tier2_calls=tier2_calls)

    _run_ortho(provider)

    assert len(tier2_calls) == 1
    assert [segment["start"] for segment in tier2_calls[0]] == [10.0, 610.0, 1210.0]


def test_temp_wav_files_cleaned_up_on_success(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider()
    temp_paths: list[pathlib.Path] = []
    _patch_common(monkeypatch, tmp_path, duration=1250.0, provider=provider, temp_paths=temp_paths)

    _run_ortho(provider)

    assert temp_paths
    assert all(not path.exists() for path in temp_paths)


def test_temp_wav_files_cleaned_up_on_exception(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider(failures={1: RuntimeError("weird")})
    temp_paths: list[pathlib.Path] = []
    _patch_common(monkeypatch, tmp_path, duration=1250.0, provider=provider, temp_paths=temp_paths)

    _run_ortho(provider)

    assert temp_paths
    assert all(not path.exists() for path in temp_paths)


def test_chunk_size_env_var_zero_disables_chunking(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_ORTH_DEFAULT_CHUNK_MINUTES", "0")
    provider = _FakeProvider()
    _patch_common(monkeypatch, tmp_path, duration=1850.0, provider=provider)

    result = _run_ortho(provider)

    assert len(provider.calls) == 1
    assert result["chunks"] == []


def test_chunk_size_env_var_invalid_falls_back_to_default(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_ORTH_DEFAULT_CHUNK_MINUTES", "garbage")
    provider = _FakeProvider()
    _patch_common(monkeypatch, tmp_path, duration=1850.0, provider=provider)

    result = _run_ortho(provider)

    assert len(provider.calls) == 4
    assert result["chunks"][-1]["span"] == {"idx": 3, "start": 1800.0, "end": 1850.0}


def test_result_dict_includes_chunks_field(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _FakeProvider()
    _patch_common(monkeypatch, tmp_path, duration=300.0, provider=provider)

    result = _run_ortho(provider)

    assert "chunks" in result
    assert isinstance(result["chunks"], list)


def test_khan01_shape_chunked_ortho_does_not_oom(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def response_factory(idx: int, _kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        time.sleep(0.05)
        return [
            {"start": float(j * 5), "end": float(j * 5 + 2), "text": f"chunk-{idx}-seg-{j}"}
            for j in range(5)
        ]

    provider = _FakeProvider(response_factory=response_factory)
    tier2_calls: list[list[dict[str, Any]]] = []
    temp_paths: list[pathlib.Path] = []
    _patch_common(monkeypatch, tmp_path, duration=18130.0, provider=provider, tier2_calls=tier2_calls, temp_paths=temp_paths)
    baseline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()

    result = server._compute_speaker_ortho("job-khan", {"speaker": "Khan01", "overwrite": True}, provider=provider)

    elapsed = time.perf_counter() - started
    final_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert len(provider.calls) == 31
    assert len(result["chunks"]) == 31
    assert elapsed < 30.0
    assert final_rss <= max(baseline_rss * 2, baseline_rss + 64 * 1024)
    assert tier2_calls[0][0]["start"] == 0.0
    assert tier2_calls[0][5]["start"] == 600.0
    assert tier2_calls[0][-1]["end"] == 18022.0
    assert all(not path.exists() for path in temp_paths)
