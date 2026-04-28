from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.workflow_tools import DEFAULT_MCP_WORKFLOW_TOOL_NAMES
from external_api.catalog import (
    load_mcp_config as _shared_load_mcp_config,
    mcp_exposure_payload as _shared_mcp_exposure_payload,
    resolve_mcp_config_path as _shared_resolve_mcp_config_path,
    selected_mcp_tool_names as _shared_selected_mcp_tool_names,
)

logger = logging.getLogger("parse.mcp_adapter")

_ADAPTER_DIR = Path(__file__).resolve().parent.parent
_PYTHON_DIR = _ADAPTER_DIR.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

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
    """Return the preferred mcp_config.json path if one exists."""
    return _shared_resolve_mcp_config_path(project_root_path)

def _load_mcp_config(project_root_path: Path) -> Dict[str, Any]:
    """Load MCP adapter config used to choose shipped-default vs legacy-curated active mode."""
    return _shared_load_mcp_config(project_root_path)

def _selected_mcp_tool_names(
    all_tool_names: List[str],
    expose_all_tools: bool,
    *,
    config_path: Optional[str] = None,
) -> List[str]:
    """Return the MCP tool surface for this server instance."""
    return _shared_selected_mcp_tool_names(
        all_tool_names,
        expose_all_tools,
        config_path=config_path,
    )

def _mcp_exposure_payload(
    *,
    expose_all_tools: bool,
    config_source: Optional[str],
    parse_chat_tool_count: int,
    workflow_tool_count: int,
    mcp_tool_count: int,
) -> Dict[str, Any]:
    """Build a read-only MCP payload describing the active exposure mode."""
    return _shared_mcp_exposure_payload(
        expose_all_tools=expose_all_tools,
        config_source=config_source,
        parse_chat_tool_count=parse_chat_tool_count,
        workflow_tool_count=workflow_tool_count,
        mcp_tool_count=mcp_tool_count,
    )

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

__all__ = [
    'DEFAULT_MCP_WORKFLOW_TOOL_NAMES',
    '_resolve_project_root',
    '_resolve_mcp_config_path',
    '_load_mcp_config',
    '_selected_mcp_tool_names',
    '_mcp_exposure_payload',
    '_load_repo_parse_env',
    '_resolve_api_base',
    '_resolve_onboard_http_timeout',
    '_resolve_external_read_roots',
    '_resolve_memory_path',
]
