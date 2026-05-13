"""Mocked-provider full-pipeline integration tests for MC-384-Q.

These tests drive the real full-pipeline sequencer across normalize → STT →
ORTH → IPA boundaries while replacing only model/audio-heavy providers. They
assert long-audio chunk envelopes survive the Tier-1 boundary and that Tier-3
IPA writes interval-aligned output from the ORTH tier without loading models.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
from typing import Any

import pytest
import soundfile as sf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402
from ai import job_cancel  # noqa: E402
from tests.fixtures.audio_synth import build_synthetic_long_wav  # noqa: E402

LONG_DURATION_SEC = 70.0 * 60.0
SHORT_DURATION_SEC = 60.0
SHRINK_PROJECTED_DURATION_SEC = 1500.0
DEFAULT_CHUNK_MINUTES = "10"
EXPECTED_LONG_CHUNKS = 7


class _MockTier1Provider:
    """Deterministic STT/ORTH provider returning one chunk-local segment per call."""

    def __init__(self, *, failures: dict[int, BaseException] | None = None, text_prefix: str = "chunk") -> None:
        self.calls: list[pathlib.Path] = []
        self.failures = failures or {}
        self.text_prefix = text_prefix
        self.refine_lexemes = False

    def transcribe(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        audio_path = kwargs.get("audio_path") if kwargs else None
        if audio_path is None and args:
            audio_path = args[0]
        path = pathlib.Path(audio_path)
        idx = len(self.calls)
        self.calls.append(path)
        failure = self.failures.get(idx)
        if failure is not None:
            raise failure
        duration = float(sf.info(str(path)).duration)
        segment = {
            "start": 0.0,
            "end": duration,
            "text": f"{self.text_prefix}-{idx}",
            "confidence": 0.99,
            # Keep words empty so the IPA step exercises interval-driven Tier 3
            # from ORTH intervals rather than the word forced-align branch.
            "words": [],
        }
        callback = kwargs.get("segment_callback")
        if callable(callback):
            callback(dict(segment))
        return [segment]

    def unload_model(self) -> None:
        return None


class _FakeTensor:
    def __init__(self, sample_count: int = 16_000) -> None:
        self._sample_count = int(sample_count)

    def numel(self) -> int:
        return self._sample_count


@pytest.fixture(autouse=True)
def _install_routes_and_reset(monkeypatch: pytest.MonkeyPatch):
    server._install_route_bindings()
    server._jobs.clear()
    monkeypatch.setattr(server, "_ensure_host_memory_for_step", lambda _step: None)
    monkeypatch.setattr(server, "_ensure_free_gpu_memory_for_ipa", lambda: None, raising=False)
    monkeypatch.setattr(server, "_gpu_free_memory_gb", lambda: 16.0)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_collect_after_unload", lambda: None)
    yield
    server._jobs.clear()
    for job_id in (
        "job-long-all-stages",
        "job-long-stt-failure",
        "job-ipa-shrink-warning",
        "job-short-all-stages",
    ):
        job_cancel.clear_cancel(job_id)


@pytest.fixture(scope="session")
def long_source_wav(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    wav_path = tmp_path_factory.mktemp("full_pipeline_long_audio") / "IntTest01.wav"
    build_synthetic_long_wav(LONG_DURATION_SEC, speech_pattern="tile", output_path=wav_path)
    return wav_path


def _seed_workspace(
    tmp_path: pathlib.Path,
    *,
    speaker: str,
    duration_sec: float,
    source_wav: pathlib.Path | None = None,
    existing_ipa: list[dict[str, Any]] | None = None,
) -> pathlib.Path:
    source_rel = pathlib.Path("raw") / f"{speaker}.wav"
    source_path = tmp_path / source_rel
    source_path.parent.mkdir(parents=True, exist_ok=True)
    if source_wav is None:
        build_synthetic_long_wav(duration_sec, speech_pattern="tile", output_path=source_path)
    else:
        try:
            source_path.hardlink_to(source_wav)
        except OSError:
            shutil.copy2(source_wav, source_path)
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    annotation = {
        "version": 1,
        "project_id": "integration-test",
        "speaker": speaker,
        "source_audio": str(source_rel).replace("\\", "/"),
        "source_audio_duration_sec": float(duration_sec),
        "tiers": {
            "ipa": {"type": "interval", "display_order": 1, "intervals": existing_ipa or []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "concept": {"type": "interval", "display_order": 3, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {
            "language_code": "sdh",
            "created": "2026-01-01T00:00:00Z",
            "modified": "2026-01-01T00:00:00Z",
        },
    }
    (annotations_dir / f"{speaker}.parse.json").write_text(json.dumps(annotation), encoding="utf-8")
    return source_path


def _load_annotation(root: pathlib.Path, speaker: str) -> dict[str, Any]:
    return json.loads((root / "annotations" / f"{speaker}.parse.json").read_text(encoding="utf-8"))


def _install_pipeline_mocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    *,
    stt_provider: _MockTier1Provider | None = None,
    ortho_provider: _MockTier1Provider | None = None,
) -> tuple[_MockTier1Provider, _MockTier1Provider, list[dict[str, Any]]]:
    stt_provider = stt_provider or _MockTier1Provider(text_prefix="stt")
    ortho_provider = ortho_provider or _MockTier1Provider(text_prefix="ortho")
    ipa_calls: list[dict[str, Any]] = []
    snapshots: dict[str, dict[str, Any]] = {}

    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    def primary_source_from_annotation(speaker: str) -> str:
        annotation_path = tmp_path / "annotations" / f"{speaker}.parse.json"
        if not annotation_path.is_file():
            return ""
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        return str(annotation.get("source_audio") or annotation.get("source_wav") or "").strip()

    monkeypatch.setattr(server, "_annotation_primary_source_wav", primary_source_from_annotation)
    monkeypatch.setenv("PARSE_STT_DEFAULT_CHUNK_MINUTES", DEFAULT_CHUNK_MINUTES)
    monkeypatch.setenv("PARSE_ORTH_DEFAULT_CHUNK_MINUTES", DEFAULT_CHUNK_MINUTES)
    monkeypatch.setenv("PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC", "60")
    monkeypatch.setattr(server, "get_stt_provider", lambda: stt_provider)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: ortho_provider)
    monkeypatch.setattr(server, "_get_ipa_aligner", lambda: object())
    monkeypatch.setattr(server, "_release_ipa_aligner", lambda: None)

    def fake_normalize(job_id: str, speaker: str, source_rel: str) -> None:
        source_path = server._resolve_project_path(source_rel)
        working_dir = server._project_root() / "audio" / "working" / speaker
        working_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = server.build_normalized_output_path(source_path, working_dir)
        try:
            normalized_path.hardlink_to(source_path)
        except OSError:
            shutil.copy2(source_path, normalized_path)
        snapshots[job_id] = {
            "status": "complete",
            "result": {
                "done": True,
                "path": str(normalized_path.relative_to(server._project_root())).replace("\\", "/"),
            },
        }

    def fake_get_job_snapshot(job_id: str) -> dict[str, Any]:
        return snapshots.get(job_id, {"status": "running"})

    def fake_reset_job_to_running(job_id: str) -> None:
        snapshots[job_id] = {"status": "running"}

    monkeypatch.setattr(server, "_run_normalize_job", fake_normalize)
    monkeypatch.setattr(server, "_get_job_snapshot", fake_get_job_snapshot)
    monkeypatch.setattr(server, "_reset_job_to_running", fake_reset_job_to_running)

    from ai import forced_align, ipa_transcribe

    monkeypatch.setattr(forced_align, "_load_audio_mono_16k", lambda _path: _FakeTensor())

    def fake_transcribe_slice_structured(_audio_tensor: Any, start: float, end: float, _aligner: Any) -> dict[str, Any]:
        call = {"start": float(start), "end": float(end), "ipa": f"ipa-{len(ipa_calls)}"}
        ipa_calls.append(call)
        return {
            "raw_ipa": call["ipa"],
            "model": "mock-xlsr",
            "model_version": "mock-xlsr-test",
            "decoded_at": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(ipa_transcribe, "transcribe_slice_structured", fake_transcribe_slice_structured)

    def inline_ipa(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        sub_result = server._compute_speaker_ipa(job_id, payload)
        return server._full_pipeline_ipa_step_result(dict(sub_result))

    monkeypatch.setattr(server, "_compute_full_pipeline_ipa_in_subprocess", inline_ipa)
    return stt_provider, ortho_provider, ipa_calls


def _run_full_pipeline(speaker: str, job_id: str) -> dict[str, Any]:
    return server._compute_full_pipeline(
        job_id,
        {
            "speaker": speaker,
            "steps": ["normalize", "stt", "ortho", "ipa"],
            "overwrites": {"normalize": True, "stt": True, "ortho": True, "ipa": True},
            "run_mode": "full",
            "language": "sdh",
        },
    )


def test_full_pipeline_long_audio_all_three_stages_complete(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    long_source_wav: pathlib.Path,
) -> None:
    speaker = "IntTest01"
    _seed_workspace(tmp_path, speaker=speaker, duration_sec=LONG_DURATION_SEC, source_wav=long_source_wav)
    stt_provider, ortho_provider, ipa_calls = _install_pipeline_mocks(monkeypatch, tmp_path)

    result = _run_full_pipeline(speaker, "job-long-all-stages")

    assert result["steps_run"] == ["normalize", "stt", "ortho", "ipa"]
    assert {step: payload["status"] for step, payload in result["results"].items()} == {
        "normalize": "ok",
        "stt": "ok",
        "ortho": "ok",
        "ipa": "ok",
    }
    stt_chunks = result["results"]["stt"]["chunks"]
    assert len(stt_chunks) == EXPECTED_LONG_CHUNKS
    assert all(chunk["status"] == "ok" for chunk in stt_chunks)
    assert len(stt_provider.calls) == EXPECTED_LONG_CHUNKS
    assert len(ortho_provider.calls) == EXPECTED_LONG_CHUNKS

    annotation = _load_annotation(tmp_path, speaker)
    ortho_intervals = annotation["tiers"]["ortho"]["intervals"]
    ipa_intervals = annotation["tiers"]["ipa"]["intervals"]
    assert ortho_intervals[0]["start"] == pytest.approx(0.0, abs=0.001)
    assert ortho_intervals[-1]["end"] == pytest.approx(LONG_DURATION_SEC, abs=0.001)
    assert result["results"]["ipa"]["filled"] == len(ortho_intervals)
    assert len(ipa_calls) == len(ortho_intervals)
    assert [(iv["start"], iv["end"]) for iv in ipa_intervals] == [
        (iv["start"], iv["end"]) for iv in ortho_intervals
    ]


def test_full_pipeline_stt_chunk_failure_does_not_block_ortho_ipa(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    long_source_wav: pathlib.Path,
) -> None:
    speaker = "IntTest02"
    _seed_workspace(tmp_path, speaker=speaker, duration_sec=LONG_DURATION_SEC, source_wav=long_source_wav)
    stt_provider = _MockTier1Provider(failures={2: MemoryError("CUDA out of memory")}, text_prefix="stt")
    _stt_provider, ortho_provider, ipa_calls = _install_pipeline_mocks(
        monkeypatch,
        tmp_path,
        stt_provider=stt_provider,
        ortho_provider=_MockTier1Provider(text_prefix="ortho"),
    )

    result = _run_full_pipeline(speaker, "job-long-stt-failure")

    stt_result = result["results"]["stt"]
    assert stt_result["status"] == "ok"
    assert len(stt_result["chunks"]) == EXPECTED_LONG_CHUNKS
    assert stt_result["chunks"][2]["status"] == "error"
    assert stt_result["chunks"][2]["error_code"] == "oom_suspect"
    assert result["results"]["ortho"]["status"] == "ok"
    assert result["results"]["ipa"]["status"] == "ok"
    assert len(ortho_provider.calls) == EXPECTED_LONG_CHUNKS
    assert ipa_calls


def test_full_pipeline_ipa_overwrite_shrink_warning_surfaces(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    speaker = "IntTest03"
    _seed_workspace(
        tmp_path,
        speaker=speaker,
        duration_sec=SHRINK_PROJECTED_DURATION_SEC,
        existing_ipa=[{"start": 0.0, "end": 8000.0, "text": "existing long coverage"}],
    )
    _install_pipeline_mocks(monkeypatch, tmp_path)

    result = _run_full_pipeline(speaker, "job-ipa-shrink-warning")

    assert result["results"]["ipa"]["status"] == "ok"
    assert result["results"]["ipa"]["coverage_shrink_warning"] == {
        "previous_end": 8000.0,
        "projected_end": SHRINK_PROJECTED_DURATION_SEC,
        "previous_count": 1,
    }


def test_full_pipeline_short_audio_no_chunking_all_stages_run(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    speaker = "IntTest04"
    _seed_workspace(tmp_path, speaker=speaker, duration_sec=SHORT_DURATION_SEC)
    stt_provider, ortho_provider, ipa_calls = _install_pipeline_mocks(monkeypatch, tmp_path)

    result = _run_full_pipeline(speaker, "job-short-all-stages")

    assert {step: payload["status"] for step, payload in result["results"].items()} == {
        "normalize": "ok",
        "stt": "ok",
        "ortho": "ok",
        "ipa": "ok",
    }
    assert result["results"]["stt"]["chunks"] == []
    assert len(stt_provider.calls) == 1
    assert len(ortho_provider.calls) == 1
    assert ipa_calls == [{"start": 0.0, "end": SHORT_DURATION_SEC, "ipa": "ipa-0"}]
