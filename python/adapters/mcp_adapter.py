#!/usr/bin/env python3
"""PARSE MCP Server — expose ParseChatTools as MCP tools for third-party agents.

Starts a stdio MCP server that lets any MCP client (Claude Code, Cursor, Codex,
Windsurf, etc.) call PARSE's linguistic analysis tools programmatically.

Tools exposed:
  Read-only inspection:
    project_context_read, annotation_read, speakers_list,
    pipeline_state_read, pipeline_state_batch,
    read_csv_preview, read_text_preview, read_audio_info,
    cognate_compute_preview, cross_speaker_match_preview,
    spectrogram_preview, parse_memory_read
  Job control:
    stt_start, stt_status, pipeline_run, compute_status,
    stt_word_level_start, stt_word_level_status,
    forced_align_start, forced_align_status,
    ipa_transcribe_acoustic_start, ipa_transcribe_acoustic_status
  Offset alignment:
    detect_timestamp_offset, detect_timestamp_offset_from_pair,
    apply_timestamp_offset
  Write-allowed:
    contact_lexeme_lookup, import_tag_csv, prepare_tag_import,
    onboard_speaker_import, import_processed_speaker,
    parse_memory_upsert_section,
    audio_normalize_start, enrichments_write, lexeme_notes_write,
    export_annotations_csv, export_lingpy_tsv, export_nexus
  New read tools:
    audio_normalize_status, enrichments_read, lexeme_notes_read,
    jobs_list_active, source_index_validate

Usage:
    python python/adapters/mcp_adapter.py
    python python/adapters/mcp_adapter.py --project-root /path/to/project
    python python/adapters/mcp_adapter.py --verbose

MCP client config (e.g. claude_desktop_config.json):
    {
        "mcpServers": {
            "parse": {
                "command": "python",
                "args": ["python/adapters/mcp_adapter.py"],
                "env": {
                    "PARSE_PROJECT_ROOT": "/path/to/your/parse/project",
                    "PARSE_EXTERNAL_READ_ROOTS": "/mnt/c/Users/Lucas/Thesis",
                    "PARSE_CHAT_MEMORY_PATH": "/path/to/parse-memory.md"
                }
            }
        }
    }
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("parse.mcp_adapter")

MCP_CONFIG_FILENAME = "mcp_config.json"
DEFAULT_MCP_TOOL_NAMES = (
    "project_context_read",
    "annotation_read",
    "read_csv_preview",
    "cognate_compute_preview",
    "cross_speaker_match_preview",
    "spectrogram_preview",
    "contact_lexeme_lookup",
    "stt_start",
    "stt_status",
    "stt_word_level_start",
    "stt_word_level_status",
    "forced_align_start",
    "forced_align_status",
    "ipa_transcribe_acoustic_start",
    "ipa_transcribe_acoustic_status",
    "detect_timestamp_offset",
    "detect_timestamp_offset_from_pair",
    "apply_timestamp_offset",
    "import_tag_csv",
    "prepare_tag_import",
    "onboard_speaker_import",
    "import_processed_speaker",
    "parse_memory_read",
    "parse_memory_upsert_section",
    "speakers_list",
    "pipeline_state_read",
    "pipeline_state_batch",
    "pipeline_run",
    "compute_status",
)

# ---------------------------------------------------------------------------
# Ensure the python/ package is importable
# ---------------------------------------------------------------------------

_ADAPTER_DIR = Path(__file__).resolve().parent
_PYTHON_DIR = _ADAPTER_DIR.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

# ---------------------------------------------------------------------------
# Lazy MCP SDK import
# ---------------------------------------------------------------------------

_MCP_AVAILABLE = False
try:
    from mcp.server.fastmcp import FastMCP
    _MCP_AVAILABLE = True
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Server creation
# ---------------------------------------------------------------------------

def _resolve_project_root(cli_root: Optional[str] = None) -> Path:
    """Resolve PARSE project root from CLI arg, env var, or cwd."""
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    env_root = os.environ.get("PARSE_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    # Fallback: assume the repo root is 2 levels up from this file
    candidate = _ADAPTER_DIR.parent.parent
    if (candidate / "python" / "ai" / "chat_tools.py").exists():
        return candidate
    return Path.cwd()


def _resolve_mcp_config_path(project_root_path: Path) -> Optional[Path]:
    """Return the preferred mcp_config.json path if one exists.

    Preferred location is config/mcp_config.json for consistency with the
    other PARSE config files. For backward compatibility, also accept a
    project-root mcp_config.json fallback.
    """
    candidates = [
        project_root_path / "config" / MCP_CONFIG_FILENAME,
        project_root_path / MCP_CONFIG_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _load_mcp_config(project_root_path: Path) -> Dict[str, Any]:
    """Load MCP adapter config, defaulting to the legacy 29-tool surface."""
    config_path = _resolve_mcp_config_path(project_root_path)
    if config_path is None:
        return {"expose_all_tools": False}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read %s: %s. Falling back to expose_all_tools=false.", config_path, exc)
        return {"expose_all_tools": False}
    if not isinstance(payload, dict):
        logger.warning("Ignoring non-object MCP config at %s. Falling back to expose_all_tools=false.", config_path)
        return {"expose_all_tools": False}
    expose_all_tools_raw = payload.get("expose_all_tools", False)
    if not isinstance(expose_all_tools_raw, bool):
        logger.warning(
            "Ignoring non-boolean expose_all_tools=%r at %s. Falling back to expose_all_tools=false.",
            expose_all_tools_raw,
            config_path,
        )
        expose_all_tools_raw = False
    return {"expose_all_tools": expose_all_tools_raw, "config_path": str(config_path)}


def _selected_mcp_tool_names(all_tool_names: List[str], expose_all_tools: bool) -> List[str]:
    """Return the MCP tool surface for this server instance."""
    if expose_all_tools:
        return list(all_tool_names)
    available_names = set(all_tool_names)
    return [name for name in DEFAULT_MCP_TOOL_NAMES if name in available_names]


def _load_repo_parse_env(project_root_path: Path) -> Dict[str, str]:
    """Load machine-local overrides from <project>/.parse-env into os.environ.

    The dev launcher (scripts/parse-run.sh) already sources this file before
    booting the browser/server stack, but the standalone MCP adapter is often
    launched directly by an editor or agent process. In that mode, the process
    inherits no PARSE_* environment and silently falls back to the strict
    project-root sandbox, which breaks legitimate thesis imports from /mnt/c.

    This helper mirrors the launcher convention: read simple KEY=VALUE pairs
    from .parse-env and populate only variables that are currently unset.
    Existing environment variables always win.
    """
    parse_env_path = project_root_path / ".parse-env"
    if not parse_env_path.exists() or not parse_env_path.is_file():
        return {}

    applied: Dict[str, str] = {}
    for raw_line in parse_env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
            cleaned = cleaned[1:-1]
        os.environ[key] = cleaned
        applied[key] = cleaned

    return applied


def _resolve_api_base() -> str:
    """Resolve the HTTP base URL of the running PARSE API server.

    The MCP adapter proxies STT calls through the HTTP server instead of
    running a parallel job manager — this keeps job state consistent with
    the browser UI and avoids forking the in-memory job store.
    """
    port = os.environ.get("PARSE_API_PORT") or os.environ.get("PARSE_PORT") or "8766"
    return "http://127.0.0.1:{0}".format(str(port).strip() or "8766")


def _resolve_onboard_http_timeout(total_bytes: int) -> float:
    """Return a socket timeout for MCP onboarding HTTP calls.

    Thesis WAV uploads are often multi-gigabyte files. The original fixed
    120-second timeout is too short even on localhost once the adapter spends
    time reading the file, constructing multipart payloads, and waiting for the
    server to persist the upload. Scale the timeout with payload size while
    keeping a sane floor/cap, and allow an explicit environment override for
    machine-specific tuning.
    """
    override_raw = str(os.environ.get("PARSE_MCP_ONBOARD_TIMEOUT_SEC") or "").strip()
    if override_raw:
        try:
            override = float(override_raw)
        except ValueError:
            override = 0.0
        if override > 0:
            return override

    base_timeout = 120.0
    max_timeout = 1800.0
    payload_bytes = max(0, int(total_bytes))
    if payload_bytes <= 128 * 1024 * 1024:
        return base_timeout

    processing_buffer = 180.0
    transfer_budget = payload_bytes / float(8 * 1024 * 1024)
    return min(max_timeout, max(base_timeout, processing_buffer + transfer_budget))


def _build_stt_callbacks() -> tuple:
    """Build ParseChatTools' start_stt_job / get_job_snapshot callbacks that
    proxy to the running HTTP server. Returns (start_fn, snapshot_fn).

    If the HTTP server is unreachable, the callbacks return clear errors that
    surface through the chat tool's normal validation path rather than letting
    urllib exceptions leak to the MCP client.
    """
    import json as _json
    import urllib.error
    import urllib.request

    base_url = _resolve_api_base()

    def _post_json(path: str, payload: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
        """POST JSON to the PARSE API and return the parsed body.

        For HTTP errors (404, 500, etc.) the server still sends a JSON body
        with an error message — read it and return that so the calling chat
        tool can surface the real reason (e.g. "Unknown jobId") instead of a
        generic "unreachable" message. Only network-level failures raise.
        """
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url="{0}{1}".format(base_url, path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                pass
            try:
                parsed_err = _json.loads(body) if body else {}
            except _json.JSONDecodeError:
                parsed_err = {"error": body[:400] or http_err.reason}
            if isinstance(parsed_err, dict):
                parsed_err.setdefault("status", "error")
                parsed_err.setdefault("httpStatus", http_err.code)
                return parsed_err
            return {"status": "error", "error": str(parsed_err), "httpStatus": http_err.code}
        parsed = _json.loads(body)
        return parsed if isinstance(parsed, dict) else {}

    def start_stt_job(speaker: str, source_wav: str, language: Optional[str]) -> str:
        try:
            response = _post_json(
                "/api/stt",
                {"speaker": speaker, "source_wav": source_wav, "language": language},
            )
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot start STT job. "
                "Ensure the Python server is running (scripts/parse-run.sh). "
                "Underlying error: {1}".format(base_url, exc)
            )
        job_id = str(
            response.get("job_id") or response.get("jobId") or ""
        ).strip()
        if not job_id:
            raise RuntimeError(
                "PARSE API returned no job_id for STT start: {0}".format(response)
            )
        return job_id

    def get_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
        # First try STT-style status so existing stt_status paths work
        # unchanged; if the server says "not an STT job", re-poll via the
        # generic compute status so callers get the full job snapshot
        # (result, progress, message) regardless of compute_type.
        try:
            response = _post_json("/api/stt/status", {"job_id": job_id})
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot poll job. "
                "Underlying error: {1}".format(base_url, exc)
            )
        status = str((response or {}).get("status") or "").lower()
        is_type_mismatch = (
            (response or {}).get("error") == "jobId is not an STT job"
            or status == "error"
            and "is not an stt job" in str((response or {}).get("error") or "").lower()
        )
        if is_type_mismatch:
            try:
                response = _post_json(
                    "/api/compute/status", {"job_id": job_id}
                )
            except urllib.error.URLError:
                # Swallow — return the original STT-typed error.
                pass
        return response or None

    return start_stt_job, get_job_snapshot


def _build_pipeline_callbacks() -> tuple:
    """Build ParseChatTools' pipeline_state and start_compute callbacks.

    Both proxy to the running PARSE HTTP server so chat/MCP callers see
    the same job state as the browser UI — same in-memory job registry,
    same pipeline sequencer, same annotations-on-disk.

    Returns ``(pipeline_state, start_compute)``.
    """
    import json as _json
    import urllib.error
    import urllib.request

    base_url = _resolve_api_base()

    def _get_json(path: str, timeout: float = 20.0) -> Dict[str, Any]:
        req = urllib.request.Request(
            url="{0}{1}".format(base_url, path),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                body = ""
            try:
                parsed = _json.loads(body) if body else {}
            except _json.JSONDecodeError:
                parsed = {"error": body[:400] or http_err.reason}
            if isinstance(parsed, dict):
                parsed.setdefault("httpStatus", http_err.code)
                return parsed
            return {"error": str(parsed), "httpStatus": http_err.code}
        parsed = _json.loads(body)
        return parsed if isinstance(parsed, dict) else {}

    def _post_json(path: str, payload: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url="{0}{1}".format(base_url, path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                body = ""
            try:
                parsed = _json.loads(body) if body else {}
            except _json.JSONDecodeError:
                parsed = {"error": body[:400] or http_err.reason}
            if isinstance(parsed, dict):
                parsed.setdefault("httpStatus", http_err.code)
                return parsed
            return {"error": str(parsed), "httpStatus": http_err.code}
        parsed = _json.loads(body)
        return parsed if isinstance(parsed, dict) else {}

    def pipeline_state(speaker: str) -> Dict[str, Any]:
        import urllib.parse
        safe = urllib.parse.quote(str(speaker or "").strip(), safe="")
        try:
            return _get_json("/api/pipeline/state/{0}".format(safe))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot probe pipeline state. "
                "Underlying error: {1}".format(base_url, exc)
            )

    def start_compute(compute_type: str, payload: Dict[str, Any]) -> str:
        import urllib.parse
        safe = urllib.parse.quote(str(compute_type or "").strip(), safe="")
        try:
            response = _post_json("/api/compute/{0}".format(safe), payload or {})
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot start compute job. "
                "Underlying error: {1}".format(base_url, exc)
            )
        job_id = str(response.get("job_id") or response.get("jobId") or "").strip()
        if not job_id:
            raise RuntimeError(
                "PARSE API returned no jobId for compute start: {0}".format(response)
            )
        return job_id

    return pipeline_state, start_compute


def _build_normalize_callback():
    """Build ParseChatTools' start_normalize_job callback that proxies to the HTTP server."""
    import json as _json
    import urllib.error
    import urllib.request

    base_url = _resolve_api_base()

    def start_normalize_job(speaker: str, source_wav: Optional[str]) -> str:
        payload: Dict[str, Any] = {"speaker": speaker}
        if source_wav:
            payload["sourceWav"] = source_wav
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url="{0}/api/normalize".format(base_url),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                body = ""
            raise RuntimeError(
                "PARSE API normalize start failed ({0}): {1}".format(http_err.code, body[:300])
            )
        except urllib.error.URLError as exc:
            raise RuntimeError("PARSE API unreachable at {0}: {1}".format(base_url, exc))
        parsed = _json.loads(body) if body else {}
        job_id = str(parsed.get("jobId") or parsed.get("job_id") or "").strip()
        if not job_id:
            raise RuntimeError(
                "PARSE API returned no jobId for normalize start: {0}".format(parsed)
            )
        return job_id

    return start_normalize_job


def _build_jobs_callback():
    """Build ParseChatTools' list_active_jobs callback that proxies to the HTTP server."""
    import json as _json
    import urllib.error
    import urllib.request

    base_url = _resolve_api_base()

    def list_active_jobs() -> List[Dict[str, Any]]:
        req = urllib.request.Request(
            url="{0}/api/jobs/active".format(base_url),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            raise RuntimeError(
                "PARSE API jobs/active failed ({0})".format(http_err.code)
            )
        except urllib.error.URLError as exc:
            raise RuntimeError("PARSE API unreachable at {0}: {1}".format(base_url, exc))
        parsed = _json.loads(body) if body else {}
        return list(parsed.get("jobs") or [])

    return list_active_jobs


def _resolve_external_read_roots() -> list:
    """Parse PARSE_EXTERNAL_READ_ROOTS from env into a list of Paths.

    Mirrors server._chat_external_read_roots so MCP clients and the in-process
    chat runtime share the same sandbox roots.
    """
    raw = str(os.environ.get("PARSE_EXTERNAL_READ_ROOTS") or "").strip()
    if not raw:
        return []
    sep = ";" if os.name == "nt" or ";" in raw else os.pathsep
    roots: list = []
    for piece in raw.split(sep):
        piece = piece.strip()
        if not piece:
            continue
        if piece in {"*", "**", "/"}:
            roots.append(Path(piece))
            continue
        candidate = Path(piece).expanduser()
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _resolve_memory_path(project_root_path: Path) -> Path:
    raw = str(os.environ.get("PARSE_CHAT_MEMORY_PATH") or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = project_root_path / candidate
        try:
            return candidate.resolve()
        except Exception:
            return candidate
    return (project_root_path / "parse-memory.md").resolve()


def _build_onboard_callback() -> Optional[object]:
    """Return a callback that proxies onboard_speaker_import through the HTTP API.

    The MCP adapter runs out-of-process from the PARSE server, so we can't call
    the in-process job worker directly. Instead, POST the source files as
    multipart/form-data to /api/onboard/speaker and block on the resulting job
    until it completes. Returns None if the API is unreachable when invoked.
    """
    import email.generator
    import mimetypes
    import time
    import urllib.error
    import urllib.request
    import uuid

    base_url = _resolve_api_base()

    def onboard(speaker: str, source_wav: Path, source_csv: Optional[Path], is_primary: bool) -> Dict[str, Any]:
        boundary = "----parse-mcp-{0}".format(uuid.uuid4().hex)
        crlf = b"\r\n"
        parts: list = []
        total_bytes = source_wav.stat().st_size + (source_csv.stat().st_size if source_csv is not None else 0)
        http_timeout = _resolve_onboard_http_timeout(total_bytes)

        def add_field(name: str, value: str) -> None:
            parts.append(
                (
                    "--{0}\r\nContent-Disposition: form-data; name=\"{1}\"\r\n\r\n{2}\r\n"
                    .format(boundary, name, value)
                ).encode("utf-8")
            )

        def add_file(name: str, path: Path) -> None:
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            header = (
                "--{0}\r\nContent-Disposition: form-data; name=\"{1}\"; filename=\"{2}\"\r\n"
                "Content-Type: {3}\r\n\r\n".format(boundary, name, path.name, mime)
            ).encode("utf-8")
            parts.append(header)
            parts.append(path.read_bytes())
            parts.append(crlf)

        add_field("speaker_id", speaker)
        add_file("audio", source_wav)
        if source_csv is not None:
            add_file("csv", source_csv)
        parts.append("--{0}--\r\n".format(boundary).encode("utf-8"))

        body = b"".join(parts)
        req = urllib.request.Request(
            url="{0}/api/onboard/speaker".format(base_url),
            data=body,
            headers={"Content-Type": "multipart/form-data; boundary={0}".format(boundary)},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=http_timeout) as resp:
                response = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot onboard speaker. Underlying: {1}".format(
                    base_url, exc
                )
            )

        job_id = str(response.get("job_id") or response.get("jobId") or "").strip()
        if not job_id:
            raise RuntimeError("Onboard API did not return a job_id: {0}".format(response))

        # Poll for completion (bounded).
        status_req_body = json.dumps({"job_id": job_id}).encode("utf-8")
        deadline = time.time() + http_timeout
        final: Dict[str, Any] = {}
        while time.time() < deadline:
            status_req = urllib.request.Request(
                url="{0}/api/onboard/speaker/status".format(base_url),
                data=status_req_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(status_req, timeout=10.0) as sresp:
                    final = json.loads(sresp.read().decode("utf-8") or "{}")
            except urllib.error.URLError:
                time.sleep(1.0)
                continue
            status = str(final.get("status") or "").lower()
            if status in {"complete", "error"}:
                break
            time.sleep(1.0)

        if str(final.get("status") or "").lower() != "complete":
            raise RuntimeError(
                "Onboarding failed for speaker {0!r}: {1}".format(speaker, final.get("error") or final)
            )

        result = final.get("result") if isinstance(final.get("result"), dict) else {}
        return {
            "jobId": job_id,
            "annotationPath": result.get("annotationPath"),
            "wavPath": result.get("wavPath"),
            "csvPath": result.get("csvPath"),
            "isPrimary": is_primary,
        }

    return onboard


def create_mcp_server(project_root: Optional[str] = None) -> "FastMCP":
    """Create and return the PARSE MCP server with all tools registered.

    Wraps ParseChatTools so every tool available to the built-in AI chat
    is also available over MCP for third-party agents. STT and onboarding
    tools proxy through the running HTTP server on PARSE_API_PORT
    (default 8766) so job state is shared with the browser UI.
    """
    if not _MCP_AVAILABLE:
        raise ImportError(
            "MCP server requires the 'mcp' package. "
            "Install with: pip install 'mcp[cli]'"
        )

    from ai.chat_tools import ParseChatTools

    root = _resolve_project_root(project_root)
    applied_env = _load_repo_parse_env(root)
    external_roots = _resolve_external_read_roots()
    memory_path = _resolve_memory_path(root)
    logger.info("PARSE MCP server starting with project root: %s", root)
    if applied_env:
        logger.info(
            "Loaded .parse-env overrides: %s",
            ", ".join("{0}={1}".format(k, v) for k, v in sorted(applied_env.items())),
        )
    if external_roots:
        logger.info("External read roots: %s", ", ".join(str(r) for r in external_roots))
    logger.info("Chat memory path: %s", memory_path)

    start_stt, get_snapshot = _build_stt_callbacks()
    pipeline_state_cb, start_compute_cb = _build_pipeline_callbacks()
    onboard_callback = _build_onboard_callback()
    normalize_cb = _build_normalize_callback()
    jobs_cb = _build_jobs_callback()
    tools = ParseChatTools(
        project_root=root,
        start_stt_job=start_stt,
        get_job_snapshot=get_snapshot,
        external_read_roots=external_roots,
        memory_path=memory_path,
        onboard_speaker=onboard_callback,
        pipeline_state=pipeline_state_cb,
        start_compute_job=start_compute_cb,
        start_normalize_job=normalize_cb,
        list_active_jobs=jobs_cb,
    )
    mcp_config = _load_mcp_config(root)
    expose_all_tools = mcp_config.get("expose_all_tools", False)
    all_mcp_tool_names = ParseChatTools.get_all_tool_names()
    selected_mcp_tool_names = _selected_mcp_tool_names(all_mcp_tool_names, expose_all_tools)

    mcp = FastMCP(
        "parse",
        instructions=(
            "PARSE — Phonetic Analysis & Review Source Explorer. "
            "Linguistic fieldwork tools for annotation, cross-speaker comparison, "
            "cognate analysis, STT pipeline control, and contact-language lookup."
        ),
    )

    def _json_tool_result(tool_name: str, args: Dict[str, Any]) -> str:
        result = tools.execute(tool_name, args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    # -- Register each ParseChatTools tool as an MCP tool --------------------
    # The cross-check test in python/adapters/test_mcp_adapter.py enforces
    # that every @mcp.tool() below maps to a name in tools.tool_names(), so
    # phantom registrations fail in CI rather than at runtime.

    @mcp.tool()
    def project_context_read(
        include: Optional[list] = None,
        maxSpeakers: Optional[int] = None,
    ) -> str:
        """Read high-level PARSE project context (project metadata, source index summary,
        annotation inventory, and enrichment summary). Read-only.

        Args:
            include: Sections to include (project, source_index, annotation_inventory, enrichments_summary, ai_config, constraints)
            maxSpeakers: Maximum number of speakers to include in summaries
        """
        args: Dict[str, Any] = {}
        if include is not None:
            args["include"] = include
        if maxSpeakers is not None:
            args["maxSpeakers"] = maxSpeakers
        result = tools.execute("project_context_read", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def annotation_read(
        speaker: str,
        conceptIds: Optional[list] = None,
        includeTiers: Optional[list] = None,
        maxIntervals: Optional[int] = None,
    ) -> str:
        """Read one speaker's annotation data with optional concept/tier filtering. Read-only.

        Args:
            speaker: Speaker name (filename stem from annotations/)
            conceptIds: Filter to specific concept IDs
            includeTiers: Filter to specific tiers (ipa, ortho, concept, speaker)
            maxIntervals: Maximum number of intervals to return
        """
        args: Dict[str, Any] = {"speaker": speaker}
        if conceptIds is not None:
            args["conceptIds"] = conceptIds
        if includeTiers is not None:
            args["includeTiers"] = includeTiers
        if maxIntervals is not None:
            args["maxIntervals"] = maxIntervals
        result = tools.execute("annotation_read", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def read_csv_preview(
        csvPath: Optional[str] = None,
        maxRows: Optional[int] = None,
    ) -> str:
        """Read first N rows of a CSV file. Defaults to concepts.csv. Read-only.

        Args:
            csvPath: Path to CSV file (relative to project root, or absolute)
            maxRows: Maximum rows to return (default 20, max 200)
        """
        args: Dict[str, Any] = {}
        if csvPath is not None:
            args["csvPath"] = csvPath
        if maxRows is not None:
            args["maxRows"] = maxRows
        result = tools.execute("read_csv_preview", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def cognate_compute_preview(
        speakers: Optional[list] = None,
        conceptIds: Optional[list] = None,
        threshold: Optional[float] = None,
        contactLanguages: Optional[list] = None,
        includeSimilarity: Optional[bool] = None,
        maxConcepts: Optional[int] = None,
    ) -> str:
        """Compute a read-only cognate/similarity preview from annotations.
        Does not write parse-enrichments.json.

        Args:
            speakers: Filter to specific speakers
            conceptIds: Filter to specific concept IDs
            threshold: Similarity threshold (0.01–2.0)
            contactLanguages: ISO 639 codes for contact languages to compare against
            includeSimilarity: Include pairwise similarity scores
            maxConcepts: Maximum concepts to process
        """
        args: Dict[str, Any] = {}
        if speakers is not None:
            args["speakers"] = speakers
        if conceptIds is not None:
            args["conceptIds"] = conceptIds
        if threshold is not None:
            args["threshold"] = threshold
        if contactLanguages is not None:
            args["contactLanguages"] = contactLanguages
        if includeSimilarity is not None:
            args["includeSimilarity"] = includeSimilarity
        if maxConcepts is not None:
            args["maxConcepts"] = maxConcepts
        result = tools.execute("cognate_compute_preview", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def cross_speaker_match_preview(
        speaker: Optional[str] = None,
        sttJobId: Optional[str] = None,
        sttSegments: Optional[list] = None,
        topK: Optional[int] = None,
        minConfidence: Optional[float] = None,
        maxConcepts: Optional[int] = None,
    ) -> str:
        """Compute read-only cross-speaker match candidates from STT output
        and existing annotations.

        Args:
            speaker: Target speaker to find matches for
            sttJobId: ID of a completed STT job to use as input
            sttSegments: Inline STT segments (alternative to sttJobId)
            topK: Number of top candidates per concept (1–20)
            minConfidence: Minimum confidence threshold (0.0–1.0)
            maxConcepts: Maximum concepts to process
        """
        args: Dict[str, Any] = {}
        if speaker is not None:
            args["speaker"] = speaker
        if sttJobId is not None:
            args["sttJobId"] = sttJobId
        if sttSegments is not None:
            args["sttSegments"] = sttSegments
        if topK is not None:
            args["topK"] = topK
        if minConfidence is not None:
            args["minConfidence"] = minConfidence
        if maxConcepts is not None:
            args["maxConcepts"] = maxConcepts
        result = tools.execute("cross_speaker_match_preview", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def spectrogram_preview(
        sourceWav: str,
        startSec: float,
        endSec: float,
        windowSize: Optional[int] = None,
    ) -> str:
        """Generate spectrogram preview for a segment. Read-only.

        Args:
            sourceWav: Path to the source WAV file
            startSec: Start time in seconds
            endSec: End time in seconds
            windowSize: FFT window size (256, 512, 1024, 2048, or 4096)
        """
        args: Dict[str, Any] = {
            "sourceWav": sourceWav,
            "startSec": startSec,
            "endSec": endSec,
        }
        if windowSize is not None:
            args["windowSize"] = windowSize
        result = tools.execute("spectrogram_preview", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def contact_lexeme_lookup(
        dryRun: bool,
        languages: Optional[list] = None,
        conceptIds: Optional[list] = None,
        providers: Optional[list] = None,
        maxConcepts: Optional[int] = None,
        overwrite: Optional[bool] = None,
    ) -> str:
        """Fetch reference forms (IPA) for contact/comparison languages.

        Gated by dryRun — ALWAYS pass dryRun=true first to preview, then
        dryRun=false after the user confirms. Only the second call writes to
        sil_contact_languages.json.

        Args:
            dryRun: Required. If true, preview only (no filesystem writes).
                If false, fetch and merge into sil_contact_languages.json.
            languages: ISO 639 language codes (e.g. ["ar", "fa", "ckb"]).
                Defaults to all configured languages in sil_contact_languages.json.
            conceptIds: Concept labels matching the concept_en column in
                concepts.csv. Defaults to all concepts.
            providers: Provider priority order (csv_override, lingpy_wordlist,
                pycldf, pylexibank, asjp, cldf, wikidata, wiktionary, grokipedia,
                literature).
            maxConcepts: Cap on concepts processed this call (1–200). Useful for
                bounded previews.
            overwrite: When dryRun=false, re-fetch even if forms already exist.
                Ignored when dryRun=true.
        """
        args: Dict[str, Any] = {"dryRun": dryRun}
        if languages is not None:
            args["languages"] = languages
        if conceptIds is not None:
            args["conceptIds"] = conceptIds
        if providers is not None:
            args["providers"] = providers
        if maxConcepts is not None:
            args["maxConcepts"] = maxConcepts
        if overwrite is not None:
            args["overwrite"] = overwrite
        result = tools.execute("contact_lexeme_lookup", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def stt_start(
        speaker: str,
        sourceWav: str,
        language: Optional[str] = None,
    ) -> str:
        """Start a bounded STT background job for a project audio file.
        Returns a jobId for polling with stt_status.

        Args:
            speaker: Speaker name
            sourceWav: Path to source WAV file (relative to audio/)
            language: Language code hint for the STT model
        """
        args: Dict[str, Any] = {"speaker": speaker, "sourceWav": sourceWav}
        if language is not None:
            args["language"] = language
        result = tools.execute("stt_start", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def stt_status(
        jobId: str,
        includeSegments: Optional[bool] = None,
        maxSegments: Optional[int] = None,
    ) -> str:
        """Read status/progress of an existing STT job.

        Args:
            jobId: The job ID returned by stt_start
            includeSegments: Include transcribed segments in response
            maxSegments: Maximum segments to return (1–300)
        """
        args: Dict[str, Any] = {"jobId": jobId}
        if includeSegments is not None:
            args["includeSegments"] = includeSegments
        if maxSegments is not None:
            args["maxSegments"] = maxSegments
        result = tools.execute("stt_status", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Tier 1/2/3 acoustic alignment surface
    # ------------------------------------------------------------------

    @mcp.tool()
    def stt_word_level_start(
        speaker: str,
        sourceWav: str,
        language: Optional[str] = None,
        dryRun: Optional[bool] = None,
    ) -> str:
        """Start a Tier 1 word-level STT job. Segments include nested
        words[] spans (word, start, end, prob) from faster-whisper's
        word_timestamps=True.

        Args:
            speaker: Speaker name
            sourceWav: Path to source WAV file (relative to audio/)
            language: Language code hint for the STT model
            dryRun: Validate and describe the plan without launching the job
        """
        args: Dict[str, Any] = {"speaker": speaker, "sourceWav": sourceWav}
        if language is not None:
            args["language"] = language
        if dryRun is not None:
            args["dryRun"] = dryRun
        result = tools.execute("stt_word_level_start", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def stt_word_level_status(
        jobId: str,
        includeSegments: Optional[bool] = None,
        includeWords: Optional[bool] = None,
        maxSegments: Optional[int] = None,
    ) -> str:
        """Read status of a Tier 1 word-level STT job. includeWords
        defaults to true so the nested words[] payload is returned.
        """
        args: Dict[str, Any] = {"jobId": jobId}
        if includeSegments is not None:
            args["includeSegments"] = includeSegments
        if includeWords is not None:
            args["includeWords"] = includeWords
        if maxSegments is not None:
            args["maxSegments"] = maxSegments
        result = tools.execute("stt_word_level_status", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def forced_align_start(
        speaker: str,
        overwrite: Optional[bool] = None,
        language: Optional[str] = None,
        padMs: Optional[int] = None,
        emitPhonemes: Optional[bool] = None,
        dryRun: Optional[bool] = None,
    ) -> str:
        """Start a Tier 2 forced-alignment job for a speaker. Runs
        torchaudio.functional.forced_align against
        facebook/wav2vec2-xlsr-53-espeak-cv-ft on each Tier 1 word
        window, producing tight per-word (and optional per-phoneme)
        boundaries. G2P (phonemizer + espeak-ng) is used only to build
        CTC targets and is discarded — no G2P output is persisted.

        Args:
            speaker: Speaker name
            overwrite: When true, replaces an existing aligned artifact (default: false)
            language: espeak-ng language code for the internal G2P step (default: ku)
            padMs: Context pad around each word window in milliseconds (0-500, default 100)
            emitPhonemes: Include per-phoneme spans in the output (default true)
            dryRun: Validate and describe the plan without launching the job
        """
        args: Dict[str, Any] = {"speaker": speaker}
        if overwrite is not None:
            args["overwrite"] = overwrite
        if language is not None:
            args["language"] = language
        if padMs is not None:
            args["padMs"] = padMs
        if emitPhonemes is not None:
            args["emitPhonemes"] = emitPhonemes
        if dryRun is not None:
            args["dryRun"] = dryRun
        result = tools.execute("forced_align_start", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def forced_align_status(jobId: str) -> str:
        """Read status of a Tier 2 forced-alignment compute job.

        Args:
            jobId: The job ID returned by forced_align_start
        """
        result = tools.execute("forced_align_status", {"jobId": jobId})
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def ipa_transcribe_acoustic_start(
        speaker: str,
        overwrite: Optional[bool] = None,
        dryRun: Optional[bool] = None,
    ) -> str:
        """Start a Tier 3 acoustic IPA job. Runs
        facebook/wav2vec2-xlsr-53-espeak-cv-ft CTC on each ortho
        interval's audio window and writes the decoded phoneme string
        into the speaker's IPA tier. wav2vec2 is the ONLY IPA engine —
        there are no text-based fallbacks.

        Args:
            speaker: Speaker name
            overwrite: Replace existing non-empty IPA cells (default false)
            dryRun: Validate and describe the plan without launching the job
        """
        args: Dict[str, Any] = {"speaker": speaker}
        if overwrite is not None:
            args["overwrite"] = overwrite
        if dryRun is not None:
            args["dryRun"] = dryRun
        result = tools.execute("ipa_transcribe_acoustic_start", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def ipa_transcribe_acoustic_status(jobId: str) -> str:
        """Read status of a Tier 3 acoustic IPA compute job.

        Args:
            jobId: The job ID returned by ipa_transcribe_acoustic_start
        """
        result = tools.execute("ipa_transcribe_acoustic_status", {"jobId": jobId})
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def detect_timestamp_offset(
        speaker: str,
        sttJobId: Optional[str] = None,
        nAnchors: Optional[int] = None,
        bucketSec: Optional[float] = None,
        minMatchScore: Optional[float] = None,
        anchorDistribution: Optional[str] = None,
    ) -> str:
        """Detect a constant timestamp offset between a speaker's annotation
        intervals and STT segments for the same audio. Read-only.

        Uses monotonic anchor↔segment alignment (chosen matches must visit
        anchors and segments in increasing time order) so false matches to
        similar-sounding words elsewhere in the recording can't elect the
        wrong direction. Anchors are sampled across the timeline by quantile
        by default — pass ``anchorDistribution="earliest"`` for the legacy
        first-N selection.

        The return payload includes ``direction`` ("earlier" / "later"),
        ``directionLabel`` (plain-language sentence), ``spreadSec`` (median
        absolute deviation of the matched offsets), ``warnings`` (e.g. "low
        confidence"), and ``matches`` (the actual anchor↔segment pairs the
        algorithm chose). Sanity-check those before calling
        apply_timestamp_offset; if anything looks off, fall back to
        detect_timestamp_offset_from_pair with a manually known anchor.

        Args:
            speaker: Speaker ID whose annotation tiers provide the anchors
            sttJobId: Required. The jobId of a completed stt_start run for the
                same speaker — its segments are matched against annotation
                anchors to compute the offset. (For an STT-free path, use
                detect_timestamp_offset_from_pair instead.)
            nAnchors: Number of annotation intervals to sample (2–50, default 12)
            bucketSec: Bucket-vote granularity, used only as a fallback when
                monotonic alignment can't form a chain (default 1.0)
            minMatchScore: Minimum token similarity to accept a match (0.0–1.0, default 0.56)
            anchorDistribution: ``"quantile"`` (default — even sampling across
                the timeline) or ``"earliest"`` (first N intervals).
        """
        args: Dict[str, Any] = {"speaker": speaker}
        if sttJobId is not None:
            args["sttJobId"] = sttJobId
        if nAnchors is not None:
            args["nAnchors"] = nAnchors
        if bucketSec is not None:
            args["bucketSec"] = bucketSec
        if minMatchScore is not None:
            args["minMatchScore"] = minMatchScore
        if anchorDistribution is not None:
            args["anchorDistribution"] = anchorDistribution
        result = tools.execute("detect_timestamp_offset", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def detect_timestamp_offset_from_pair(
        speaker: str,
        audioTimeSec: Optional[float] = None,
        csvTimeSec: Optional[float] = None,
        conceptId: Optional[str] = None,
        pairs: Optional[list] = None,
    ) -> str:
        """Compute a timestamp offset from one or more trusted
        (csvTime, audioTime) pairs. No STT, no statistics-on-text, no
        false matches. Read-only.

        Use this when you (or the user) already know where one or more
        lexemes actually are in the audio — e.g. "STONE is at 02:34, WATER
        is at 04:12". With two or more pairs the response carries the MAD
        spread plus a warning if any pair disagrees with the consensus.

        Two argument shapes are accepted:

        * **Single pair** — pass ``audioTimeSec`` plus exactly one of
          ``csvTimeSec`` or ``conceptId``. Returns a single-pair offset.
        * **Multiple pairs** — pass ``pairs=[{...}, {...}]`` where each
          element is a pair object. The reported offsetSec is the median
          of per-pair offsets; spread is the median absolute deviation.

        Args:
            speaker: Speaker ID whose annotation will be shifted
            audioTimeSec: Single-pair convenience — the true audio time
                of the anchor lexeme. Mutually exclusive with ``pairs``.
            csvTimeSec: Single-pair convenience — the lexeme's current
                annotation time. Use either this or ``conceptId``.
            conceptId: Single-pair convenience — concept id to look up in
                the annotation; the matching interval's start becomes the
                csv time. Use either this or ``csvTimeSec``.
            pairs: Multi-pair list. Each item is
                ``{audioTimeSec, csvTimeSec? | conceptId?}``.
        """
        args: Dict[str, Any] = {"speaker": speaker}
        if audioTimeSec is not None:
            args["audioTimeSec"] = audioTimeSec
        if csvTimeSec is not None:
            args["csvTimeSec"] = csvTimeSec
        if conceptId is not None:
            args["conceptId"] = conceptId
        if pairs is not None:
            args["pairs"] = pairs
        result = tools.execute("detect_timestamp_offset_from_pair", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def apply_timestamp_offset(
        speaker: str,
        offsetSec: float,
        dryRun: bool,
    ) -> str:
        """Shift every annotation interval (start and end) by ``offsetSec`` for
        the given speaker. Mutates annotations/<speaker>.parse.json.

        Use dryRun=true first to preview the shift (returns a sample of
        before/after intervals), then dryRun=false to write the change.

        Args:
            speaker: Speaker ID whose annotation will be shifted
            offsetSec: Seconds to add to every interval start and end (negative
                values pull timestamps earlier; clamped at 0).
            dryRun: Required. If true, return preview only. If false, write.
        """
        args: Dict[str, Any] = {
            "speaker": speaker,
            "offsetSec": offsetSec,
            "dryRun": dryRun,
        }
        result = tools.execute("apply_timestamp_offset", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def import_tag_csv(
        dryRun: bool,
        csvPath: Optional[str] = None,
        tagName: Optional[str] = None,
        color: Optional[str] = None,
        labelColumn: Optional[str] = None,
    ) -> str:
        """Import a CSV file as a custom tag list. Use dryRun=true first to preview,
        then dryRun=false after user confirmation.

        Args:
            dryRun: If true, returns preview without writing. Always use true first.
            csvPath: Path to the CSV file
            tagName: Name for the new tag
            color: Hex color code (e.g. #FF0000)
            labelColumn: Column name containing concept labels
        """
        args: Dict[str, Any] = {"dryRun": dryRun}
        if csvPath is not None:
            args["csvPath"] = csvPath
        if tagName is not None:
            args["tagName"] = tagName
        if color is not None:
            args["color"] = color
        if labelColumn is not None:
            args["labelColumn"] = labelColumn
        result = tools.execute("import_tag_csv", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def prepare_tag_import(
        tagName: str,
        conceptIds: list,
        dryRun: bool,
        color: Optional[str] = None,
    ) -> str:
        """Create or update a tag with a list of concept IDs and write to parse-tags.json.
        Use dryRun=true first to preview, then dryRun=false after user confirmation.

        Args:
            tagName: Name for the tag
            conceptIds: List of concept IDs to assign to this tag
            dryRun: If true, returns preview without writing
            color: Hex color code (e.g. #FF0000)
        """
        args: Dict[str, Any] = {
            "tagName": tagName,
            "conceptIds": conceptIds,
            "dryRun": dryRun,
        }
        if color is not None:
            args["color"] = color
        result = tools.execute("prepare_tag_import", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def onboard_speaker_import(
        speaker: str,
        sourceWav: str,
        dryRun: bool,
        sourceCsv: Optional[str] = None,
        isPrimary: Optional[bool] = None,
    ) -> str:
        """Import a new speaker from on-disk audio (and optional transcription CSV).

        Copies the audio into audio/original/<speaker>/, scaffolds an annotation
        record, and registers the speaker in source_index.json. sourceWav/sourceCsv
        may be absolute paths under PARSE_EXTERNAL_READ_ROOTS or project-relative.
        Use dryRun=true first to preview, then dryRun=false to execute.

        Args:
            speaker: Speaker ID (filename-safe, no path separators)
            sourceWav: Path to the source audio file
            dryRun: If true, preview only. Run false to perform the import.
            sourceCsv: Optional path to a transcription CSV to store alongside
            isPrimary: Flag this WAV as the speaker's primary source
        """
        args: Dict[str, Any] = {
            "speaker": speaker,
            "sourceWav": sourceWav,
            "dryRun": dryRun,
        }
        if sourceCsv is not None:
            args["sourceCsv"] = sourceCsv
        if isPrimary is not None:
            args["isPrimary"] = isPrimary
        result = tools.execute("onboard_speaker_import", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def import_processed_speaker(
        speaker: str,
        workingWav: str,
        annotationJson: str,
        dryRun: bool,
        peaksJson: Optional[str] = None,
        transcriptCsv: Optional[str] = None,
    ) -> str:
        """Import a speaker from existing processed artifacts.

        Use when lexemes are already timestamped to a working WAV and the goal is
        to bootstrap the PARSE workspace from those processed files rather than
        re-running raw-audio onboarding or STT.

        Args:
            speaker: Speaker ID
            workingWav: Path to the processed/working WAV
            annotationJson: Path to the timestamp-bearing annotation JSON
            dryRun: If true, preview only
            peaksJson: Optional peaks JSON for the same working WAV
            transcriptCsv: Optional legacy transcript CSV to preserve in workspace
        """
        args: Dict[str, Any] = {
            "speaker": speaker,
            "workingWav": workingWav,
            "annotationJson": annotationJson,
            "dryRun": dryRun,
        }
        if peaksJson is not None:
            args["peaksJson"] = peaksJson
        if transcriptCsv is not None:
            args["transcriptCsv"] = transcriptCsv
        result = tools.execute("import_processed_speaker", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def parse_memory_read(
        section: Optional[str] = None,
        maxBytes: Optional[int] = None,
    ) -> str:
        """Read the persistent chat memory markdown (parse-memory.md).

        Records speaker provenance, file origins, user preferences, and session
        context. Read-only. Returns the full document bounded by maxBytes, or a
        specific `## Section` when section is provided.

        Args:
            section: Heading text (without leading `##`). If given, only that
                section is returned.
            maxBytes: Cap on bytes returned (min 512).
        """
        args: Dict[str, Any] = {}
        if section is not None:
            args["section"] = section
        if maxBytes is not None:
            args["maxBytes"] = maxBytes
        result = tools.execute("parse_memory_read", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def parse_memory_upsert_section(
        section: str,
        body: str,
        dryRun: bool,
    ) -> str:
        """Create or replace a `## Section` block in parse-memory.md.

        Use for persisting user preferences, speaker notes, onboarding decisions,
        and file provenance that should survive across chat turns. The existing
        block under the same heading is overwritten; other sections are untouched.
        Use dryRun=true first to preview, then dryRun=false to write.

        Args:
            section: Section heading (without leading `##`)
            body: Markdown body for the section
            dryRun: If true, returns preview without writing
        """
        args: Dict[str, Any] = {
            "section": section,
            "body": body,
            "dryRun": dryRun,
        }
        result = tools.execute("parse_memory_upsert_section", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ---- Pipeline + preflight tools (added for batch-pipeline workflow) ----

    @mcp.tool()
    def speakers_list() -> str:
        """List every annotated speaker in the project.

        Returns a sorted array of speaker ids, filtered to real annotation
        files (skips sibling dirs like ``backups/``). Starting point for
        batch pipeline runs — feed into ``pipeline_state_batch`` to see
        which speakers are ready to process, then into ``pipeline_run``
        to kick jobs off.
        """
        result = tools.execute("speakers_list", {})
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pipeline_state_read(speaker: str) -> str:
        """Preflight one speaker: done + can_run + FULL-FILE COVERAGE per step.

        Per-step fields: ``done, intervals|segments, can_run, reason,
        coverage_start_sec, coverage_end_sec, coverage_fraction,
        full_coverage``. Top-level also returns ``duration_sec``.

        CRITICAL: ``done`` is NOT the same as ``full_coverage``. A tier
        can have 128 intervals that only cover the first 30 seconds of
        a 6-minute WAV — ``done: true``, ``full_coverage: false``. If
        you're deciding whether a step needs to re-run, check
        ``full_coverage`` (bool). ``coverage_fraction`` (0.0–1.0) gives
        the precise ratio of last-interval-end to audio duration.

        Args:
            speaker: Speaker id (filename stem in annotations/)
        """
        result = tools.execute("pipeline_state_read", {"speaker": speaker})
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pipeline_state_batch(speakers: Optional[list] = None) -> str:
        """Preflight many speakers at once — the "can I walk away?" tool.

        Returns ``{count, blockedSpeakers, partialCoverageSpeakers, rows}``
        where each row carries the same per-step fields as
        ``pipeline_state_read`` (including ``full_coverage``). A speaker
        counts as ``blockedSpeakers`` if any step currently can_run=false;
        as ``partialCoverageSpeakers`` if any STT/ORTH/IPA step is
        ``done=true`` but ``full_coverage=false`` (work was started but
        doesn't span the whole WAV — typically because older runs were
        constrained to stale concept timestamps).

        Args:
            speakers: Optional subset. Omit to probe all speakers.
        """
        args: Dict[str, Any] = {}
        if speakers is not None:
            args["speakers"] = speakers
        result = tools.execute("pipeline_state_batch", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def pipeline_run(
        speaker: str,
        steps: list,
        overwrites: Optional[dict] = None,
        language: Optional[str] = None,
    ) -> str:
        """Start a transcription pipeline for ONE speaker. Returns jobId.

        Drives the same ``full_pipeline`` compute the UI uses. To run
        razhan (ORTH) on a speaker with overwrite enabled:

            steps=["ortho"], overwrites={"ortho": true}

        For the full chain in order:

            steps=["normalize", "stt", "ortho", "ipa"]

        Steps are step-resilient: a failing STT will not abort ORTH/IPA
        for the same speaker. Poll with ``compute_status`` until
        ``status=complete`` — the returned result carries per-step
        status (ok / skipped / error) + tracebacks for failures.

        Args:
            speaker: Speaker id to run against.
            steps: Subset of ["normalize", "stt", "ortho", "ipa"].
            overwrites: Per-step overwrite flags (default: all false).
            language: Optional language override for STT + ORTH.
        """
        args: Dict[str, Any] = {"speaker": speaker, "steps": steps}
        if overwrites is not None:
            args["overwrites"] = overwrites
        if language is not None:
            args["language"] = language
        result = tools.execute("pipeline_run", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def compute_status(jobId: str, computeType: Optional[str] = None) -> str:
        """Poll any compute job (full_pipeline, ortho, ipa, contact-lexemes).

        Returns the full server-side job snapshot including the ``result``
        payload for completed jobs. Pass ``computeType`` to assert the
        job's expected type (e.g. ``"full_pipeline"``) — the tool returns
        an ``invalid_job_type`` status if it doesn't match.

        Args:
            jobId: Job id returned by ``pipeline_run`` (or any compute start).
            computeType: Optional expected type (e.g. "full_pipeline").
        """
        args: Dict[str, Any] = {"jobId": jobId}
        if computeType is not None:
            args["computeType"] = computeType
        result = tools.execute("compute_status", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    if expose_all_tools:
        # These wrappers intentionally stay explicit, even in the "all tools"
        # mode, so the MCP surface remains readable/auditable in code rather
        # than being generated by reflection magic.
        def mcp_audio_normalize_start(speaker: str, sourceWav: Optional[str] = None) -> str:
            """Start speaker audio normalization. Returns a jobId for audio_normalize_status."""
            args: Dict[str, Any] = {"speaker": speaker}
            if sourceWav is not None:
                args["sourceWav"] = sourceWav
            return _json_tool_result("audio_normalize_start", args)
        mcp.tool(name="audio_normalize_start")(mcp_audio_normalize_start)

        def mcp_audio_normalize_status(jobId: str) -> str:
            """Poll a normalize job started with audio_normalize_start."""
            return _json_tool_result("audio_normalize_status", {"jobId": jobId})
        mcp.tool(name="audio_normalize_status")(mcp_audio_normalize_status)

        def mcp_enrichments_read(keys: Optional[list] = None) -> str:
            """Read parse-enrichments.json, optionally filtered to top-level keys."""
            args: Dict[str, Any] = {}
            if keys is not None:
                args["keys"] = keys
            return _json_tool_result("enrichments_read", args)
        mcp.tool(name="enrichments_read")(mcp_enrichments_read)

        def mcp_enrichments_write(enrichments: dict, merge: Optional[bool] = None) -> str:
            """Write or merge enrichments into parse-enrichments.json."""
            args: Dict[str, Any] = {"enrichments": enrichments}
            if merge is not None:
                args["merge"] = merge
            return _json_tool_result("enrichments_write", args)
        mcp.tool(name="enrichments_write")(mcp_enrichments_write)

        def mcp_export_annotations_csv(
            speaker: Optional[str] = None,
            outputPath: Optional[str] = None,
            dryRun: Optional[bool] = None,
        ) -> str:
            """Export annotations to CSV, or preview when outputPath is omitted."""
            args: Dict[str, Any] = {}
            if speaker is not None:
                args["speaker"] = speaker
            if outputPath is not None:
                args["outputPath"] = outputPath
            if dryRun is not None:
                args["dryRun"] = dryRun
            return _json_tool_result("export_annotations_csv", args)
        mcp.tool(name="export_annotations_csv")(mcp_export_annotations_csv)

        def mcp_export_annotations_elan(
            speaker: str,
            outputPath: Optional[str] = None,
            dryRun: Optional[bool] = None,
        ) -> str:
            """Export one speaker's annotations to ELAN .eaf XML."""
            args: Dict[str, Any] = {"speaker": speaker}
            if outputPath is not None:
                args["outputPath"] = outputPath
            if dryRun is not None:
                args["dryRun"] = dryRun
            return _json_tool_result("export_annotations_elan", args)
        mcp.tool(name="export_annotations_elan")(mcp_export_annotations_elan)

        def mcp_export_annotations_textgrid(
            speaker: str,
            outputPath: Optional[str] = None,
            dryRun: Optional[bool] = None,
        ) -> str:
            """Export one speaker's annotations to Praat TextGrid."""
            args: Dict[str, Any] = {"speaker": speaker}
            if outputPath is not None:
                args["outputPath"] = outputPath
            if dryRun is not None:
                args["dryRun"] = dryRun
            return _json_tool_result("export_annotations_textgrid", args)
        mcp.tool(name="export_annotations_textgrid")(mcp_export_annotations_textgrid)

        def mcp_export_lingpy_tsv(outputPath: Optional[str] = None, dryRun: Optional[bool] = None) -> str:
            """Export a LingPy TSV preview or write it inside the project."""
            args: Dict[str, Any] = {}
            if outputPath is not None:
                args["outputPath"] = outputPath
            if dryRun is not None:
                args["dryRun"] = dryRun
            return _json_tool_result("export_lingpy_tsv", args)
        mcp.tool(name="export_lingpy_tsv")(mcp_export_lingpy_tsv)

        def mcp_export_nexus(outputPath: Optional[str] = None, dryRun: Optional[bool] = None) -> str:
            """Export a NEXUS preview or write it inside the project."""
            args: Dict[str, Any] = {}
            if outputPath is not None:
                args["outputPath"] = outputPath
            if dryRun is not None:
                args["dryRun"] = dryRun
            return _json_tool_result("export_nexus", args)
        mcp.tool(name="export_nexus")(mcp_export_nexus)

        def mcp_jobs_list_active() -> str:
            """List active jobs in the shared PARSE job registry."""
            return _json_tool_result("jobs_list_active", {})
        mcp.tool(name="jobs_list_active")(mcp_jobs_list_active)

        def mcp_lexeme_notes_read(speaker: Optional[str] = None, conceptId: Optional[str] = None) -> str:
            """Read lexeme notes, optionally narrowed by speaker and/or concept."""
            args: Dict[str, Any] = {}
            if speaker is not None:
                args["speaker"] = speaker
            if conceptId is not None:
                args["conceptId"] = conceptId
            return _json_tool_result("lexeme_notes_read", args)
        mcp.tool(name="lexeme_notes_read")(mcp_lexeme_notes_read)

        def mcp_lexeme_notes_write(
            speaker: str,
            conceptId: str,
            userNote: Optional[str] = None,
            importNote: Optional[str] = None,
            delete: Optional[bool] = None,
        ) -> str:
            """Write or delete one lexeme note entry."""
            args: Dict[str, Any] = {"speaker": speaker, "conceptId": conceptId}
            if userNote is not None:
                args["userNote"] = userNote
            if importNote is not None:
                args["importNote"] = importNote
            if delete is not None:
                args["delete"] = delete
            return _json_tool_result("lexeme_notes_write", args)
        mcp.tool(name="lexeme_notes_write")(mcp_lexeme_notes_write)

        def mcp_peaks_generate(
            speaker: Optional[str] = None,
            audioPath: Optional[str] = None,
            outputPath: Optional[str] = None,
            samplesPerPixel: Optional[int] = None,
            dryRun: Optional[bool] = None,
        ) -> str:
            """Generate waveform peaks for a speaker or explicit audio file."""
            args: Dict[str, Any] = {}
            if speaker is not None:
                args["speaker"] = speaker
            if audioPath is not None:
                args["audioPath"] = audioPath
            if outputPath is not None:
                args["outputPath"] = outputPath
            if samplesPerPixel is not None:
                args["samplesPerPixel"] = samplesPerPixel
            if dryRun is not None:
                args["dryRun"] = dryRun
            return _json_tool_result("peaks_generate", args)
        mcp.tool(name="peaks_generate")(mcp_peaks_generate)

        def mcp_phonetic_rules_apply(
            form: str,
            mode: Optional[str] = None,
            form2: Optional[str] = None,
            rules: Optional[list] = None,
        ) -> str:
            """Normalize/apply/compare IPA forms using project phonetic rules."""
            args: Dict[str, Any] = {"form": form}
            if mode is not None:
                args["mode"] = mode
            if form2 is not None:
                args["form2"] = form2
            if rules is not None:
                args["rules"] = rules
            return _json_tool_result("phonetic_rules_apply", args)
        mcp.tool(name="phonetic_rules_apply")(mcp_phonetic_rules_apply)

        def mcp_read_audio_info(sourceWav: str) -> str:
            """Read WAV metadata without loading audio samples."""
            return _json_tool_result("read_audio_info", {"sourceWav": sourceWav})
        mcp.tool(name="read_audio_info")(mcp_read_audio_info)

        def mcp_read_text_preview(
            path: str,
            startLine: Optional[int] = None,
            maxLines: Optional[int] = None,
            maxChars: Optional[int] = None,
        ) -> str:
            """Read a bounded preview of a markdown/text file."""
            args: Dict[str, Any] = {"path": path}
            if startLine is not None:
                args["startLine"] = startLine
            if maxLines is not None:
                args["maxLines"] = maxLines
            if maxChars is not None:
                args["maxChars"] = maxChars
            return _json_tool_result("read_text_preview", args)
        mcp.tool(name="read_text_preview")(mcp_read_text_preview)

        def mcp_source_index_validate(
            mode: Optional[str] = None,
            speakerId: Optional[str] = None,
            speakerData: Optional[dict] = None,
            manifest: Optional[dict] = None,
            outputPath: Optional[str] = None,
        ) -> str:
            """Validate one source-index entry or a full source-index manifest."""
            args: Dict[str, Any] = {}
            if mode is not None:
                args["mode"] = mode
            if speakerId is not None:
                args["speakerId"] = speakerId
            if speakerData is not None:
                args["speakerData"] = speakerData
            if manifest is not None:
                args["manifest"] = manifest
            if outputPath is not None:
                args["outputPath"] = outputPath
            return _json_tool_result("source_index_validate", args)
        mcp.tool(name="source_index_validate")(mcp_source_index_validate)

        def mcp_transcript_reformat(
            inputPath: str,
            outputPath: Optional[str] = None,
            speaker: Optional[str] = None,
            sourceWav: Optional[str] = None,
            durationSec: Optional[float] = None,
            dryRun: Optional[bool] = None,
        ) -> str:
            """Reformat a *_coarse.json file into PARSE coarse-transcript schema."""
            args: Dict[str, Any] = {"inputPath": inputPath}
            if outputPath is not None:
                args["outputPath"] = outputPath
            if speaker is not None:
                args["speaker"] = speaker
            if sourceWav is not None:
                args["sourceWav"] = sourceWav
            if durationSec is not None:
                args["durationSec"] = durationSec
            if dryRun is not None:
                args["dryRun"] = dryRun
            return _json_tool_result("transcript_reformat", args)
        mcp.tool(name="transcript_reformat")(mcp_transcript_reformat)

    logger.info(
        "MCP exposing %s tools (expose_all_tools=%s)",
        len(selected_mcp_tool_names),
        str(expose_all_tools).lower(),
    )

    return mcp


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the PARSE MCP server on stdio."""
    import argparse

    parser = argparse.ArgumentParser(description="PARSE MCP Server")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Path to PARSE project root (default: $PARSE_PROJECT_ROOT or auto-detect)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging on stderr",
    )
    args = parser.parse_args()

    if not _MCP_AVAILABLE:
        print(
            "Error: MCP server requires the 'mcp' package.\n"
            "Install with: pip install 'mcp[cli]'",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    server = create_mcp_server(project_root=args.project_root)

    import asyncio

    async def _run():
        await server.run_stdio_async()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
