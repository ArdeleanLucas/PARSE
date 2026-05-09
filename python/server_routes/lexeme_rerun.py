"""PARSE server route-domain module: synchronous lexeme reruns."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import server as _server
from ai.wav2vec2_runtime import resolve_wav2vec2_runtime_options
from app.http.lexeme_rerun_handlers import (
    LexemeRerunHandlerError,
    LexemeRerunSubprocessError,
    build_post_run_ipa_response,
    build_post_run_ortho_response,
)
from server_routes.locks import _locks_dir


_DEFAULT_LEXEME_RERUN_SUBPROCESS_TIMEOUT_SEC = 120.0


def _wav2vec2_options_with_safe_fallback() -> tuple[Optional[str], bool]:
    try:
        options = resolve_wav2vec2_runtime_options()
        return options.device, options.allow_wsl_cuda
    except Exception:
        # Preserve the pre-config-plumbing behavior if even the resolver is
        # monkeypatched/broken: forced_align owns auto device resolution and WSL
        # CUDA remains disabled unless config was read successfully.
        return None, False


def _run_ortho_interval(*, audio_path: Path, start: float, end: float, language: Optional[str] = None) -> str:
    from ai.stt_pipeline import run_ortho_on_interval

    device, allow_wsl_cuda = _wav2vec2_options_with_safe_fallback()
    return run_ortho_on_interval(
        audio_path=audio_path,
        start=start,
        end=end,
        language=language,
        config_path=_server._config_path(),
        device=device,
        allow_wsl_cuda=allow_wsl_cuda,
    )


def _run_ipa_interval(*, audio_path: Path, start: float, end: float, language: Optional[str] = None) -> str:
    _ = language
    from ai.ipa_transcribe import transcribe_intervals

    device, allow_wsl_cuda = _wav2vec2_options_with_safe_fallback()
    results = transcribe_intervals(
        audio_path=audio_path,
        intervals=[{"start": start, "end": end}],
        device=device,
        allow_wsl_cuda=allow_wsl_cuda,
    )
    if not results:
        return ""
    first = results[0]
    if first.get("error") == "interval_too_short":
        raise ValueError(
            "interval_too_short: duration_ms={0} minimum_ms=80.0".format(first.get("duration_ms"))
        )
    return str(first.get("ipa") or "").strip()


def _lexeme_rerun_subprocess_timeout_sec() -> float:
    raw = _server.os.environ.get("PARSE_LEXEME_RERUN_SUBPROCESS_TIMEOUT_SEC", str(int(_DEFAULT_LEXEME_RERUN_SUBPROCESS_TIMEOUT_SEC)))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_LEXEME_RERUN_SUBPROCESS_TIMEOUT_SEC
    return value if value > 0.0 else _DEFAULT_LEXEME_RERUN_SUBPROCESS_TIMEOUT_SEC


def _lexeme_subprocess_code(exit_code: int | None) -> str:
    if exit_code in (-9, 137):
        return "subprocess_oom"
    if exit_code in (-11, 139):
        return "subprocess_segfault"
    return "subprocess_failed"


def _lexeme_subprocess_message(tier_label: str, code: str, exit_code: int | None) -> str:
    if code == "subprocess_oom":
        return "lexeme {0} subprocess was killed (likely OOM)".format(tier_label)
    if code == "subprocess_segfault":
        return "lexeme {0} subprocess exited with code {1} (segmentation fault)".format(tier_label, exit_code)
    return "lexeme {0} subprocess exited with code {1}".format(tier_label, exit_code)


def _lexeme_rerun_subprocess_entry(kind: str, payload: dict[str, Any], result_path: str) -> None:
    import json as _json
    import traceback as _traceback

    outcome: dict[str, Any]
    try:
        audio_path = Path(str(payload["audio_path"]))
        start = float(payload["start"])
        end = float(payload["end"])
        language_raw = payload.get("language")
        language = str(language_raw) if language_raw is not None else None
        if kind == "ipa":
            result = _run_ipa_interval(audio_path=audio_path, start=start, end=end, language=language)
        elif kind == "ortho":
            result = _run_ortho_interval(audio_path=audio_path, start=start, end=end, language=language)
        else:
            raise ValueError("unknown lexeme rerun kind: {0}".format(kind))
        # Contract: synchronous lexeme children serialize exactly one JSON string
        # result so the parent can map process crashes without sharing model state.
        outcome = {"ok": True, "result": str(result or "")}
    except BaseException as exc:  # noqa: BLE001 - child must serialize recoverable failures for the parent.
        outcome = {"ok": False, "error": str(exc), "traceback": _traceback.format_exc()}
    try:
        with open(result_path, "w", encoding="utf-8") as handle:
            _json.dump(outcome, handle)
    except Exception:
        pass


def _run_interval_in_subprocess(
    *,
    kind: str,
    tier_label: str,
    audio_path: Path,
    start: float,
    end: float,
    language: Optional[str] = None,
) -> str:
    import json as _json
    import multiprocessing
    import tempfile

    fd, result_path = tempfile.mkstemp(prefix="parse-lexeme-rerun-{0}-".format(kind), suffix=".json")
    _server.os.close(fd)
    try:
        _server.os.remove(result_path)
    except OSError:
        pass

    payload = {"audio_path": str(Path(audio_path)), "start": float(start), "end": float(end), "language": language}
    ctx = multiprocessing.get_context("spawn")
    child = ctx.Process(
        target=_lexeme_rerun_subprocess_entry,
        name="parse-lexeme-rerun-{0}".format(kind),
        args=(kind, payload, result_path),
        daemon=True,
    )
    child.start()
    timeout_sec = _lexeme_rerun_subprocess_timeout_sec()
    child.join(timeout=timeout_sec)
    if child.is_alive():
        try:
            child.terminate()
            child.join(timeout=10.0)
        except Exception:
            pass
        raise LexemeRerunSubprocessError(
            code="subprocess_timeout",
            exit_code=child.exitcode,
            message="lexeme {0} subprocess exceeded PARSE_LEXEME_RERUN_SUBPROCESS_TIMEOUT_SEC ({1}s) and was terminated".format(
                tier_label,
                int(timeout_sec) if timeout_sec.is_integer() else timeout_sec,
            ),
        )

    exit_code = child.exitcode
    if exit_code not in (0, None):
        try:
            if _server.os.path.exists(result_path):
                _server.os.remove(result_path)
        except OSError:
            pass
        code = _lexeme_subprocess_code(exit_code)
        raise LexemeRerunSubprocessError(code=code, exit_code=exit_code, message=_lexeme_subprocess_message(tier_label, code, exit_code))

    if not _server.os.path.exists(result_path):
        raise LexemeRerunSubprocessError(
            code="subprocess_failed",
            exit_code=exit_code,
            message="lexeme {0} subprocess result file was not written".format(tier_label),
        )
    try:
        with open(result_path, "r", encoding="utf-8") as handle:
            outcome = _json.load(handle)
    except Exception as exc:
        raise LexemeRerunSubprocessError(
            code="subprocess_failed",
            exit_code=exit_code,
            message="lexeme {0} subprocess result file unreadable: {1}".format(tier_label, exc),
        ) from exc
    finally:
        try:
            _server.os.remove(result_path)
        except OSError:
            pass

    if bool(outcome.get("ok")):
        return str(outcome.get("result") or "").strip()
    raise LexemeRerunSubprocessError(
        code="subprocess_failed",
        exit_code=exit_code,
        message=str(outcome.get("error") or "lexeme {0} subprocess reported failure".format(tier_label)),
    )


def _run_ipa_interval_in_subprocess(*, audio_path: Path, start: float, end: float, language: Optional[str] = None) -> str:
    return _run_interval_in_subprocess(kind="ipa", tier_label="IPA", audio_path=audio_path, start=start, end=end, language=language)


def _run_ortho_interval_in_subprocess(*, audio_path: Path, start: float, end: float, language: Optional[str] = None) -> str:
    return _run_interval_in_subprocess(kind="ortho", tier_label="ORTH", audio_path=audio_path, start=start, end=end, language=language)


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
            run_ortho_interval=_run_ortho_interval_in_subprocess,
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
            run_ipa_interval=_run_ipa_interval_in_subprocess,
            locks_dir=_locks_dir(),
        )
    except LexemeRerunHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


__all__ = [
    "_api_post_lexeme_run_ortho",
    "_api_post_lexeme_run_ipa",
    "_lexeme_rerun_subprocess_entry",
    "_run_interval_in_subprocess",
    "_run_ortho_interval",
    "_run_ortho_interval_in_subprocess",
    "_run_ipa_interval",
    "_run_ipa_interval_in_subprocess",
]
