"""PARSE server route-domain module: synchronous lexeme reruns."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import server as _server
from app.http.lexeme_rerun_handlers import LexemeRerunHandlerError, build_post_run_ipa_response, build_post_run_ortho_response
from server_routes.locks import _locks_dir


def _run_ortho_interval(*, audio_path: Path, start: float, end: float, language: Optional[str] = None) -> str:
    from ai.stt_pipeline import run_stt_on_interval

    return run_stt_on_interval(
        audio_path=audio_path,
        start=start,
        end=end,
        language=language,
        config_path=_server._config_path(),
    )


def _run_ipa_interval(*, audio_path: Path, start: float, end: float, language: Optional[str] = None) -> str:
    _ = language
    from ai.ipa_transcribe import transcribe_intervals

    results = transcribe_intervals(audio_path=audio_path, intervals=[{"start": start, "end": end}])
    if not results:
        return ""
    return str(results[0].get("ipa") or "").strip()


def _api_post_lexeme_run_ortho(self) -> None:
    try:
        body = self._expect_object(self._read_json_body(), "body")
        response = build_post_run_ortho_response(
            body,
            project_root=_server._project_root(),
            normalize_speaker_id=_server._normalize_speaker_id,
            annotation_read_path_for_speaker=_server._annotation_read_path_for_speaker,
            read_json_any_file=_server._read_json_any_file,
            normalize_annotation_record=_server._normalize_annotation_record,
            resolve_audio_path_for_speaker=_server._pipeline_audio_path_for_speaker,
            run_ortho_interval=_run_ortho_interval,
            locks_dir=_locks_dir(),
        )
    except LexemeRerunHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


def _api_post_lexeme_run_ipa(self) -> None:
    try:
        body = self._expect_object(self._read_json_body(), "body")
        response = build_post_run_ipa_response(
            body,
            project_root=_server._project_root(),
            normalize_speaker_id=_server._normalize_speaker_id,
            annotation_read_path_for_speaker=_server._annotation_read_path_for_speaker,
            read_json_any_file=_server._read_json_any_file,
            normalize_annotation_record=_server._normalize_annotation_record,
            resolve_audio_path_for_speaker=_server._pipeline_audio_path_for_speaker,
            run_ipa_interval=_run_ipa_interval,
            locks_dir=_locks_dir(),
        )
    except LexemeRerunHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


__all__ = ["_api_post_lexeme_run_ortho", "_api_post_lexeme_run_ipa", "_run_ortho_interval", "_run_ipa_interval"]
