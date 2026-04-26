from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools.acoustic_starter_tools import (
    tool_audio_normalize_start,
    tool_stt_start,
    tool_stt_word_level_start,
)


def _make_tools(
    tmp_path: pathlib.Path,
    *,
    start_stt_calls: Optional[List[Tuple[str, str, Optional[str]]]] = None,
    start_normalize_calls: Optional[List[Tuple[str, Optional[str]]]] = None,
) -> ParseChatTools:
    def _start_stt(speaker: str, source_wav: str, language: Optional[str]) -> str:
        if start_stt_calls is not None:
            start_stt_calls.append((speaker, source_wav, language))
        return "job-stt-direct"

    def _start_normalize(speaker: str, source_wav: Optional[str]) -> str:
        if start_normalize_calls is not None:
            start_normalize_calls.append((speaker, source_wav))
        return "job-normalize-direct"

    resolved_root = tmp_path.resolve()
    (resolved_root / "audio").mkdir(exist_ok=True)
    (resolved_root / "audio" / "clip.wav").write_bytes(b"RIFFWAVE")

    return ParseChatTools(
        project_root=resolved_root,
        start_stt_job=_start_stt,
        start_normalize_job=_start_normalize,
    )


def test_tool_stt_start_runs_direct_bundle_handler(tmp_path) -> None:
    stt_calls: List[Tuple[str, str, Optional[str]]] = []
    tools = _make_tools(tmp_path, start_stt_calls=stt_calls)

    payload = tool_stt_start(
        tools,
        {"speaker": "Fail02", "sourceWav": "audio/clip.wav", "language": "sdh"},
    )

    assert payload["jobId"] == "job-stt-direct"
    assert payload["status"] == "running"
    assert payload["sourceWav"] == "audio/clip.wav"
    assert stt_calls == [("Fail02", "audio/clip.wav", "sdh")]


def test_tool_stt_word_level_start_reuses_shared_stt_logic(tmp_path) -> None:
    stt_calls: List[Tuple[str, str, Optional[str]]] = []
    tools = _make_tools(tmp_path, start_stt_calls=stt_calls)

    payload = tool_stt_word_level_start(
        tools,
        {"speaker": "Fail02", "sourceWav": "audio/clip.wav", "language": "sdh"},
    )

    assert payload["jobId"] == "job-stt-direct"
    assert payload["tier"] == "tier1_word_level"
    assert payload["message"] == "Word-level STT job started. Poll with stt_word_level_status."
    assert stt_calls == [("Fail02", "audio/clip.wav", "sdh")]


def test_tool_audio_normalize_start_runs_direct_bundle_handler(tmp_path) -> None:
    normalize_calls: List[Tuple[str, Optional[str]]] = []
    tools = _make_tools(tmp_path, start_normalize_calls=normalize_calls)

    payload = tool_audio_normalize_start(
        tools,
        {"speaker": "Fail02", "sourceWav": "audio/clip.wav"},
    )

    assert payload["jobId"] == "job-normalize-direct"
    assert payload["status"] == "running"
    assert payload["speaker"] == "Fail02"
    assert normalize_calls == [("Fail02", "audio/clip.wav")]
