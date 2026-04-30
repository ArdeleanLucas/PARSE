from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ai.chat_tools import REGISTRY
from ai.workflow_tools import DEFAULT_MCP_WORKFLOW_TOOL_NAMES

MCP_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "mcp-tool-payloads"
CHAT_TOOL_NAMES = sorted(REGISTRY.keys())
WORKFLOW_TOOL_NAMES = list(DEFAULT_MCP_WORKFLOW_TOOL_NAMES)
PARITY_EXTRA_CHAT_TOOL_NAMES = (
    "compute_boundaries_start",
    "compute_boundaries_status",
    "retranscribe_with_boundaries_start",
    "retranscribe_with_boundaries_status",
)
ADAPTER_TOOL_NAME = "mcp_get_exposure_mode"
ALL_TARGET_TOOL_NAMES = list(dict.fromkeys(CHAT_TOOL_NAMES + list(PARITY_EXTRA_CHAT_TOOL_NAMES) + WORKFLOW_TOOL_NAMES))
ALL_CASE_TOOL_NAMES = ALL_TARGET_TOOL_NAMES + [ADAPTER_TOOL_NAME]
TEXT_EXTENSIONS = {
    ".csv",
    ".eaf",
    ".json",
    ".md",
    ".nex",
    ".parse.json",
    ".textgrid",
    ".TextGrid",
    ".tsv",
    ".txt",
}
BINARY_EXTENSIONS = {".wav", ".png"}


@dataclass(frozen=True)
class McpFixtureContext:
    workspace_root: Path
    input_root: Path
    seed_speaker_id: str
    compare_speaker_id: str
    onboard_speaker_id: str
    tag_name: str
    tag_color: str


@dataclass(frozen=True)
class McpServerHandle:
    repo_root: Path
    project_root: Path
    input_root: Path



def list_chat_tool_fixture_names(fixture_dir: Path = MCP_FIXTURE_DIR) -> list[str]:
    excluded_names = set(WORKFLOW_TOOL_NAMES) | {ADAPTER_TOOL_NAME}
    names = []
    for payload_path in sorted(fixture_dir.glob("*.json")):
        if payload_path.name.endswith(".invalid.json"):
            continue
        tool_name = payload_path.stem
        if tool_name in excluded_names:
            continue
        names.append(tool_name)
    return names



def list_workflow_tool_fixture_names(fixture_dir: Path = MCP_FIXTURE_DIR) -> list[str]:
    available = {path.stem for path in fixture_dir.glob("*.json") if not path.name.endswith(".invalid.json")}
    return [name for name in WORKFLOW_TOOL_NAMES if name in available]



def build_mcp_tools_capture(
    *,
    repo_root: Path,
    workspace_root: Path,
    input_root: Path,
    seed_speaker_id: str,
    compare_speaker_id: str,
    onboard_speaker_id: str,
    tag_name: str,
    tag_color: str,
) -> dict[str, Any]:
    context = McpFixtureContext(
        workspace_root=Path(workspace_root).resolve(),
        input_root=Path(input_root).resolve(),
        seed_speaker_id=str(seed_speaker_id),
        compare_speaker_id=str(compare_speaker_id),
        onboard_speaker_id=str(onboard_speaker_id),
        tag_name=str(tag_name),
        tag_color=str(tag_color),
    )
    return anyio.run(_build_mcp_tools_capture_async, Path(repo_root).resolve(), context)



def _load_payload_fixture(tool_name: str, *, invalid: bool = False) -> Any:
    suffix = ".invalid.json" if invalid else ".json"
    path = MCP_FIXTURE_DIR / f"{tool_name}{suffix}"
    return json.loads(path.read_text(encoding="utf-8"))



def _write_test_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 1600)



def _ensure_mcp_fixture_inputs(context: McpFixtureContext) -> None:
    (context.workspace_root / "config").mkdir(parents=True, exist_ok=True)
    (context.workspace_root / "notes").mkdir(parents=True, exist_ok=True)
    (context.input_root / "processed").mkdir(parents=True, exist_ok=True)

    (context.workspace_root / "config" / "ai_config.json").write_text("{}\n", encoding="utf-8")
    (context.workspace_root / "config" / "phonetic_rules.json").write_text("[]\n", encoding="utf-8")
    (context.workspace_root / "notes" / "fixture.md").write_text(
        "# MCP parity fixture\n\n- Base01\n- Base02\n",
        encoding="utf-8",
    )
    (context.workspace_root / "parse-memory.md").write_text(
        "# PARSE chat memory\n\n## Speakers\n- Base01\n",
        encoding="utf-8",
    )
    (context.input_root / "transcript-input.txt").write_text(
        json.dumps(
            {
                "segments": [
                    {"start": 0.0, "end": 0.1, "text": "ash"},
                    {"start": 0.1, "end": 0.2, "text": "bark"},
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    processed_wav = context.input_root / "processed" / "Proc01.wav"
    processed_annotation = context.input_root / "processed" / "Proc01.parse.json"
    processed_peaks = context.input_root / "processed" / "Proc01-peaks.json"
    processed_csv = context.input_root / "processed" / "Proc01.csv"
    _write_test_wav(processed_wav)
    processed_annotation.write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "parse-parity-fixture",
                "speaker": "Proc01",
                "source_audio": "audio/working/Proc01/Proc01.wav",
                "source_audio_duration_sec": 0.1,
                "metadata": {"language_code": "sdh", "timestamps_source": "processed"},
                "tiers": {
                    "concept": {
                        "display_order": 3,
                        "intervals": [{"start": 0.0, "end": 0.1, "text": "1: ash"}],
                    },
                    "speaker": {
                        "display_order": 4,
                        "intervals": [{"start": 0.0, "end": 0.1, "text": "Proc01"}],
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    processed_peaks.write_text(
        json.dumps({"duration": 0.1, "peaks": [0, 1, 0, -1]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    processed_csv.write_text("Name\tStart\tDuration\n(1)- ash\t0:00.000\t0:00.100\n", encoding="utf-8")

    enrichments_path = context.workspace_root / "parse-enrichments.json"
    if not enrichments_path.exists():
        enrichments_path.write_text('{"lexeme_notes": {}}\n', encoding="utf-8")
    backup_dir = context.workspace_root / "annotations" / "backups" / f"20260430T000000Z-{context.seed_speaker_id}-csv-reimport"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_files: list[str] = []
    for filename, source_path in (
        (f"{context.seed_speaker_id}.parse.json", context.workspace_root / "annotations" / f"{context.seed_speaker_id}.parse.json"),
        ("parse-enrichments.json", enrichments_path),
        ("concepts.csv", context.workspace_root / "concepts.csv"),
    ):
        if source_path.exists():
            shutil.copy2(source_path, backup_dir / filename)
            backup_files.append(filename)
    (backup_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "createdAt": "2026-04-30T00:00:00Z",
                "speaker": context.seed_speaker_id,
                "operation": "csv_only_reimport",
                "files": backup_files,
                "input": {
                    "sourceCsv": "<fixture>",
                    "commentsCsv": None,
                    "wavPath": f"audio/original/{context.seed_speaker_id}/source.wav",
                },
                "result": None,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )



def _copy_fixture_context(source: McpFixtureContext, destination_root: Path) -> McpFixtureContext:
    workspace_root = destination_root / "workspace"
    input_root = destination_root / "inputs"
    shutil.copytree(source.workspace_root, workspace_root)
    shutil.copytree(source.input_root, input_root)
    return McpFixtureContext(
        workspace_root=workspace_root,
        input_root=input_root,
        seed_speaker_id=source.seed_speaker_id,
        compare_speaker_id=source.compare_speaker_id,
        onboard_speaker_id=source.onboard_speaker_id,
        tag_name=source.tag_name,
        tag_color=source.tag_color,
    )



def _resolve_placeholders(value: Any, *, context: McpFixtureContext, setup_state: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_placeholders(item, context=context, setup_state=setup_state) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(item, context=context, setup_state=setup_state) for item in value]
    if not isinstance(value, str):
        return value

    placeholder_map = {
        "${WORKSPACE_ROOT}": str(context.workspace_root),
        "${INPUT_ROOT}": str(context.input_root),
        "${SEED_SPEAKER}": context.seed_speaker_id,
        "${COMPARE_SPEAKER}": context.compare_speaker_id,
        "${ONBOARD_SPEAKER}": context.onboard_speaker_id,
        "${TAG_NAME}": context.tag_name,
        "${TAG_COLOR}": context.tag_color,
        "${STT_JOB_ID}": setup_state.get("STT_JOB_ID", ""),
        "${STT_WORD_LEVEL_JOB_ID}": setup_state.get("STT_WORD_LEVEL_JOB_ID", ""),
        "${FORCED_ALIGN_JOB_ID}": setup_state.get("FORCED_ALIGN_JOB_ID", ""),
        "${IPA_JOB_ID}": setup_state.get("IPA_JOB_ID", ""),
        "${NORMALIZE_JOB_ID}": setup_state.get("NORMALIZE_JOB_ID", ""),
        "${PIPELINE_JOB_ID}": setup_state.get("PIPELINE_JOB_ID", ""),
    }
    resolved = value
    for token, replacement in placeholder_map.items():
        if token in resolved:
            resolved = resolved.replace(token, replacement)
    return resolved



def _artifact_snapshot(workspace_root: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for file_path in sorted(workspace_root.rglob("*")):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(workspace_root).as_posix()
        suffix = file_path.suffix
        if relative_path.endswith(".parse.json") or suffix == ".json":
            try:
                snapshot[relative_path] = {"kind": "json", "value": json.loads(file_path.read_text(encoding="utf-8"))}
                continue
            except Exception:
                pass
        if suffix in TEXT_EXTENSIONS:
            try:
                snapshot[relative_path] = {"kind": "text", "value": file_path.read_text(encoding="utf-8")}
                continue
            except Exception:
                pass
        snapshot[relative_path] = {
            "kind": "binary",
            "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
            "size": file_path.stat().st_size,
        }
    return snapshot



def _summarize_side_effects(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_keys = set(before)
    after_keys = set(after)
    written = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    changed = sorted(path for path in before_keys & after_keys if before[path] != after[path])
    details = {path: after[path] for path in written + changed}
    return {
        "written_files": written,
        "removed_files": removed,
        "changed_files": changed,
        "details": details,
    }



def _decode_json_or_text(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _normalize_embedded_json(value: Any) -> Any:
    if isinstance(value, str):
        decoded = _decode_json_or_text(value)
        if decoded is value:
            return value
        return _normalize_embedded_json(decoded)
    if isinstance(value, list):
        return [_normalize_embedded_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_embedded_json(item) for key, item in value.items()}
    return value


def _canonicalize_path_text(value: str, replacements: dict[str, str]) -> str:
    normalized = value.replace("\\", "/")
    for source, token in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalized.replace(source.replace("\\", "/"), token)
    return normalized


def _canonicalize_tool_value(value: Any, *, replacements: dict[str, str]) -> Any:
    value = _normalize_embedded_json(value)
    if isinstance(value, str):
        return _canonicalize_path_text(value, replacements)
    if isinstance(value, list):
        return [_canonicalize_tool_value(item, replacements=replacements) for item in value]
    if isinstance(value, dict):
        return {key: _canonicalize_tool_value(item, replacements=replacements) for key, item in value.items()}
    return value


def _normalize_tool_descriptor(tool: Any) -> dict[str, Any]:
    annotations = None
    if getattr(tool, "annotations", None) is not None:
        annotations = tool.annotations.model_dump(mode="json")
    meta = None
    if getattr(tool, "meta", None) is not None:
        meta = copy.deepcopy(tool.meta)
    family = "workflow" if tool.name in WORKFLOW_TOOL_NAMES else "chat"
    if tool.name == ADAPTER_TOOL_NAME:
        family = "adapter"
    return {
        "name": tool.name,
        "family": family,
        "description": tool.description,
        "inputSchema": tool.inputSchema,
        "outputSchema": tool.outputSchema,
        "annotations": annotations,
        "meta": meta,
    }



def _normalize_call_result(result: Any) -> dict[str, Any]:
    normalized_content: list[Any] = []
    for item in list(getattr(result, "content", []) or []):
        text = getattr(item, "text", None)
        if isinstance(text, str):
            normalized_content.append({"type": "text", "value": _decode_json_or_text(text)})
        else:
            normalized_content.append(item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item))
    structured_content = getattr(result, "structuredContent", None)
    if hasattr(structured_content, "model_dump"):
        structured_content = structured_content.model_dump(mode="json")
    structured_content = _normalize_embedded_json(structured_content)
    return {
        "isError": bool(getattr(result, "isError", False)),
        "content": normalized_content,
        "structuredContent": structured_content,
    }


async def _call_tool(session: ClientSession, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        result = await session.call_tool(tool_name, payload)
    except Exception as exc:  # pragma: no cover - runtime fallback path
        return {
            "raised": {
                "type": type(exc).__name__,
                "message": str(exc),
            }
        }
    return _normalize_call_result(result)



def _extract_job_id(result_payload: dict[str, Any]) -> str:
    if result_payload.get("raised"):
        raise RuntimeError(str(result_payload["raised"]))
    for item in result_payload.get("content", []):
        value = item.get("value") if isinstance(item, dict) else None
        if isinstance(value, dict):
            inner = value.get("result") if isinstance(value.get("result"), dict) else value
            job_id = str(inner.get("jobId") or inner.get("job_id") or "").strip() if isinstance(inner, dict) else ""
            if job_id:
                return job_id
    raise RuntimeError(f"No jobId found in setup result: {result_payload}")


async def _ensure_setup_value(session: ClientSession, context: McpFixtureContext, setup_state: dict[str, str], key: str) -> str:
    if key in setup_state and setup_state[key]:
        return setup_state[key]

    if key == "STT_JOB_ID":
        payload = {"speaker": context.seed_speaker_id, "sourceWav": f"audio/original/{context.seed_speaker_id}/source.wav"}
        setup_state[key] = _extract_job_id(await _call_tool(session, "stt_start", payload))
        return setup_state[key]
    if key == "STT_WORD_LEVEL_JOB_ID":
        payload = {"speaker": context.seed_speaker_id, "sourceWav": f"audio/original/{context.seed_speaker_id}/source.wav"}
        setup_state[key] = _extract_job_id(await _call_tool(session, "stt_word_level_start", payload))
        return setup_state[key]
    if key == "FORCED_ALIGN_JOB_ID":
        payload = {"speaker": context.seed_speaker_id}
        setup_state[key] = _extract_job_id(await _call_tool(session, "forced_align_start", payload))
        return setup_state[key]
    if key == "IPA_JOB_ID":
        payload = {"speaker": context.seed_speaker_id, "overwrite": False}
        setup_state[key] = _extract_job_id(await _call_tool(session, "ipa_transcribe_acoustic_start", payload))
        return setup_state[key]
    if key == "NORMALIZE_JOB_ID":
        payload = {"speaker": context.seed_speaker_id, "sourceWav": f"audio/original/{context.seed_speaker_id}/source.wav"}
        setup_state[key] = _extract_job_id(await _call_tool(session, "audio_normalize_start", payload))
        return setup_state[key]
    if key == "PIPELINE_JOB_ID":
        payload = {"speaker": context.seed_speaker_id, "steps": ["ortho"]}
        setup_state[key] = _extract_job_id(await _call_tool(session, "pipeline_run", payload))
        return setup_state[key]

    raise KeyError(key)


async def _resolve_setup_tokens(session: ClientSession, context: McpFixtureContext, payload: Any, setup_state: dict[str, str]) -> Any:
    if isinstance(payload, dict):
        return {key: await _resolve_setup_tokens(session, context, value, setup_state) for key, value in payload.items()}
    if isinstance(payload, list):
        values = []
        for item in payload:
            values.append(await _resolve_setup_tokens(session, context, item, setup_state))
        return values
    if not isinstance(payload, str):
        return payload

    for token in (
        "STT_JOB_ID",
        "STT_WORD_LEVEL_JOB_ID",
        "FORCED_ALIGN_JOB_ID",
        "IPA_JOB_ID",
        "NORMALIZE_JOB_ID",
        "PIPELINE_JOB_ID",
    ):
        marker = f"${{{token}}}"
        if marker in payload:
            value = await _ensure_setup_value(session, context, setup_state, token)
            payload = payload.replace(marker, value)
    return payload


async def _list_tools_catalog(handle: McpServerHandle) -> dict[str, Any]:
    async with _open_mcp_session(handle) as session:
        await session.initialize()
        listing = await session.list_tools()
    tools_by_name = {tool.name: _normalize_tool_descriptor(tool) for tool in listing.tools}
    return {
        "count": len(listing.tools),
        "names": sorted(tools_by_name.keys()),
        "tools": tools_by_name,
    }


async def _capture_tool_cases(handle: McpServerHandle, base_context: McpFixtureContext, tool_name: str) -> dict[str, Any]:
    with TemporaryDirectory(prefix=f"parse-mcp-tool-{tool_name.replace('_', '-')}-") as temp_root:
        working_context = _copy_fixture_context(base_context, Path(temp_root))
        server_handle = McpServerHandle(
            repo_root=handle.repo_root,
            project_root=working_context.workspace_root,
            input_root=working_context.input_root,
        )
        async with _open_mcp_session(server_handle) as session:
            await session.initialize()
            listing = await session.list_tools()
            descriptor = next((_normalize_tool_descriptor(tool) for tool in listing.tools if tool.name == tool_name), None)
            setup_state: dict[str, str] = {}
            replacements = {
                str(handle.repo_root.resolve()): "<repo>",
                str(working_context.workspace_root.resolve()): "<workspace>",
                str(working_context.input_root.resolve()): "<input-root>",
            }

            success_payload = _load_payload_fixture(tool_name)
            success_payload = await _resolve_setup_tokens(session, working_context, success_payload, setup_state)
            success_payload = _resolve_placeholders(success_payload, context=working_context, setup_state=setup_state)
            before_success = _artifact_snapshot(working_context.workspace_root)
            success_result = await _call_tool(session, tool_name, success_payload)
            after_success = _artifact_snapshot(working_context.workspace_root)

            invalid_payload = _load_payload_fixture(tool_name, invalid=True)
            invalid_payload = await _resolve_setup_tokens(session, working_context, invalid_payload, setup_state)
            invalid_payload = _resolve_placeholders(invalid_payload, context=working_context, setup_state=setup_state)
            before_invalid = _artifact_snapshot(working_context.workspace_root)
            invalid_result = await _call_tool(session, tool_name, invalid_payload)
            after_invalid = _artifact_snapshot(working_context.workspace_root)

    return {
        "descriptor": _canonicalize_tool_value(descriptor, replacements=replacements),
        "success": {
            "payload": _canonicalize_tool_value(success_payload, replacements=replacements),
            "response": _canonicalize_tool_value(success_result, replacements=replacements),
            "side_effects": _canonicalize_tool_value(_summarize_side_effects(before_success, after_success), replacements=replacements),
        },
        "invalid": {
            "payload": _canonicalize_tool_value(invalid_payload, replacements=replacements),
            "response": _canonicalize_tool_value(invalid_result, replacements=replacements),
            "side_effects": _canonicalize_tool_value(_summarize_side_effects(before_invalid, after_invalid), replacements=replacements),
        },
    }


async def _build_mcp_tools_capture_async(repo_root: Path, context: McpFixtureContext) -> dict[str, Any]:
    _ensure_mcp_fixture_inputs(context)
    handle = McpServerHandle(repo_root=repo_root, project_root=context.workspace_root, input_root=context.input_root)
    catalog = await _list_tools_catalog(handle)

    results: dict[str, Any] = {
        "registry_count": len(CHAT_TOOL_NAMES),
        "workflow_tool_count": len(WORKFLOW_TOOL_NAMES),
        "adapter_tool_count": 1,
        "target_tool_count": len(ALL_CASE_TOOL_NAMES),
        "target_tool_names": list(ALL_CASE_TOOL_NAMES),
        "catalog": {
            "count": catalog["count"],
            "names": catalog["names"],
            "adapter_tool_present": ADAPTER_TOOL_NAME in catalog["tools"],
            "missing_expected": [name for name in ALL_TARGET_TOOL_NAMES if name not in catalog["tools"]],
            "unexpected": [name for name in catalog["names"] if name not in set(ALL_TARGET_TOOL_NAMES) | {ADAPTER_TOOL_NAME}],
        },
        "tools": {},
    }

    for tool_name in ALL_CASE_TOOL_NAMES:
        results["tools"][tool_name] = await _capture_tool_cases(handle, context, tool_name)

    return results


@asynccontextmanager
async def _open_mcp_session(handle: McpServerHandle):
    config_dir = handle.project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "mcp_config.json").write_text('{"expose_all_tools": true}\n', encoding="utf-8")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "adapters.mcp_adapter", "--project-root", str(handle.project_root)],
        cwd=str(handle.repo_root),
        env={
            **os.environ,
            "PYTHONPATH": str(handle.repo_root / "python"),
            "PARSE_EXTERNAL_READ_ROOTS": "*",
            "PYTHONUNBUFFERED": "1",
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            yield session


__all__ = [
    "ALL_TARGET_TOOL_NAMES",
    "CHAT_TOOL_NAMES",
    "MCP_FIXTURE_DIR",
    "PARITY_EXTRA_CHAT_TOOL_NAMES",
    "WORKFLOW_TOOL_NAMES",
    "build_mcp_tools_capture",
    "list_chat_tool_fixture_names",
    "list_workflow_tool_fixture_names",
]
