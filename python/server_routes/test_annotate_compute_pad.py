from __future__ import annotations

import json
import pathlib
import sys
from http import HTTPStatus
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server  # noqa: E402


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, body: dict[str, Any] | None = None) -> None:
        self._body = {} if body is None else body
        self.sent_json: list[tuple[HTTPStatus, dict[str, Any]]] = []

    def _read_json_body(self, required: bool = True) -> dict[str, Any]:
        return self._body

    def _expect_object(self, value: Any, _label: str) -> dict[str, Any]:
        assert isinstance(value, dict)
        return value

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self.sent_json.append((status, payload))


class _FullOrthoProvider:
    def __init__(self) -> None:
        self.transcribe_calls: list[dict[str, Any]] = []

    def transcribe(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.transcribe_calls.append(dict(kwargs))
        return []


class _ClipProvider:
    pass


def _seed_annotation(
    tmp_path: pathlib.Path,
    *,
    speaker: str = "Fail02",
    concept_intervals: list[dict[str, Any]] | None = None,
    ortho_intervals: list[dict[str, Any]] | None = None,
) -> pathlib.Path:
    (tmp_path / "annotations").mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio" / "working" / speaker / "synthetic.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFFWAVEfake")
    payload = {
        "version": 1,
        "project_id": "parse-test",
        "speaker": speaker,
        "source_audio": f"audio/working/{speaker}/synthetic.wav",
        "source_audio_duration_sec": 8.0,
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": concept_intervals
                or [{"start": 1.0, "end": 1.5, "text": "root", "concept_id": "1"}],
            },
            "ortho": {"type": "interval", "display_order": 2, "intervals": ortho_intervals or []},
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho_words": {
                "type": "interval",
                "display_order": 4,
                "intervals": [
                    {"start": 0.2, "end": 0.4, "text": "OUTSIDE_BEFORE", "source": "seed"},
                    {"start": 1.0, "end": 1.25, "text": "OLD", "source": "seed"},
                    {"start": 1.25, "end": 1.5, "text": "ROOT", "source": "seed"},
                    {"start": 2.0, "end": 2.2, "text": "OUTSIDE_AFTER", "source": "seed"},
                ],
            },
            "speaker": {"type": "interval", "display_order": 5, "intervals": []},
        },
        "metadata": {"language_code": "sdh"},
    }
    (tmp_path / "annotations" / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")
    return audio_path


def _patch_common(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_pipeline_audio_path_for_speaker", lambda speaker: tmp_path / "audio" / "working" / speaker / "synthetic.wav")


def _capture_concept_window_runner(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_runner(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(dict(kwargs))
        step = str(kwargs["step"])
        return [
            {
                "start": 1.0,
                "end": 1.5,
                "text": f"{step}-window",
                "conceptId": "1",
                "source": f"concept_window_{step}",
            }
        ]

    monkeypatch.setattr(server, "_run_step_on_concept_windows", fake_runner)
    return calls


def _run_ortho_concept_windows(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> dict[str, Any]:
    _patch_common(monkeypatch, tmp_path)
    _seed_annotation(tmp_path)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: _ClipProvider())
    return server._compute_speaker_ortho("job-ortho", {"speaker": "Fail02", "run_mode": "concept-windows", **payload})


def test_compute_speaker_ortho_concept_windows_default_pad_is_0_20(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_concept_window_runner(monkeypatch)

    result = _run_ortho_concept_windows(tmp_path, monkeypatch, {})

    assert calls[0]["pad_sec"] == 0.2
    assert result["pad"] == 0.2


def test_compute_speaker_ortho_concept_windows_rebuilds_ortho_words(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_concept_window_runner(monkeypatch)
    align_calls: list[dict[str, Any]] = []

    def fake_align(audio_path: pathlib.Path, segments: list[dict[str, Any]], **_kwargs: Any) -> list[dict[str, Any]]:
        align_calls.append({"audio_path": audio_path, "segments": segments})
        words = segments[0]["words"]
        return [
            {"start": float(word["start"]), "end": float(word["end"]), "text": str(word["word"]), "source": "stub-align"}
            for word in words
        ]

    monkeypatch.setattr(server, "_ortho_tier2_align_to_words", fake_align)

    result = _run_ortho_concept_windows(tmp_path, monkeypatch, {})

    assert result["filled"] == 1
    assert calls[0]["step"] == "ortho"
    assert align_calls and align_calls[0]["segments"][0]["words"]
    annotation_path = tmp_path / "annotations" / "Fail02.parse.json"
    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    words = persisted["tiers"]["ortho_words"]["intervals"]
    inside = [iv["text"] for iv in words if 1.0 <= float(iv["start"]) and float(iv["end"]) <= 1.5]
    assert "-".join(inside) == "ortho-window"
    outside = [iv for iv in words if float(iv["end"]) <= 1.0 or float(iv["start"]) >= 1.5]
    assert outside == [
        {"start": 0.2, "end": 0.4, "text": "OUTSIDE_BEFORE", "source": "seed"},
        {"start": 2.0, "end": 2.2, "text": "OUTSIDE_AFTER", "source": "seed"},
    ]



def test_compute_speaker_ortho_concept_windows_writes_picked_lexeme_to_ortho_tier(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_concept_window_runner(monkeypatch)

    def fake_align(_audio_path: pathlib.Path, _segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"start": 1.0, "end": 1.18, "text": "the", "source": "stub-align"},
            {"start": 1.18, "end": 1.36, "text": "head", "source": "stub-align"},
            {"start": 1.36, "end": 1.5, "text": "is", "source": "stub-align"},
        ]

    monkeypatch.setattr(server, "_align_partial_ortho_words", fake_align)

    result = _run_ortho_concept_windows(tmp_path, monkeypatch, {})

    assert result["filled"] == 1
    annotation_path = tmp_path / "annotations" / "Fail02.parse.json"
    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    assert persisted["tiers"]["ortho"]["intervals"] == [
        {"start": 1.0, "end": 1.5, "text": "head", "conceptId": "1", "source": "concept_window_ortho"}
    ]
    assert [iv["text"] for iv in persisted["tiers"]["ortho_words"]["intervals"] if iv["source"] == "stub-align"] == [
        "the",
        "head",
        "is",
    ]

def test_compute_speaker_ortho_concept_windows_handles_align_failure_gracefully(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_common(monkeypatch, tmp_path)
    _seed_annotation(tmp_path)
    calls = _capture_concept_window_runner(monkeypatch)
    monkeypatch.setattr(server, "get_ortho_provider", lambda: _ClipProvider())
    monkeypatch.setattr(
        server,
        "_align_partial_ortho_words",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("wav2vec2 unavailable")),
    )
    annotation_path = tmp_path / "annotations" / "Fail02.parse.json"
    before = json.loads(annotation_path.read_text(encoding="utf-8"))
    before_words = before["tiers"]["ortho_words"]["intervals"]

    result = server._compute_speaker_ortho("job-ortho", {"speaker": "Fail02", "run_mode": "concept-windows"})

    assert result["filled"] == 1
    assert calls[0]["step"] == "ortho"
    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    ortho_inside = [
        iv["text"]
        for iv in persisted["tiers"]["ortho"]["intervals"]
        if 1.0 <= float(iv["start"]) and float(iv["end"]) <= 1.5
    ]
    assert ortho_inside == ["ortho-window"]
    assert persisted["tiers"]["ortho_words"]["intervals"] == before_words



def test_compute_speaker_ortho_concept_windows_keeps_multi_word_ortho_when_no_word_overlaps(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_concept_window_runner(monkeypatch)

    def fake_align(_audio_path: pathlib.Path, _segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"start": 0.1, "end": 0.4, "text": "outside", "source": "stub-align"},
            {"start": 1.6, "end": 1.9, "text": "after", "source": "stub-align"},
        ]

    monkeypatch.setattr(server, "_align_partial_ortho_words", fake_align)

    result = _run_ortho_concept_windows(tmp_path, monkeypatch, {})

    assert result["filled"] == 1
    annotation_path = tmp_path / "annotations" / "Fail02.parse.json"
    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    ortho_inside = [
        iv["text"]
        for iv in persisted["tiers"]["ortho"]["intervals"]
        if 1.0 <= float(iv["start"]) and float(iv["end"]) <= 1.5
    ]
    assert ortho_inside == ["ortho-window"]

def test_compute_speaker_ortho_concept_windows_explicit_pad_0_0(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_concept_window_runner(monkeypatch)

    result = _run_ortho_concept_windows(tmp_path, monkeypatch, {"pad": 0.0})

    assert calls[0]["pad_sec"] == 0.0
    assert result["pad"] == 0.0


def test_compute_speaker_ortho_concept_windows_explicit_pad_0_5(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_concept_window_runner(monkeypatch)

    result = _run_ortho_concept_windows(tmp_path, monkeypatch, {"pad": 0.5})

    assert calls[0]["pad_sec"] == 0.5
    assert result["pad"] == 0.5


def test_compute_speaker_ortho_concept_windows_invalid_pad_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail02", "run_mode": "concept-windows", "pad": 0.123})
    monkeypatch.setattr(server, "_compute_concept_scoped_noop_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_job_callback_url_from_mapping", lambda _body: None)
    monkeypatch.setattr(
        server,
        "_app_build_post_compute_start_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("invalid pad must not start a job")),
        raising=False,
    )

    with pytest.raises(server.ApiError) as excinfo:
        handler._api_post_compute_start("ortho")

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "pad must be one of 0.0, 0.2, 0.5"


def test_compute_speaker_stt_concept_windows_pad_threaded(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch, tmp_path)
    _seed_annotation(tmp_path)
    calls = _capture_concept_window_runner(monkeypatch)
    monkeypatch.setattr(server, "get_stt_provider", lambda: _ClipProvider())

    result = server._compute_speaker_stt("job-stt", {"speaker": "Fail02", "run_mode": "concept-windows", "pad": 0.5})

    assert calls[0]["step"] == "stt"
    assert calls[0]["pad_sec"] == 0.5
    assert result["pad"] == 0.5


def test_compute_speaker_ipa_concept_windows_pad_threaded(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch, tmp_path)
    _seed_annotation(tmp_path)
    calls = _capture_concept_window_runner(monkeypatch)
    monkeypatch.setattr(server, "_get_ipa_aligner", lambda: _ClipProvider())

    result = server._compute_speaker_ipa("job-ipa", {"speaker": "Fail02", "run_mode": "concept-windows", "pad": 0.5})

    assert calls[0]["step"] == "ipa"
    assert calls[0]["pad_sec"] == 0.5
    assert result["pad"] == 0.5


def test_compute_full_run_mode_ignores_pad(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch, tmp_path)
    _seed_annotation(tmp_path)
    provider = _FullOrthoProvider()
    monkeypatch.setattr(server, "_run_step_on_concept_windows", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("full mode must not run concept windows")))

    result = server._compute_speaker_ortho("job-ortho", {"speaker": "Fail02", "run_mode": "full", "pad": 0.5}, provider=provider)

    assert provider.transcribe_calls
    assert result["speaker"] == "Fail02"
    assert "pad" not in result


def test_concept_windows_result_payload_reports_pad(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_concept_window_runner(monkeypatch)

    result = _run_ortho_concept_windows(tmp_path, monkeypatch, {"pad": 0.5})

    assert calls[0]["pad_sec"] == 0.5
    assert result["pad"] == 0.5
    assert isinstance(result["pad"], float)
# ---------------------------------------------------------------------------
# MC-363: concept-windows ORTH must emit progress through the Tier-2 pass.
# ---------------------------------------------------------------------------


def test_run_step_on_concept_windows_honors_progress_max(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-window pct cap is callsite-controlled. The ORTH concept-windows
    path needs headroom (>=20%) for the Tier-2 alignment pass that follows;
    other steps (STT, IPA) can keep the historical 95% cap.
    """
    server._install_route_bindings()
    progress_events: list[tuple[float, str]] = []

    def fake_set_job_progress(job_id, progress, *, message="", **_):
        progress_events.append((float(progress), str(message)))

    monkeypatch.setattr(server, "_set_job_progress", fake_set_job_progress)

    # Stub forced_align audio loader and minimal numpy-y waveform.
    import numpy as np

    monkeypatch.setattr(
        "ai.forced_align._load_audio_mono_16k",
        lambda path: type("_T", (), {"squeeze": lambda self: self, "detach": lambda self: self,
                                      "cpu": lambda self: self, "numpy": lambda self: np.zeros(16000 * 30, dtype=np.float32)})(),
    )

    class _OrthoStub:
        def transcribe_clip(self, clip, **kw):
            return ("ok", 1.0)

    intervals = [
        {"start": float(i), "end": float(i) + 0.5, "concept_id": str(i)}
        for i in range(5)
    ]

    server._run_step_on_concept_windows(
        audio_path=tmp_path / "x.wav",
        concept_intervals=intervals,
        provider=_OrthoStub(),
        step="ortho",
        job_id="job-progmax",
        progress_max=70.0,
    )

    pct_values = [pct for pct, _msg in progress_events]
    assert pct_values, "expected at least one progress event"
    assert max(pct_values) <= 70.0 + 1e-6, (
        f"progress should cap at 70.0 when progress_max=70.0; saw max={max(pct_values)}"
    )
    # Last event should be near (but not exceeding) the cap.
    assert pct_values[-1] >= 60.0


def test_compute_speaker_ortho_concept_windows_emits_tier2_and_write_progress(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Between the per-window loop and the function return,
    `_compute_speaker_ortho_concept_windows` must emit progress events for the
    Tier-2 forced-alignment phase, the per-segment alignment ticks, the write
    phase, and the final 'concept-windows complete' marker. Without these the
    UI freezes at the loop's last event for the duration of forced alignment
    (~16 min on thesis-corpus WAVs)."""
    server._install_route_bindings()
    _patch_common(monkeypatch, tmp_path)
    _seed_annotation(tmp_path)

    progress_events: list[tuple[float, str]] = []

    def fake_set_job_progress(job_id, progress, *, message="", **_):
        progress_events.append((float(progress), str(message)))

    monkeypatch.setattr(server, "_set_job_progress", fake_set_job_progress)

    # Stub the heavy ORTH provider + concept-window runner so we test the
    # progress envelope, not the runner internals.
    monkeypatch.setattr(server, "get_ortho_provider", lambda: _ClipProvider())

    def fake_runner(*, job_id, progress_max=95.0, **kwargs):
        # Simulate the runner's progress emissions reaching its cap.
        if job_id:
            fake_set_job_progress(job_id, float(progress_max), message="ORTHO concept window 1/1")
        return [{"start": 1.0, "end": 1.5, "text": "ok", "conceptId": "1", "source": "concept_window_ortho"}]

    monkeypatch.setattr(server, "_run_step_on_concept_windows", fake_runner)

    # Stub Tier-2 aligner so we can verify it received a progress_callback and that
    # the callback emits compute-progress events into the 70..90 band.
    callback_holder: dict[str, Any] = {}

    def fake_align_partial(audio_path, rows, *, progress_callback=None):
        callback_holder["cb"] = progress_callback
        if progress_callback is not None:
            progress_callback(1, 2)
            progress_callback(2, 2)
        # Return at least one word interval so merge runs.
        return [{"start": 1.0, "end": 1.2, "text": "x", "source": "stub-align"}]

    monkeypatch.setattr(server, "_align_partial_ortho_words", fake_align_partial)

    server._compute_speaker_ortho(
        "job-prog",
        {"speaker": "Fail02", "run_mode": "concept-windows"},
    )

    messages = [msg for _pct, msg in progress_events]
    pcts = [pct for pct, _msg in progress_events]

    # Loop emission stays at-or-below 70 (the new ortho budget).
    loop_pcts = [p for p, m in progress_events if "ORTHO concept window" in m]
    assert loop_pcts and max(loop_pcts) <= 70.0 + 1e-6

    # Tier-2 phase announcement before alignment starts.
    assert any("Aligning ortho_words" in m for m in messages), messages

    # Tier-2 callback was wired and produced events strictly between 70 and 92.
    assert callback_holder.get("cb") is not None
    tier2_band = [p for p, m in progress_events if "Aligning ortho_words" in m and m != "Aligning ortho_words (Tier-2)"]
    # Per-segment ticks land in (70, 92).
    inside_band = [p for p in tier2_band if 70.0 < p < 92.0]
    assert inside_band, progress_events

    # Write phase event.
    assert any("Writing annotation" in m for m in messages), messages

    # Final concept-windows-complete event at 95.
    final = [p for p, m in progress_events if "concept-windows complete" in m.lower()]
    assert final and abs(final[-1] - 95.0) < 1e-6, progress_events
