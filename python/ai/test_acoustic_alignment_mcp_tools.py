"""MCP surface regression for the Tier 1/2/3 acoustic alignment tools.

Verifies that:
  - ParseChatTools registers the 6 new tool names.
  - JSON schemas reject missing required args.
  - Dry-run mode short-circuits before any callback fires.
  - Non-dry-run start handlers invoke the expected callback
    (start_stt_job or start_compute_job) with the right arguments.
  - Status handlers return a structured payload and reject wrong job types.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from ai.chat_tools import (
    ChatToolExecutionError,
    ChatToolValidationError,
    ParseChatTools,
)


TIER_TOOLS = {
    "stt_word_level_start",
    "stt_word_level_status",
    "forced_align_start",
    "forced_align_status",
    "ipa_transcribe_acoustic_start",
    "ipa_transcribe_acoustic_status",
}


def _make_tools(
    tmp_path: pathlib.Path,
    *,
    start_stt_calls: Optional[List[Tuple[str, str, Optional[str]]]] = None,
    start_compute_calls: Optional[List[Tuple[str, Dict[str, Any]]]] = None,
    snapshots: Optional[Dict[str, Dict[str, Any]]] = None,
) -> ParseChatTools:
    snapshots = snapshots or {}

    def _start_stt(speaker: str, source_wav: str, language: Optional[str]) -> str:
        if start_stt_calls is not None:
            start_stt_calls.append((speaker, source_wav, language))
        return "job-stt-1"

    def _start_compute(compute_type: str, payload: Dict[str, Any]) -> str:
        if start_compute_calls is not None:
            start_compute_calls.append((compute_type, dict(payload)))
        return "job-compute-{0}".format(compute_type)

    def _get_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
        return snapshots.get(job_id)

    resolved_root = tmp_path.resolve()  # macOS /tmp -> /private/tmp symlink
    (resolved_root / "audio").mkdir(exist_ok=True)
    (resolved_root / "audio" / "clip.wav").write_bytes(b"RIFFWAVE")

    return ParseChatTools(
        project_root=resolved_root,
        start_stt_job=_start_stt,
        get_job_snapshot=_get_snapshot,
        start_compute_job=_start_compute,
    )


# ---------------------------------------------------------------------------
# Registration + schema
# ---------------------------------------------------------------------------


def test_six_new_tools_registered(tmp_path) -> None:
    tools = _make_tools(tmp_path)
    names = set(tools.tool_names())
    missing = TIER_TOOLS - names
    assert not missing, "Missing tools: {0}".format(missing)


def test_stt_word_level_start_requires_speaker_and_source(tmp_path) -> None:
    tools = _make_tools(tmp_path)
    with pytest.raises(ChatToolValidationError):
        tools.execute("stt_word_level_start", {})
    with pytest.raises(ChatToolValidationError):
        tools.execute("stt_word_level_start", {"speaker": "Fail02"})


def test_forced_align_start_requires_speaker(tmp_path) -> None:
    tools = _make_tools(tmp_path)
    with pytest.raises(ChatToolValidationError):
        tools.execute("forced_align_start", {})


def test_ipa_transcribe_acoustic_start_requires_speaker(tmp_path) -> None:
    tools = _make_tools(tmp_path)
    with pytest.raises(ChatToolValidationError):
        tools.execute("ipa_transcribe_acoustic_start", {})


# ---------------------------------------------------------------------------
# Dry-run short-circuits
# ---------------------------------------------------------------------------


def test_stt_word_level_start_dry_run_skips_callback(tmp_path) -> None:
    calls: List[Tuple[str, str, Optional[str]]] = []
    tools = _make_tools(tmp_path, start_stt_calls=calls)
    out = tools.execute(
        "stt_word_level_start",
        {"speaker": "Fail02", "sourceWav": "clip.wav", "dryRun": True},
    )
    assert out["ok"] is True
    assert out["result"]["status"] == "dry_run"
    assert calls == []


def test_forced_align_start_dry_run_skips_callback(tmp_path) -> None:
    calls: List[Tuple[str, Dict[str, Any]]] = []
    tools = _make_tools(tmp_path, start_compute_calls=calls)
    out = tools.execute(
        "forced_align_start",
        {"speaker": "Fail02", "dryRun": True},
    )
    assert out["result"]["status"] == "dry_run"
    assert out["result"]["plan"]["speaker"] == "Fail02"
    assert out["result"]["plan"]["language"] == "ku"
    assert calls == []


def test_ipa_transcribe_acoustic_start_dry_run_skips_callback(tmp_path) -> None:
    calls: List[Tuple[str, Dict[str, Any]]] = []
    tools = _make_tools(tmp_path, start_compute_calls=calls)
    out = tools.execute(
        "ipa_transcribe_acoustic_start",
        {"speaker": "Fail02", "overwrite": True, "dryRun": True},
    )
    assert out["result"]["status"] == "dry_run"
    assert out["result"]["plan"]["overwrite"] is True
    assert calls == []


# ---------------------------------------------------------------------------
# Live start paths dispatch to the correct callback
# ---------------------------------------------------------------------------


def test_stt_word_level_start_live_invokes_stt_callback(tmp_path) -> None:
    stt_calls: List[Tuple[str, str, Optional[str]]] = []
    tools = _make_tools(tmp_path, start_stt_calls=stt_calls)
    out = tools.execute(
        "stt_word_level_start",
        {"speaker": "Fail02", "sourceWav": "audio/clip.wav", "language": "sdh"},
    )
    assert out["result"]["jobId"] == "job-stt-1"
    assert out["result"]["tier"] == "tier1_word_level"
    # Single invocation, right speaker/language. The path is normalised by
    # ParseChatTools before being handed to the callback.
    assert len(stt_calls) == 1
    assert stt_calls[0][0] == "Fail02"
    assert stt_calls[0][2] == "sdh"


def test_forced_align_start_live_dispatches_forced_align_compute(tmp_path) -> None:
    compute_calls: List[Tuple[str, Dict[str, Any]]] = []
    tools = _make_tools(tmp_path, start_compute_calls=compute_calls)
    out = tools.execute(
        "forced_align_start",
        {"speaker": "Fail02", "padMs": 150, "emitPhonemes": False},
    )
    assert out["result"]["jobId"] == "job-compute-forced_align"
    assert out["result"]["tier"] == "tier2_forced_align"
    assert compute_calls == [
        (
            "forced_align",
            {
                "speaker": "Fail02",
                "language": "ku",
                "padMs": 150,
                "emitPhonemes": False,
            },
        )
    ]


def test_ipa_transcribe_acoustic_start_live_dispatches_ipa_only(tmp_path) -> None:
    compute_calls: List[Tuple[str, Dict[str, Any]]] = []
    tools = _make_tools(tmp_path, start_compute_calls=compute_calls)
    out = tools.execute(
        "ipa_transcribe_acoustic_start",
        {"speaker": "Fail02", "overwrite": True},
    )
    assert out["result"]["jobId"] == "job-compute-ipa_only"
    assert out["result"]["tier"] == "tier3_acoustic_ipa"
    assert compute_calls == [
        ("ipa_only", {"speaker": "Fail02", "overwrite": True})
    ]


# ---------------------------------------------------------------------------
# Status handlers
# ---------------------------------------------------------------------------


def test_forced_align_status_rejects_wrong_job_type(tmp_path) -> None:
    tools = _make_tools(
        tmp_path,
        snapshots={
            "job-x": {"type": "stt", "status": "running"},
        },
    )
    out = tools.execute("forced_align_status", {"jobId": "job-x"})
    assert out["result"]["status"] == "invalid_job_type"
    assert out["result"]["expected"] == "forced_align"


def test_forced_align_status_passes_snapshot_fields(tmp_path) -> None:
    tools = _make_tools(
        tmp_path,
        snapshots={
            "job-a": {
                "type": "forced_align",
                "status": "complete",
                "progress": 100.0,
                "result": {"filled": 42, "methodCounts": {"wav2vec2": 41, "proportional-fallback": 1}},
            }
        },
    )
    out = tools.execute("forced_align_status", {"jobId": "job-a"})
    assert out["result"]["status"] == "complete"
    assert out["result"]["result"]["filled"] == 42
    assert out["result"]["tier"] == "tier2_forced_align"


def test_ipa_transcribe_acoustic_status_accepts_ipa_only_type(tmp_path) -> None:
    tools = _make_tools(
        tmp_path,
        snapshots={
            "job-ipa": {
                "type": "ipa_only",
                "status": "complete",
                "progress": 100.0,
                "result": {"filled": 10, "skipped": 2, "total": 12},
            }
        },
    )
    out = tools.execute("ipa_transcribe_acoustic_status", {"jobId": "job-ipa"})
    assert out["result"]["status"] == "complete"
    assert out["result"]["tier"] == "tier3_acoustic_ipa"


def test_status_unknown_job_returns_not_found(tmp_path) -> None:
    tools = _make_tools(tmp_path)
    out = tools.execute("forced_align_status", {"jobId": "ghost"})
    assert out["result"]["status"] == "not_found"


# ---------------------------------------------------------------------------
# Failure when callback absent
# ---------------------------------------------------------------------------


def test_forced_align_start_without_compute_callback_raises(tmp_path) -> None:
    # Build ParseChatTools without start_compute_job callback.
    (tmp_path / "audio").mkdir(exist_ok=True)
    tools = ParseChatTools(project_root=tmp_path)
    with pytest.raises(ChatToolExecutionError):
        tools.execute("forced_align_start", {"speaker": "Fail02"})
