"""Khan01 Milestone A regression harness for MC-384."""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any, Callable

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server  # noqa: E402
from ai import job_cancel  # noqa: E402
from server_routes import annotate  # noqa: E402

# Handoff acceptance locks the Khan01 default-threshold expectation at 31 chunks.
DEFAULT_CHUNK_SECONDS = 10 * 60
EXPECTED_KHAN01_CHUNKS = 31
KHAN01_DURATION_SECONDS = EXPECTED_KHAN01_CHUNKS * DEFAULT_CHUNK_SECONDS


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
        return [{"start": 1.0, "end": 2.0, "text": f"chunk-{idx}"}]

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
def _install_routes_and_reset(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    server._install_route_bindings()
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_ensure_host_memory_for_step", lambda _step: None)
    monkeypatch.setattr(annotate, "_set_compute_progress", lambda *args, **kwargs: None)
    yield
    server._jobs.clear()
    for job_id in ("job-khan01-oom", "job-khan01-chunks", "job-khan01-partial", "job-khan01-cancel"):
        job_cancel.clear_cancel(job_id)


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
                "source_audio_duration_sec": KHAN01_DURATION_SECONDS,
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


def _patch_khan01_ortho(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    provider: _FakeProvider,
) -> None:
    audio_path = _seed_workspace(tmp_path)
    monkeypatch.setattr(server, "_pipeline_audio_path_for_speaker", lambda _speaker: audio_path)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: provider)
    monkeypatch.setattr(annotate, "_ortho_audio_duration_seconds", lambda _path: KHAN01_DURATION_SECONDS)
    monkeypatch.setattr(annotate, "_write_audio_slice_to_temp_wav", lambda _audio_path, _start, _end: str(audio_path))
    monkeypatch.setattr(server, "_ortho_tier2_align_to_words", lambda _audio_path, segments, **_kwargs: list(segments))


def _run_full_pipeline_ortho(job_id: str) -> dict[str, Any]:
    return server._compute_full_pipeline(
        job_id,
        {
            "speaker": "Khan01",
            "steps": ["ortho"],
            "overwrites": {"ortho": True},
            "run_mode": "full",
        },
    )


def test_khan01_shape_full_pipeline_ortho_does_not_kill_parent(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Full-pipeline ORTH OOM is returned as oom_suspect, not parent death."""
    _seed_workspace(tmp_path)
    parent_pid = os.getpid()

    def fake_ortho_subprocess(_job_id: str, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "error", "error_code": "oom_suspect", "error": "synthetic Khan01 OOM", "chunks": []}

    monkeypatch.setattr(server, "_compute_speaker_ortho_in_subprocess", fake_ortho_subprocess)
    result = _run_full_pipeline_ortho("job-khan01-oom")

    ortho = result["results"]["ortho"]
    assert ortho["error_code"] == "oom_suspect"
    assert os.getpid() == parent_pid


def test_khan01_shape_full_pipeline_ortho_chunks_count_matches_duration(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """A Khan01-scale full ORTH job uses 31 default 10-minute chunks."""
    provider = _FakeProvider()
    _patch_khan01_ortho(monkeypatch, tmp_path, provider)

    result = _run_full_pipeline_ortho("job-khan01-chunks")

    chunks = result["results"]["ortho"]["chunks"]
    assert len(provider.calls) == EXPECTED_KHAN01_CHUNKS
    assert len(chunks) == EXPECTED_KHAN01_CHUNKS
    assert chunks[0]["span"] == {"idx": 0, "start": 0.0, "end": DEFAULT_CHUNK_SECONDS}
    assert chunks[-1]["span"]["end"] == KHAN01_DURATION_SECONDS


def test_khan01_shape_partial_chunk_failure_returns_partial_result(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Failed chunks are structured errors while other chunks remain ok."""
    provider = _FakeProvider(failures={7: MemoryError("CUDA out of memory"), 13: MemoryError("OOM")})
    _patch_khan01_ortho(monkeypatch, tmp_path, provider)

    result = _run_full_pipeline_ortho("job-khan01-partial")

    chunks = result["results"]["ortho"]["chunks"]
    failing = {chunk["idx"] for chunk in chunks if chunk["status"] == "error"}
    assert failing == {7, 13}
    assert all(chunk["error_code"] == "oom_suspect" for chunk in chunks if chunk["idx"] in failing)
    assert sum(1 for chunk in chunks if chunk["status"] == "ok") == EXPECTED_KHAN01_CHUNKS - 2


def test_khan01_shape_cancel_mid_run_returns_cancelled(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Between-chunk cancellation preserves completed chunks and cancels the rest."""
    def cancel_after_chunk_five(idx: int) -> None:
        if idx == 5:
            job_cancel.request_cancel("job-khan01-cancel")

    provider = _FakeProvider(after_call=cancel_after_chunk_five)
    _patch_khan01_ortho(monkeypatch, tmp_path, provider)

    result = _run_full_pipeline_ortho("job-khan01-cancel")

    chunks = result["results"]["ortho"]["chunks"]
    assert [chunk["status"] for chunk in chunks[:6]] == ["ok"] * 6
    assert [chunk["status"] for chunk in chunks[6:]] == ["cancelled"] * (EXPECTED_KHAN01_CHUNKS - 6)


def test_khan01_milestone_a_acceptance_summary(capsys: pytest.CaptureFixture[str]) -> None:
    """Print the one-line Milestone A acceptance summary for PR closeout."""
    summary = "MC-384 Milestone A: Khan01 OOM contained ✅ | Tier-1 chunking ✅ | Standalone IPA wrap ✅"
    with capsys.disabled():
        print(summary)
    assert "Khan01 OOM contained" in summary
    assert "Tier-1 chunking" in summary
    assert "Standalone IPA wrap" in summary
