#!/usr/bin/env python3
"""Bounded PARSE-native chat tools for the built-in AI toolbox.

This module intentionally exposes a strict, read-only tool allowlist.
There is no arbitrary shell execution and no arbitrary filesystem access.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from compare import cognate_compute as cognate_compute_module
except Exception:
    cognate_compute_module = None

try:
    from compare import cross_speaker_match as cross_speaker_match_module
except Exception:
    cross_speaker_match_module = None


ANNOTATION_FILENAME_SUFFIX = ".parse.json"
ANNOTATION_LEGACY_FILENAME_SUFFIX = ".json"
SPEAKER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
TOKEN_RE = re.compile(r"[\w\u0600-\u06FF\u0750-\u077F]+", flags=re.UNICODE)
MUTATING_TOOL_NAME_RE = re.compile(
    r"(save|write|update|edit|patch|delete|remove|create|insert|import|rename|commit)",
    flags=re.IGNORECASE,
)
READ_ONLY_NOTICE = (
    "PARSE chat MVP is mostly read-only. Tools can inspect/analyze data and run background previews; "
    "only specific allowlisted tools may write dedicated support files such as contact lexeme config or parse-tags, "
    "not annotations or enrichments."
)
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
    "jobs_list",
    "job_status",
    "job_logs",
)
WRITE_ALLOWED_TOOL_NAMES = frozenset({
    "audio_normalize_start",
    "contact_lexeme_lookup",
    "enrichments_write",
    "export_annotations_csv",
    "export_annotations_elan",
    "export_annotations_textgrid",
    "export_lingpy_tsv",
    "export_nexus",
    "import_tag_csv",
    "peaks_generate",
    "source_index_validate",
    "transcript_reformat",
    "import_processed_speaker",
    "lexeme_notes_write",
    "onboard_speaker_import",
    "parse_memory_upsert_section",
    "apply_timestamp_offset",
    # Pipeline run kicks off background transcription jobs — it's
    # "mutating" in the sense that annotations get rewritten once the
    # job completes, but the tool itself just returns a jobId for the
    # caller to poll via compute_status.
    "pipeline_run",
    "prepare_tag_import",
})
TEXT_PREVIEW_EXTENSIONS = frozenset({".md", ".markdown", ".txt", ".rst"})
ONBOARD_AUDIO_EXTENSIONS = frozenset({".wav", ".flac", ".mp3", ".ogg", ".m4a"})
MEMORY_MAX_BYTES = 256 * 1024  # 256 KB cap on parse-memory.md
MEMORY_SECTION_SLUG_RE = re.compile(r"[^A-Za-z0-9 _./-]+")

TOOL_MUTABILITY_READ_ONLY = "read_only"
TOOL_MUTABILITY_STATEFUL_JOB = "stateful_job"
TOOL_MUTABILITY_MUTATING = "mutating"

TOOL_CONDITION_KIND_PROJECT_STATE = "project_state"
TOOL_CONDITION_KIND_FILE_PRESENCE = "file_presence"
TOOL_CONDITION_KIND_INPUT_SHAPE = "input_shape"
TOOL_CONDITION_KIND_FILESYSTEM_WRITE = "filesystem_write"
TOOL_CONDITION_KIND_JOB_STATE = "job_state"
TOOL_CONDITION_KINDS = frozenset({
    TOOL_CONDITION_KIND_PROJECT_STATE,
    TOOL_CONDITION_KIND_FILE_PRESENCE,
    TOOL_CONDITION_KIND_INPUT_SHAPE,
    TOOL_CONDITION_KIND_FILESYSTEM_WRITE,
    TOOL_CONDITION_KIND_JOB_STATE,
})


class ChatToolError(Exception):
    """Base chat tool error."""


class ChatToolValidationError(ChatToolError):
    """Tool input validation error."""


class ChatToolExecutionError(ChatToolError):
    """Tool runtime error."""


@dataclass(frozen=True)
class ToolCondition:
    """Machine-readable safety condition for agent-facing tool metadata."""

    id: str
    description: str
    severity: str = "required"
    kind: str = TOOL_CONDITION_KIND_PROJECT_STATE

    def to_payload(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "description": self.description,
            "severity": self.severity,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ChatToolSpec:
    """Tool definition for OpenAI function-calling, validation, and MCP metadata."""

    name: str
    description: str
    parameters: Dict[str, Any]
    mutability: str = TOOL_MUTABILITY_READ_ONLY
    supports_dry_run: bool = False
    dry_run_parameter: Optional[str] = None
    preconditions: Tuple[ToolCondition, ...] = ()
    postconditions: Tuple[ToolCondition, ...] = ()

    def mcp_annotations_payload(self) -> Dict[str, Any]:
        destructive = self.mutability == TOOL_MUTABILITY_MUTATING
        read_only = self.mutability == TOOL_MUTABILITY_READ_ONLY
        payload: Dict[str, Any] = {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": read_only,
        }
        return payload

    def mcp_meta_payload(self) -> Dict[str, Any]:
        return {
            "mutability": self.mutability,
            "supports_dry_run": self.supports_dry_run,
            "dry_run_parameter": self.dry_run_parameter,
            "preconditions": [condition.to_payload() for condition in self.preconditions],
            "postconditions": [condition.to_payload() for condition in self.postconditions],
        }


def _tool_condition(
    condition_id: str,
    description: str,
    *,
    severity: str = "required",
    kind: str = TOOL_CONDITION_KIND_PROJECT_STATE,
) -> ToolCondition:
    if kind not in TOOL_CONDITION_KINDS:
        raise ValueError("Unsupported ToolCondition kind: {0}".format(kind))
    return ToolCondition(
        id=condition_id,
        description=description,
        severity=severity,
        kind=kind,
    )


def _project_loaded_condition() -> ToolCondition:
    return _tool_condition(
        "project_loaded",
        "The PARSE project root must be available and readable.",
        kind=TOOL_CONDITION_KIND_PROJECT_STATE,
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_concept_id(value: Any) -> str:
    text = _normalize_space(value)
    if not text:
        return ""

    if text.startswith("#"):
        text = _normalize_space(text[1:])

    if ":" in text:
        text = _normalize_space(text.split(":", 1)[0])

    return text


def _concept_sort_key(concept_id: str) -> Tuple[int, float, str]:
    normalized = _normalize_concept_id(concept_id)
    try:
        return (0, float(normalized), normalized)
    except ValueError:
        return (1, float("inf"), normalized)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(default)

    return payload


def _json_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_schema_type(expected: str, value: Any) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _validate_schema(value: Any, schema: Dict[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if isinstance(expected_type, str):
        if not _matches_schema_type(expected_type, value):
            raise ChatToolValidationError(
                "{0} expected {1}, got {2}".format(path, expected_type, _json_type_name(value))
            )

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        if value not in enum_values:
            raise ChatToolValidationError(
                "{0} must be one of {1}".format(path, ", ".join([str(item) for item in enum_values]))
            )

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise ChatToolValidationError("{0} must be at least {1} characters".format(path, min_length))

        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            raise ChatToolValidationError("{0} must be <= {1} characters".format(path, max_length))

        pattern = schema.get("pattern")
        if isinstance(pattern, str) and pattern:
            if not re.match(pattern, value):
                raise ChatToolValidationError("{0} does not match required pattern".format(path))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and float(value) < float(minimum):
            raise ChatToolValidationError("{0} must be >= {1}".format(path, minimum))

        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and float(value) > float(maximum):
            raise ChatToolValidationError("{0} must be <= {1}".format(path, maximum))

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise ChatToolValidationError("{0} must contain at least {1} items".format(path, min_items))

        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            raise ChatToolValidationError("{0} must contain <= {1} items".format(path, max_items))

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, path="{0}[{1}]".format(path, index))

    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    raise ChatToolValidationError("{0}.{1} is required".format(path, key))

        properties = schema.get("properties")
        if isinstance(properties, dict):
            additional_allowed = bool(schema.get("additionalProperties", True))
            for key, item_value in value.items():
                if key not in properties:
                    if not additional_allowed:
                        raise ChatToolValidationError("{0}.{1} is not allowed".format(path, key))
                    continue

                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    _validate_schema(item_value, child_schema, path="{0}.{1}".format(path, key))


def _deepcopy_jsonable(payload: Any) -> Any:
    return copy.deepcopy(payload)


_WSL_MOUNT_RE = re.compile(r'^[/\\]mnt[/\\]([a-zA-Z])[/\\]?(.*)', re.DOTALL)


def _wsl_to_windows_path(raw: str) -> Optional[str]:
    """Convert a WSL /mnt/X/... path to a Windows drive-letter path.

    On Windows Python, /mnt/c/Users/... is not absolute (no drive letter),
    so pathlib anchors it under cwd and produces a broken UNC path.
    Returns the translated string, or None if the input isn't a WSL mount path.
    """
    if os.name != 'nt':
        return None
    m = _WSL_MOUNT_RE.match(raw)
    if not m:
        return None
    drive = m.group(1).upper()
    rest = m.group(2).replace('\\', '/')
    return f"{drive}:/{rest}" if rest else f"{drive}:/"


from ai.tools.acoustic_starter_tools import (
    ACOUSTIC_STARTER_TOOL_SPECS,
    tool_audio_normalize_start,
    tool_forced_align_start,
    tool_ipa_transcribe_acoustic_start,
    tool_stt_start,
    tool_stt_word_level_start,
)
from ai.tools.job_status_tools import (
    JOB_STATUS_TOOL_SPECS,
    tool_audio_normalize_status,
    tool_compute_status,
    tool_forced_align_status,
    tool_ipa_transcribe_acoustic_status,
    tool_job_logs,
    tool_job_status,
    tool_jobs_list,
    tool_jobs_list_active,
    tool_stt_status,
    tool_stt_word_level_status,
)
from ai.tools.memory_tools import (
    MEMORY_TOOL_SPECS,
    tool_parse_memory_read,
    tool_parse_memory_upsert_section,
)
from ai.tools.offset_apply_tools import (
    OFFSET_APPLY_TOOL_SPECS,
    tool_apply_timestamp_offset,
)
from ai.tools.offset_detection_tools import (
    OFFSET_DETECTION_TOOL_SPECS,
    tool_detect_timestamp_offset,
    tool_detect_timestamp_offset_from_pair,
)
from ai.tools.pipeline_orchestration_tools import (
    PIPELINE_ORCHESTRATION_TOOL_SPECS,
    tool_pipeline_run,
    tool_pipeline_state_batch,
    tool_pipeline_state_read,
)
from ai.tools.preview_tools import (
    PREVIEW_TOOL_SPECS,
    tool_read_audio_info,
    tool_read_csv_preview,
    tool_read_text_preview,
    tool_spectrogram_preview,
)
from ai.tools.project_read_tools import (
    PROJECT_READ_TOOL_SPECS,
    tool_annotation_read,
    tool_project_context_read,
    tool_speakers_list,
)
from ai.tools.speaker_import_tools import (
    SPEAKER_IMPORT_TOOL_SPECS,
    _extract_concepts_from_annotation,
    _resolve_onboard_source,
    _resolve_processed_csv_source,
    _resolve_processed_json_source,
    _write_concepts_csv,
    _write_project_json_for_processed_import,
    _write_source_index_for_processed_import,
    tool_import_processed_speaker,
    tool_onboard_speaker_import,
)
from ai.tools.tag_import_tools import (
    TAG_IMPORT_TOOL_SPECS,
    tool_import_tag_csv,
    tool_prepare_tag_import,
)


class ParseChatTools:
    """Strict read-only tool allowlist for PARSE chat."""

    def __init__(
        self,
        project_root: Path,
        config_path: Optional[Path] = None,
        docs_root: Optional[Path] = None,
        start_stt_job: Optional[Callable[[str, str, Optional[str]], str]] = None,
        get_job_snapshot: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        list_jobs: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        get_job_logs: Optional[Callable[[str, int, int], Dict[str, Any]]] = None,
        external_read_roots: Optional[Sequence[Path]] = None,
        memory_path: Optional[Path] = None,
        onboard_speaker: Optional[
            Callable[[str, Path, Optional[Path], bool], Dict[str, Any]]
        ] = None,
        # Launch a compute job of any registered type: "full_pipeline",
        # "ortho", "ipa_only", "contact-lexemes", "forced_align",
        # "ipa" (acoustic wav2vec2). Takes (compute_type, payload),
        # returns a jobId the caller polls via compute_status. Mirrors
        # ``/api/compute/<type>`` POST. Used by both the Tier 2/3
        # acoustic-alignment tools (PR #146) and the pipeline-run /
        # compute-status MCP surface (PR #144).
        start_compute_job: Optional[Callable[[str, Dict[str, Any]], str]] = None,
        # Preflight: returns ``_pipeline_state_for_speaker``'s shape for
        # a given speaker ({"normalize": {done, can_run, reason, ...},
        # "stt": {...}, "ortho": {...}, "ipa": {...}}). Surfaces what's
        # already done and whether each step *can* run now.
        pipeline_state: Optional[Callable[[str], Dict[str, Any]]] = None,
        # Start a normalize job for a speaker. Takes (speaker, source_wav_or_None),
        # returns a jobId to poll via audio_normalize_status / compute_status.
        start_normalize_job: Optional[Callable[[str, Optional[str]], str]] = None,
        # Return all currently-running job snapshots from the server's job registry.
        list_active_jobs: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.config_path = (Path(config_path).expanduser().resolve() if config_path else self.project_root / "config" / "ai_config.json")
        self.docs_root = Path(docs_root).expanduser().resolve() if docs_root else None

        # ``external_read_roots`` supports two modes:
        #   - a list of concrete absolute roots → paths must fall under one
        #   - a single-element list containing "*" or "/" (or a Path("*")) →
        #     wildcard mode, any absolute path that exists is readable
        # Wildcard is the "broad access" knob for local single-user setups
        # where enumerating every source tree is tedious; default stays
        # conservative so unintended deployments don't leak the filesystem.
        self.external_read_roots: List[Path] = []
        self.external_read_wildcard: bool = False
        for raw_root in external_read_roots or []:
            raw_str = str(raw_root).strip()
            if raw_str in {"*", "/", "**"}:
                self.external_read_wildcard = True
                continue
            try:
                resolved_root = Path(raw_root).expanduser().resolve()
            except Exception:
                continue
            if resolved_root not in self.external_read_roots:
                self.external_read_roots.append(resolved_root)

        self.memory_path = (
            Path(memory_path).expanduser().resolve()
            if memory_path
            else (self.project_root / "parse-memory.md").resolve()
        )

        self.annotations_dir = self.project_root / "annotations"
        self.audio_dir = self.project_root / "audio"
        self.peaks_dir = self.project_root / "peaks"
        self.phonetic_rules_path = self.project_root / "config" / "phonetic_rules.json"
        self.sil_config_path = self.project_root / "config" / "sil_contact_languages.json"
        self.project_json_path = self.project_root / "project.json"
        self.source_index_path = self.project_root / "source_index.json"
        self.enrichments_path = self.project_root / "parse-enrichments.json"
        self.tags_path = self.project_root / "parse-tags.json"

        self._start_stt_job = start_stt_job
        self._get_job_snapshot = get_job_snapshot
        self._list_jobs = list_jobs
        self._get_job_logs = get_job_logs
        self._onboard_speaker = onboard_speaker
        self._start_compute_job = start_compute_job
        self._pipeline_state = pipeline_state
        self._start_normalize_job = start_normalize_job
        self._list_active_jobs = list_active_jobs

        self._tool_specs: Dict[str, ChatToolSpec] = {
            **PROJECT_READ_TOOL_SPECS,
            **PREVIEW_TOOL_SPECS,
            **JOB_STATUS_TOOL_SPECS,
            **TAG_IMPORT_TOOL_SPECS,
            **OFFSET_DETECTION_TOOL_SPECS,
            **OFFSET_APPLY_TOOL_SPECS,
            **ACOUSTIC_STARTER_TOOL_SPECS,
            "cognate_compute_preview": ChatToolSpec(
                name="cognate_compute_preview",
                description=(
                    "Compute a read-only cognate/similarity preview from annotations. "
                    "Does not write parse-enrichments.json."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speakers": {
                            "type": "array",
                            "maxItems": 300,
                            "items": {"type": "string", "minLength": 1, "maxLength": 200},
                        },
                        "conceptIds": {
                            "type": "array",
                            "maxItems": 500,
                            "items": {"type": "string", "minLength": 1, "maxLength": 64},
                        },
                        "threshold": {"type": "number", "minimum": 0.01, "maximum": 2.0},
                        "contactLanguages": {
                            "type": "array",
                            "maxItems": 20,
                            "items": {"type": "string", "minLength": 1, "maxLength": 16},
                        },
                        "includeSimilarity": {"type": "boolean"},
                        "maxConcepts": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                },
            ),
            "cross_speaker_match_preview": ChatToolSpec(
                name="cross_speaker_match_preview",
                description=(
                    "Compute read-only cross-speaker match candidates from STT output and existing "
                    "annotations. Accepts sttJobId or inline sttSegments."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "sttJobId": {"type": "string", "minLength": 1, "maxLength": 128},
                        "sttSegments": {
                            "type": "array",
                            "maxItems": 20000,
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "start": {"type": "number"},
                                    "end": {"type": "number"},
                                    "startSec": {"type": "number"},
                                    "endSec": {"type": "number"},
                                    "text": {"type": "string"},
                                    "ipa": {"type": "string"},
                                    "ortho": {"type": "string"},
                                },
                            },
                        },
                        "topK": {"type": "integer", "minimum": 1, "maximum": 20},
                        "minConfidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "maxConcepts": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                },
            ),
            "contact_lexeme_lookup": ChatToolSpec(
                name="contact_lexeme_lookup",
                description=(
                    "Fetch reference forms (IPA transcriptions) for contact/comparison languages "
                    "from third-party sources (local CLDF, ASJP, Wikidata, Wiktionary, Grokipedia, "
                    "literature). Gated by dryRun: pass dryRun=true FIRST to preview what would be "
                    "fetched without touching sil_contact_languages.json, then dryRun=false after "
                    "the user confirms — only the second call writes. maxConcepts caps the sample "
                    "size per call for bounded previews."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["dryRun"],
                    "properties": {
                        "languages": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 10,
                            "items": {"type": "string", "minLength": 1, "maxLength": 16},
                            "description": "ISO 639 language codes, e.g. [\"ar\", \"fa\", \"ckb\"]",
                        },
                        "conceptIds": {
                            "type": "array",
                            "maxItems": 100,
                            "items": {"type": "string", "minLength": 1, "maxLength": 100},
                            "description": "Project concept IDs or English concept labels to look up. Defaults to all project concepts.",
                        },
                        "providers": {
                            "type": "array",
                            "maxItems": 10,
                            "items": {
                                "type": "string",
                                "enum": [
                                    "csv_override", "lingpy_wordlist", "pycldf", "pylexibank",
                                    "asjp", "cldf", "wikidata", "wiktionary", "grokipedia", "literature",
                                ],
                            },
                            "description": "Provider priority order. Defaults to full chain.",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, preview only — fetches via the provider registry but does NOT write to sil_contact_languages.json. If false, merges results and writes. Required.",
                        },
                        "maxConcepts": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "description": "Cap on concepts processed this call. Useful for bounded previews.",
                        },
                        "overwrite": {
                            "type": "boolean",
                            "description": "If true and dryRun is false, re-fetch even if forms already exist. Ignored when dryRun is true.",
                        },
                    },
                },
            ),
            **SPEAKER_IMPORT_TOOL_SPECS,
            **MEMORY_TOOL_SPECS,
            **PIPELINE_ORCHESTRATION_TOOL_SPECS,
            "enrichments_read": ChatToolSpec(
                name="enrichments_read",
                description=(
                    "Read parse-enrichments.json (cognate sets, similarities, borrowing flags, "
                    "lexeme notes). Optionally filter to specific top-level keys."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "keys": {
                            "type": "array",
                            "maxItems": 16,
                            "items": {"type": "string", "minLength": 1, "maxLength": 64},
                            "description": (
                                "Optional list of top-level keys to return "
                                "(e.g. [\"cognate_sets\", \"lexeme_notes\"]). "
                                "Omit to return the full payload."
                            ),
                        },
                    },
                },
            ),
            "enrichments_write": ChatToolSpec(
                name="enrichments_write",
                description=(
                    "Write keys into parse-enrichments.json. By default merges (shallow) into the "
                    "existing file; pass merge=false for a full replacement. Use with care — this "
                    "file contains cognate sets and borrowing flags."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["enrichments"],
                    "properties": {
                        "enrichments": {
                            "type": "object",
                            "description": "Object to merge into (or replace) parse-enrichments.json.",
                        },
                        "merge": {
                            "type": "boolean",
                            "description": "If true (default), shallow-merge into existing data. If false, replace entirely.",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, preview the resulting top-level keys without writing parse-enrichments.json.",
                        },
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "enrichments_payload_provided",
                        "The caller must supply an enrichments object to merge or replace.",
                        kind="input_shape",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "enrichments_file_updated",
                        "When dryRun=false, parse-enrichments.json is merged or replaced with the supplied payload.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "lexeme_notes_read": ChatToolSpec(
                name="lexeme_notes_read",
                description=(
                    "Read lexeme-level notes from parse-enrichments.json. "
                    "Optionally filter by speaker and/or conceptId."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Filter to a single speaker.",
                        },
                        "conceptId": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 128,
                            "description": "Filter to a single concept ID.",
                        },
                    },
                },
            ),
            "lexeme_notes_write": ChatToolSpec(
                name="lexeme_notes_write",
                description=(
                    "Write or delete a single lexeme note in parse-enrichments.json "
                    "(speaker + conceptId key). Supports userNote and importNote fields."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "conceptId"],
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID whose lexeme note will be updated.",
                        },
                        "conceptId": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 128,
                            "description": "Concept ID whose note entry will be created, updated, or deleted.",
                        },
                        "userNote": {
                            "type": "string",
                            "maxLength": 4096,
                            "description": "Human-authored note text to store under user_note.",
                        },
                        "importNote": {
                            "type": "string",
                            "maxLength": 4096,
                            "description": "Machine/import provenance note to store under import_note.",
                        },
                        "delete": {
                            "type": "boolean",
                            "description": "If true, removes the note entry for this speaker+concept.",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, preview the resulting lexeme_notes block without writing parse-enrichments.json.",
                        },
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "speaker_and_concept_provided",
                        "The caller must provide both speaker and conceptId to identify a single lexeme-note entry.",
                        kind="input_shape",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "lexeme_note_written",
                        "When dryRun=false, the targeted lexeme_notes entry is created, updated, or deleted in parse-enrichments.json.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "export_annotations_csv": ChatToolSpec(
                name="export_annotations_csv",
                description=(
                    "Export speaker annotations to CSV (IPA, ortho, concept, timing). "
                    "Pass speaker='all' to merge all speakers. Without outputPath returns a preview "
                    "of the first 20 rows; with outputPath writes the full CSV inside the project."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID or 'all' for a merged multi-speaker export.",
                        },
                        "outputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Project-relative or absolute path inside project root to write CSV.",
                        },
                        "dryRun": {"type": "boolean", "description": "Preview only — never writes."},
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "annotations_available_for_export",
                        "At least one annotation payload must be available for the requested speaker scope.",
                        kind="project_state",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "export_file_written",
                        "When dryRun=false and outputPath is provided, the requested export file is written inside the project.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "export_lingpy_tsv": ChatToolSpec(
                name="export_lingpy_tsv",
                description=(
                    "Export a LingPy-compatible wordlist TSV from enrichments + annotations "
                    "for cognate analysis. Without outputPath returns first 20 lines; "
                    "with outputPath writes inside the project."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "outputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Project-relative or absolute path inside project root.",
                        },
                        "dryRun": {"type": "boolean", "description": "Preview only — never writes."},
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "enrichments_and_annotations_available",
                        "parse-enrichments.json and the annotation inventory must contain enough data to build a LingPy export.",
                        kind="project_state",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "export_file_written",
                        "When dryRun=false and outputPath is provided, the requested export file is written inside the project.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "export_nexus": ChatToolSpec(
                name="export_nexus",
                description=(
                    "Export a NEXUS cognate-character matrix for BEAST2 / phylogenetic tools. "
                    "Characters are (concept, cognate group) pairs; values are 1/0/? per speaker. "
                    "Without outputPath returns a preview (first 2000 chars); "
                    "with outputPath writes inside the project."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "outputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Project-relative or absolute path inside project root.",
                        },
                        "dryRun": {"type": "boolean", "description": "Preview only — never writes."},
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "cognate_matrix_available",
                        "The project must contain enough cognate/enrichment data to build a NEXUS character matrix.",
                        kind="project_state",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "export_file_written",
                        "When dryRun=false and outputPath is provided, the requested export file is written inside the project.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "export_annotations_elan": ChatToolSpec(
                name="export_annotations_elan",
                description=(
                    "Export speaker annotations to ELAN .eaf XML format for use in ELAN or other "
                    "linguistic annotation tools. Without outputPath returns an XML preview "
                    "(first 2000 chars); with outputPath writes inside the project."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID whose annotations should be converted to ELAN format.",
                        },
                        "outputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Project-relative or absolute path inside project root (e.g. exports/speaker.eaf).",
                        },
                        "dryRun": {"type": "boolean", "description": "Preview only — never writes."},
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "speaker_annotation_exists",
                        "The requested speaker must already have an annotation file to export.",
                        kind="file_presence",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "export_file_written",
                        "When dryRun=false and outputPath is provided, the requested export file is written inside the project.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "export_annotations_textgrid": ChatToolSpec(
                name="export_annotations_textgrid",
                description=(
                    "Export speaker annotations to Praat TextGrid format (.TextGrid). "
                    "Without outputPath returns a TextGrid string preview (first 2000 chars); "
                    "with outputPath writes inside the project."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID whose annotations should be converted to TextGrid format.",
                        },
                        "outputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Project-relative or absolute path inside project root (e.g. exports/speaker.TextGrid).",
                        },
                        "dryRun": {"type": "boolean", "description": "Preview only — never writes."},
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "speaker_annotation_exists",
                        "The requested speaker must already have an annotation file to export.",
                        kind="file_presence",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "export_file_written",
                        "When dryRun=false and outputPath is provided, the requested export file is written inside the project.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "phonetic_rules_apply": ChatToolSpec(
                name="phonetic_rules_apply",
                description=(
                    "Apply the project phonetic rules to IPA forms. Three modes:\n"
                    "  normalize — strip delimiters, lowercase, normalise whitespace\n"
                    "  apply     — return all rule-generated variants of a form\n"
                    "  equivalence — compare two forms; returns isEquivalent + similarity score\n"
                    "Uses project phonetic_rules.json unless custom rules are supplied."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["form"],
                    "properties": {
                        "form": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 256,
                            "description": "Primary IPA form to operate on.",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["normalize", "apply", "equivalence"],
                            "description": "Operation mode (default: normalize).",
                        },
                        "form2": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 256,
                            "description": "Second form for equivalence mode.",
                        },
                        "rules": {
                            "type": "array",
                            "maxItems": 64,
                            "items": {"type": "object"},
                            "description": (
                                "Optional inline rule list (same schema as phonetic_rules.json entries). "
                                "Omit to use the project file."
                            ),
                        },
                    },
                },
            ),
            "transcript_reformat": ChatToolSpec(
                name="transcript_reformat",
                description=(
                    "Reformat a *_coarse.json alignment file into PARSE CoarseTranscript schema "
                    "(speaker, source_wav, duration_sec, segments[]). Without outputPath returns "
                    "the reformatted JSON object; with outputPath writes inside the project."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["inputPath"],
                    "properties": {
                        "inputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Path to the *_coarse.json file to reformat (absolute or project-relative).",
                        },
                        "outputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Project-relative or absolute path inside project root to write the result.",
                        },
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Override speaker ID (inferred from filename if omitted).",
                        },
                        "sourceWav": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Override source WAV path written into the output metadata.",
                        },
                        "durationSec": {
                            "type": "number",
                            "minimum": 0.0,
                            "description": "Override total duration in seconds (inferred from segments if omitted).",
                        },
                        "dryRun": {"type": "boolean", "description": "Return parsed JSON without writing."},
                    },
                },
            ),
            "peaks_generate": ChatToolSpec(
                name="peaks_generate",
                description=(
                    "Generate waveform peak data for a speaker's audio and write to "
                    "peaks/<speaker>.json (or a custom outputPath). Required for the "
                    "waveform visualiser after audio changes. Provide speaker or audioPath."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID — resolves audio from annotations.",
                        },
                        "audioPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Explicit audio file path (absolute or project-relative). Overrides speaker lookup.",
                        },
                        "outputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Where to write peaks JSON. Defaults to peaks/<speaker>.json.",
                        },
                        "samplesPerPixel": {
                            "type": "integer",
                            "minimum": 64,
                            "maximum": 8192,
                            "description": "Samples per waveform pixel (default 512).",
                        },
                        "dryRun": {"type": "boolean", "description": "Compute peaks but do not write to disk."},
                    },
                },
            ),
            "source_index_validate": ChatToolSpec(
                name="source_index_validate",
                description=(
                    "Validate a speaker manifest entry or full manifest against the SourceIndex schema. "
                    "Two modes:\n"
                    "  speaker — validate + transform one speaker entry; returns errors and transformed shape\n"
                    "  full    — validate + build the complete source_index.json; "
                    "optionally write to outputPath inside the project"
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["speaker", "full"],
                            "description": "Validation scope (default: speaker).",
                        },
                        "speakerId": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID (required for mode=speaker).",
                        },
                        "speakerData": {
                            "type": "object",
                            "description": "Speaker manifest entry to validate (required for mode=speaker).",
                        },
                        "manifest": {
                            "type": "object",
                            "description": "Full manifest with top-level 'speakers' key (required for mode=full).",
                        },
                        "outputPath": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Write built source_index.json here (mode=full only, project-relative or absolute inside project).",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, never writes outputPath even when provided; returns the validated/constructed payload only.",
                        },
                    },
                },
            ),
        }
        self._tool_specs = self._apply_default_metadata(self._tool_specs)

    def _apply_default_metadata(self, specs: Dict[str, ChatToolSpec]) -> Dict[str, ChatToolSpec]:
        return {name: self._with_default_metadata(spec) for name, spec in specs.items()}

    def _with_default_metadata(self, spec: ChatToolSpec) -> ChatToolSpec:
        properties = spec.parameters.get("properties") if isinstance(spec.parameters, dict) else {}
        has_dry_run_param = isinstance(properties, dict) and "dryRun" in properties
        mutability = self._default_mutability_for_tool(spec.name)
        supports_dry_run = bool(spec.supports_dry_run or has_dry_run_param)
        dry_run_parameter = spec.dry_run_parameter or ("dryRun" if has_dry_run_param else None)
        preconditions = spec.preconditions or self._default_preconditions_for_tool(spec.name, mutability)
        postconditions = spec.postconditions or self._default_postconditions_for_tool(spec.name, mutability)
        return replace(
            spec,
            mutability=mutability,
            supports_dry_run=supports_dry_run,
            dry_run_parameter=dry_run_parameter,
            preconditions=preconditions,
            postconditions=postconditions,
        )

    def _default_mutability_for_tool(self, tool_name: str) -> str:
        stateful_job_tools = {
            "stt_start",
            "stt_word_level_start",
            "forced_align_start",
            "ipa_transcribe_acoustic_start",
            "audio_normalize_start",
        }
        if tool_name in stateful_job_tools:
            return TOOL_MUTABILITY_STATEFUL_JOB
        if tool_name in WRITE_ALLOWED_TOOL_NAMES:
            return TOOL_MUTABILITY_MUTATING
        return TOOL_MUTABILITY_READ_ONLY

    def _default_preconditions_for_tool(self, tool_name: str, mutability: str) -> Tuple[ToolCondition, ...]:
        if tool_name in {"project_context_read", "speakers_list", "jobs_list", "jobs_list_active"}:
            return ()

        if tool_name in {
            "stt_start",
            "stt_word_level_start",
            "audio_normalize_start",
        }:
            return (
                _project_loaded_condition(),
                _tool_condition(
                    "source_audio_available",
                    "A readable source audio path must be provided or resolvable for the requested speaker.",
                    kind=TOOL_CONDITION_KIND_FILE_PRESENCE,
                ),
            )

        if tool_name in {"forced_align_start", "ipa_transcribe_acoustic_start"}:
            return (
                _project_loaded_condition(),
                _tool_condition(
                    "speaker_annotations_available",
                    "The requested speaker must already have the upstream annotation data needed for this compute job.",
                    kind=TOOL_CONDITION_KIND_PROJECT_STATE,
                ),
            )

        if tool_name in {
            "stt_status",
            "stt_word_level_status",
            "forced_align_status",
            "ipa_transcribe_acoustic_status",
            "audio_normalize_status",
            "compute_status",
        }:
            return (
                _tool_condition(
                    "job_id_known",
                    "The caller must provide a valid jobId from a previous start call.",
                    kind=TOOL_CONDITION_KIND_INPUT_SHAPE,
                ),
            )

        if tool_name in {
            "annotation_read",
            "cognate_compute_preview",
            "cross_speaker_match_preview",
            "detect_timestamp_offset",
            "detect_timestamp_offset_from_pair",
            "enrichments_read",
            "lexeme_notes_read",
            "parse_memory_read",
            "phonetic_rules_apply",
            "pipeline_state_batch",
            "pipeline_state_read",
            "read_audio_info",
            "read_csv_preview",
            "read_text_preview",
            "spectrogram_preview",
        }:
            return (_project_loaded_condition(),)

        if tool_name in {
            "contact_lexeme_lookup",
            "import_tag_csv",
            "parse_memory_upsert_section",
            "peaks_generate",
            "prepare_tag_import",
            "source_index_validate",
            "transcript_reformat",
        }:
            return (_project_loaded_condition(),)

        if mutability in {TOOL_MUTABILITY_MUTATING, TOOL_MUTABILITY_STATEFUL_JOB}:
            return (_project_loaded_condition(),)
        return ()

    def _default_postconditions_for_tool(self, tool_name: str, mutability: str) -> Tuple[ToolCondition, ...]:
        job_start_postconditions = {
            "stt_start": "stt_job_started",
            "stt_word_level_start": "word_level_stt_job_started",
            "forced_align_start": "forced_alignment_job_started",
            "ipa_transcribe_acoustic_start": "acoustic_ipa_job_started",
            "audio_normalize_start": "audio_normalize_job_started",
            "pipeline_run": "pipeline_job_started",
        }
        if tool_name in job_start_postconditions:
            return (
                _tool_condition(
                    job_start_postconditions[tool_name],
                    "Calling this tool starts or previews a background job that can be polled later.",
                    kind=TOOL_CONDITION_KIND_JOB_STATE,
                ),
            )

        read_snapshot_tools = {
            "annotation_read",
            "audio_normalize_status",
            "cognate_compute_preview",
            "compute_status",
            "cross_speaker_match_preview",
            "detect_timestamp_offset",
            "detect_timestamp_offset_from_pair",
            "enrichments_read",
            "forced_align_status",
            "ipa_transcribe_acoustic_status",
            "jobs_list_active",
            "lexeme_notes_read",
            "parse_memory_read",
            "phonetic_rules_apply",
            "pipeline_state_batch",
            "pipeline_state_read",
            "project_context_read",
            "read_audio_info",
            "read_csv_preview",
            "read_text_preview",
            "speakers_list",
            "spectrogram_preview",
            "stt_status",
            "stt_word_level_status",
        }
        if tool_name in read_snapshot_tools:
            return (
                _tool_condition(
                    "inspection_payload_returned",
                    "The tool returns structured inspection data without mutating project state.",
                    kind=TOOL_CONDITION_KIND_PROJECT_STATE,
                    severity="recommended",
                ),
            )

        mutating_file_postconditions = {
            "contact_lexeme_lookup": "contact_lexeme_data_updated",
            "import_tag_csv": "tag_import_written",
            "parse_memory_upsert_section": "parse_memory_section_written",
            "peaks_generate": "peaks_file_written",
            "prepare_tag_import": "tag_definition_written",
            "source_index_validate": "source_index_written",
            "transcript_reformat": "transcript_written",
        }
        if tool_name in mutating_file_postconditions:
            return (
                _tool_condition(
                    mutating_file_postconditions[tool_name],
                    "When the tool is not in preview mode, it writes or updates a project artifact.",
                    kind=TOOL_CONDITION_KIND_FILESYSTEM_WRITE,
                ),
            )

        if mutability == TOOL_MUTABILITY_READ_ONLY:
            return ()
        if mutability == TOOL_MUTABILITY_STATEFUL_JOB:
            return (
                _tool_condition(
                    "job_started",
                    "The call starts or previews a background job.",
                    kind=TOOL_CONDITION_KIND_JOB_STATE,
                ),
            )
        return (
            _tool_condition(
                "project_artifact_updated",
                "When not in preview mode, the tool updates project state.",
                kind=TOOL_CONDITION_KIND_FILESYSTEM_WRITE,
            ),
        )

    def openai_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return OpenAI tool schema objects for the allowlisted tools."""
        payload: List[Dict[str, Any]] = []
        for spec in self._tool_specs.values():
            payload.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": _deepcopy_jsonable(spec.parameters),
                    },
                }
            )
        return payload

    def iter_tool_specs(self) -> Tuple[ChatToolSpec, ...]:
        """Return all registered tool specs in a stable name-sorted order."""
        return tuple(self._tool_specs[name] for name in self.tool_names())

    def tool_spec(self, tool_name: str) -> ChatToolSpec:
        """Return the ChatToolSpec for a registered tool."""
        name = str(tool_name or "").strip()
        if name not in self._tool_specs:
            raise ChatToolValidationError("Tool is not allowlisted: {0}".format(name))
        return self._tool_specs[name]

    def tool_names(self) -> List[str]:
        """Return sorted tool names in allowlist."""
        return sorted(self._tool_specs.keys())

    @classmethod
    def get_all_tool_names(cls) -> List[str]:
        """Return the full built-in ParseChatTools surface without caller setup."""
        return cls(project_root=Path.cwd()).tool_names()

    def _finalize_read_only_result(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = _deepcopy_jsonable(payload)
        result["mode"] = "read-only"
        result["readOnly"] = True
        if "previewOnly" not in result:
            result["previewOnly"] = True
        if "readOnlyNotice" not in result:
            result["readOnlyNotice"] = READ_ONLY_NOTICE
        return result

    def _finalize_write_allowed_result(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = _deepcopy_jsonable(payload)

        preview_only = bool(
            result.get("previewOnly")
            or result.get("preview")
            or result.get("dryRun")
            or result.get("needsTagName")
        )
        if "previewOnly" not in result:
            result["previewOnly"] = preview_only

        if "readOnly" not in result:
            result["readOnly"] = preview_only

        if "mode" not in result:
            result["mode"] = "read-only" if bool(result.get("readOnly")) else "write-allowed"

        if bool(result.get("readOnly")):
            if "readOnlyNotice" not in result:
                result["readOnlyNotice"] = READ_ONLY_NOTICE
        else:
            result.pop("readOnlyNotice", None)

        return result

    def execute(self, tool_name: str, raw_args: Any) -> Dict[str, Any]:
        """Execute a validated allowlisted tool."""
        name = str(tool_name or "").strip()
        if name not in self._tool_specs:
            if MUTATING_TOOL_NAME_RE.search(name):
                raise ChatToolValidationError(
                    "Mutating tool calls are disabled: {0}. {1}".format(name, READ_ONLY_NOTICE)
                )
            raise ChatToolValidationError("Tool is not allowlisted: {0}".format(name))

        # Defense-in-depth: mutating tool names remain blocked even if added by mistake,
        # except for explicitly allowlisted tools that may write dedicated support files.
        if MUTATING_TOOL_NAME_RE.search(name) and name not in WRITE_ALLOWED_TOOL_NAMES:
            raise ChatToolValidationError(
                "Mutating tool calls are disabled in read-only mode: {0}.".format(name)
            )

        args = raw_args
        if args is None:
            args = {}
        if isinstance(args, str):
            text = args.strip()
            if not text:
                args = {}
            else:
                try:
                    args = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ChatToolValidationError(
                        "Tool arguments must be valid JSON: {0}".format(exc)
                    )

        if not isinstance(args, dict):
            raise ChatToolValidationError("Tool arguments must be a JSON object")

        spec = self._tool_specs[name]
        _validate_schema(args, spec.parameters)

        handler_name = "_tool_{0}".format(name)
        handler = getattr(self, handler_name, None)
        if not callable(handler):
            raise ChatToolExecutionError("Tool handler missing for {0}".format(name))

        result = handler(args)
        if not isinstance(result, dict):
            raise ChatToolExecutionError("Tool handler must return a JSON object")

        return {
            "tool": name,
            "ok": True,
            "result": (
                self._finalize_write_allowed_result(result)
                if name in WRITE_ALLOWED_TOOL_NAMES
                else self._finalize_read_only_result(result)
            ),
        }

    def _normalize_speaker(self, raw_speaker: Any) -> str:
        speaker = _normalize_space(raw_speaker)
        if not speaker:
            raise ChatToolValidationError("speaker is required")

        if not SPEAKER_PATTERN.match(speaker):
            raise ChatToolValidationError("speaker contains unsupported characters")

        return speaker

    def _resolve_project_path(self, raw_path: str, allowed_roots: Sequence[Path]) -> Path:
        value = str(raw_path or "").strip()
        if not value:
            raise ChatToolValidationError("Path is required")

        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate

        resolved = candidate.resolve()

        try:
            resolved.relative_to(self.project_root)
        except ValueError:
            raise ChatToolValidationError("Path escapes project root")

        if allowed_roots:
            allowed = False
            for root in allowed_roots:
                root_resolved = root.resolve()
                try:
                    resolved.relative_to(root_resolved)
                    allowed = True
                    break
                except ValueError:
                    continue

            if not allowed:
                safe_roots = [str(root.resolve()) for root in allowed_roots]
                raise ChatToolValidationError(
                    "Path is outside allowed roots: {0}".format(", ".join(safe_roots))
                )

        return resolved

    def _resolve_readable_path(self, raw_path: str, *, extra_roots: Sequence[Path] = ()) -> Path:
        """Resolve an arbitrary read path against the project root or a configured external root.

        Expanded allowed roots = [project_root, *external_read_roots, *extra_roots]. Paths may
        be absolute (then must fall under one of the roots) or relative (resolved against
        project_root). When ``external_read_wildcard`` is set (PARSE_EXTERNAL_READ_ROOTS=*)
        any absolute path is accepted. Raises ChatToolValidationError on escape with a
        message listing the actual allowed roots so the caller knows what to fix.
        """
        value = str(raw_path or "").strip()
        if not value:
            raise ChatToolValidationError("Path is required")

        allowed_roots: List[Path] = [self.project_root]
        for root in self.external_read_roots:
            if root not in allowed_roots:
                allowed_roots.append(root)
        for root in extra_roots:
            resolved_extra = Path(root).expanduser().resolve()
            if resolved_extra not in allowed_roots:
                allowed_roots.append(resolved_extra)

        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            # On Windows Python, /mnt/X/... paths are WSL drive-letter mounts and
            # are not recognised as absolute.  Translate before anchoring so we
            # resolve to the real Windows path (C:\...) rather than appending the
            # raw string under project_root and ending up with a broken UNC path.
            translated = _wsl_to_windows_path(value)
            if translated is not None:
                candidate = Path(translated)
            else:
                candidate = self.project_root / candidate

        resolved = candidate.resolve()

        if self.external_read_wildcard:
            return resolved

        for root in allowed_roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue

        raise ChatToolValidationError(
            "Path {0!r} is outside allowed read roots. Allowed: {1}. "
            "Extend access by setting PARSE_EXTERNAL_READ_ROOTS "
            "(e.g. '/mnt/c/Users/Lucas/Thesis') or use '*' for no sandbox.".format(
                str(resolved), ", ".join([str(root) for root in allowed_roots])
            )
        )

    def _annotation_path_for_speaker(self, speaker: str) -> Optional[Path]:
        primary = (self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)).resolve()
        legacy = (self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_LEGACY_FILENAME_SUFFIX)).resolve()

        for candidate in [primary, legacy]:
            try:
                candidate.relative_to(self.annotations_dir.resolve())
            except ValueError:
                continue
            if candidate.exists() and candidate.is_file():
                return candidate

        return None

    def _tool_project_context_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_project_context_read(self, args)



    def _tool_annotation_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_annotation_read(self, args)


    def _tool_stt_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_stt_start(self, args)

    def _tool_stt_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_stt_status(self, args)


    # ------------------------------------------------------------------
    # Tier 1/2/3 acoustic alignment tools (from feat/acoustic-alignment-ipa)
    # ------------------------------------------------------------------

    def _tool_stt_word_level_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_stt_word_level_start(self, args)

    def _tool_stt_word_level_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_stt_word_level_status(self, args)


    def _tool_forced_align_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_forced_align_start(self, args)

    def _tool_forced_align_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_forced_align_status(self, args)


    def _tool_ipa_transcribe_acoustic_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_ipa_transcribe_acoustic_start(self, args)

    def _tool_ipa_transcribe_acoustic_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_ipa_transcribe_acoustic_status(self, args)



    # ------------------------------------------------------------------
    # Pipeline preflight + run + status tools (from feat/mcp-pipeline-tools)
    # ------------------------------------------------------------------

    def _tool_speakers_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_speakers_list(self, args)


    def _tool_pipeline_state_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_pipeline_state_read(self, args)

    def _tool_pipeline_state_batch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_pipeline_state_batch(self, args)

    def _tool_pipeline_run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_pipeline_run(self, args)

    def _tool_compute_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_compute_status(self, args)


    # ------------------------------------------------------------------
    # Tier 1 — audio normalize
    # ------------------------------------------------------------------

    def _tool_audio_normalize_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_audio_normalize_start(self, args)

    def _tool_audio_normalize_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_audio_normalize_status(self, args)


    # ------------------------------------------------------------------
    # Tier 1 — enrichments read / write
    # ------------------------------------------------------------------

    def _tool_enrichments_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return parse-enrichments.json, optionally filtered to specified top-level keys."""
        payload = _read_json_file(self.enrichments_path, {})
        if not isinstance(payload, dict):
            payload = {}
        keys = args.get("keys")
        if isinstance(keys, list) and keys:
            payload = {k: payload[k] for k in keys if k in payload}
        return {"readOnly": True, "enrichments": payload}

    def _tool_enrichments_write(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Shallow-merge (default) or replace parse-enrichments.json with the provided object."""
        incoming = args.get("enrichments")
        if not isinstance(incoming, dict):
            raise ChatToolValidationError("enrichments must be an object")

        merge = bool(args.get("merge", True))
        if merge:
            existing = _read_json_file(self.enrichments_path, {})
            if not isinstance(existing, dict):
                existing = {}
            existing.update(incoming)
            payload = existing
        else:
            payload = incoming

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "dryRun": True,
                "merge": merge,
                "incomingKeys": list(incoming.keys()),
                "resultingKeys": list(payload.keys()),
                "path": str(self.enrichments_path),
            }

        self.enrichments_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return {"success": True, "keys": list(payload.keys())}

    # ------------------------------------------------------------------
    # Tier 1 — lexeme notes read / write
    # ------------------------------------------------------------------

    def _tool_lexeme_notes_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return lexeme_notes block from enrichments, optionally filtered by speaker / conceptId."""
        enrichments = _read_json_file(self.enrichments_path, {})
        notes: Any = enrichments.get("lexeme_notes") or {}
        if not isinstance(notes, dict):
            notes = {}

        speaker_filter = str(args.get("speaker") or "").strip()
        concept_filter = _normalize_concept_id(args.get("conceptId") or "")

        if speaker_filter:
            notes = {speaker_filter: notes.get(speaker_filter, {})}
        if concept_filter:
            filtered: Dict[str, Any] = {}
            for sp, sp_notes in notes.items():
                if isinstance(sp_notes, dict) and concept_filter in sp_notes:
                    filtered[sp] = {concept_filter: sp_notes[concept_filter]}
            notes = filtered

        return {"readOnly": True, "lexeme_notes": notes}

    def _tool_lexeme_notes_write(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert or delete a single (speaker, conceptId) lexeme note inside parse-enrichments.json."""
        speaker = self._normalize_speaker(args.get("speaker"))
        concept_id = _normalize_concept_id(args.get("conceptId") or "")
        if not concept_id:
            raise ChatToolValidationError("conceptId is required")

        payload = _read_json_file(self.enrichments_path, {})
        if not isinstance(payload, dict):
            payload = {}

        notes_block = payload.get("lexeme_notes")
        if not isinstance(notes_block, dict):
            notes_block = {}
            payload["lexeme_notes"] = notes_block

        speaker_block = notes_block.get(speaker)
        if not isinstance(speaker_block, dict):
            speaker_block = {}
            notes_block[speaker] = speaker_block

        if bool(args.get("delete", False)):
            speaker_block.pop(concept_id, None)
            if not speaker_block:
                notes_block.pop(speaker, None)
        else:
            entry = speaker_block.get(concept_id)
            if not isinstance(entry, dict):
                entry = {}
            if "userNote" in args:
                entry["user_note"] = str(args.get("userNote") or "")
            if "importNote" in args:
                entry["import_note"] = str(args.get("importNote") or "")
            entry["updated_at"] = _utc_now_iso()
            speaker_block[concept_id] = entry

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "dryRun": True,
                "speaker": speaker,
                "conceptId": concept_id,
                "delete": bool(args.get("delete", False)),
                "lexeme_notes": payload.get("lexeme_notes") or {},
            }

        self.enrichments_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return {"success": True, "lexeme_notes": payload.get("lexeme_notes") or {}}

    # ------------------------------------------------------------------
    # Tier 1 — export tools
    # ------------------------------------------------------------------

    def _tool_export_annotations_csv(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Export annotations as CSV. Preview = first 20 rows; write requires outputPath."""
        try:
            from csv_export import (  # type: ignore[import]
                annotations_to_csv_str,
                _collect_all_rows,
                _sort_rows_all,
                _rows_to_csv_string,
            )
        except Exception as exc:
            raise ChatToolExecutionError("csv_export is not importable: {0}".format(exc))

        speaker_raw = str(args.get("speaker") or "all").strip()
        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        try:
            if speaker_raw == "all":
                rows = _collect_all_rows(self.annotations_dir)
                _sort_rows_all(rows)
                csv_content = _rows_to_csv_string(rows)
            else:
                sp = self._normalize_speaker(speaker_raw)
                ann_path = self.annotations_dir / "{0}{1}".format(sp, ANNOTATION_FILENAME_SUFFIX)
                if not ann_path.exists():
                    raise ChatToolExecutionError("No annotation found for speaker: {0}".format(sp))
                data = json.loads(ann_path.read_text(encoding="utf-8"))
                csv_content = annotations_to_csv_str(data, sp)
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("CSV export failed: {0}".format(exc)) from exc

        if dry_run or not output_path_str:
            lines = csv_content.splitlines()
            return {
                "readOnly": True,
                "previewOnly": True,
                "previewLines": "\n".join(lines[:20]),
                "totalLines": len(lines),
                "truncated": len(lines) > 20,
            }

        out_path = self._resolve_project_path(output_path_str, allowed_roots=[self.project_root])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(csv_content, encoding="utf-8-sig")
        return {
            "success": True,
            "outputPath": str(out_path),
            "lines": len(csv_content.splitlines()),
        }

    def _tool_export_lingpy_tsv(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Export LingPy wordlist TSV. Preview = first 20 lines via temp file; write requires outputPath."""
        if cognate_compute_module is None:
            raise ChatToolExecutionError("cognate_compute is not importable")

        import os as _os
        import tempfile

        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        try:
            if dry_run or not output_path_str:
                tmp_fd, tmp_str = tempfile.mkstemp(suffix=".tsv")
                _os.close(tmp_fd)
                tmp_path = Path(tmp_str)
                try:
                    count = cognate_compute_module.export_wordlist_tsv(
                        self.enrichments_path, self.annotations_dir, tmp_path
                    )
                    content = tmp_path.read_text(encoding="utf-8")
                finally:
                    try:
                        _os.unlink(tmp_str)
                    except OSError:
                        pass
                lines = content.splitlines()
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "previewLines": "\n".join(lines[:20]),
                    "totalLines": len(lines),
                    "truncated": len(lines) > 20,
                    "rowCount": count,
                }

            out_path = self._resolve_project_path(output_path_str, allowed_roots=[self.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            count = cognate_compute_module.export_wordlist_tsv(
                self.enrichments_path, self.annotations_dir, out_path
            )
            return {"success": True, "outputPath": str(out_path), "rowCount": count}
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("LingPy TSV export failed: {0}".format(exc)) from exc

    def _tool_export_nexus(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Build NEXUS matrix via _build_nexus_text(). Preview = first 2000 chars; write requires outputPath."""
        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        try:
            nexus_text = self._build_nexus_text()
        except Exception as exc:
            raise ChatToolExecutionError("NEXUS build failed: {0}".format(exc)) from exc

        if dry_run or not output_path_str:
            return {
                "readOnly": True,
                "previewOnly": True,
                "preview": nexus_text[:2000],
                "truncated": len(nexus_text) > 2000,
                "totalChars": len(nexus_text),
            }

        out_path = self._resolve_project_path(output_path_str, allowed_roots=[self.project_root])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(nexus_text, encoding="utf-8")
        return {"success": True, "outputPath": str(out_path), "totalChars": len(nexus_text)}

    def _build_nexus_text(self) -> str:
        """Build NEXUS cognate-character matrix (mirrors server._api_get_export_nexus)."""
        enrichments = _read_json_file(self.enrichments_path, {})
        overrides = enrichments.get("manual_overrides") or {}
        override_sets = overrides.get("cognate_sets") if isinstance(overrides, dict) else None
        auto_sets = enrichments.get("cognate_sets") if isinstance(enrichments, dict) else None
        override_sets = override_sets if isinstance(override_sets, dict) else {}
        auto_sets = auto_sets if isinstance(auto_sets, dict) else {}

        speakers_set: set = set()
        project_payload = _read_json_file(self.project_json_path, {})
        speakers_block = project_payload.get("speakers") if isinstance(project_payload, dict) else None
        if isinstance(speakers_block, dict):
            speakers_set.update(str(s) for s in speakers_block.keys() if str(s).strip())
        elif isinstance(speakers_block, list):
            speakers_set.update(str(s) for s in speakers_block if str(s).strip())

        union_keys: List[str] = []
        seen_keys: set = set()
        for key in list(override_sets.keys()) + list(auto_sets.keys()):
            if key not in seen_keys:
                seen_keys.add(key)
                union_keys.append(key)

        concept_keys: List[str] = []
        concept_group_members: Dict[str, Dict[str, List[str]]] = {}
        for key in union_keys:
            override_block = override_sets.get(key)
            auto_block = auto_sets.get(key)
            block = override_block if isinstance(override_block, dict) else auto_block
            if not isinstance(block, dict):
                continue
            groups: Dict[str, List[str]] = {}
            for group, members in block.items():
                if not isinstance(members, list):
                    continue
                cleaned = [str(m) for m in members if str(m).strip()]
                if cleaned:
                    groups[str(group)] = cleaned
                    speakers_set.update(cleaned)
            if groups:
                concept_group_members[key] = groups
                concept_keys.append(key)

        speakers = sorted(speakers_set)

        has_form: Dict[str, set] = {}
        for key in concept_keys:
            present: set = set()
            for members in concept_group_members[key].values():
                present.update(members)
            has_form[key] = present

        characters: List[Tuple[str, str, str]] = []
        for key in sorted(concept_keys, key=_concept_sort_key):
            for group in sorted(concept_group_members[key].keys()):
                label = "{0}_{1}".format(str(key).replace(" ", "_"), group)
                characters.append((key, group, label))

        def row_for(speaker: str) -> str:
            chars: List[str] = []
            for key, group, _lbl in characters:
                members = concept_group_members[key].get(group, [])
                if speaker in members:
                    chars.append("1")
                elif speaker in has_form.get(key, set()):
                    chars.append("0")
                else:
                    chars.append("?")
            return "".join(chars)

        lines: List[str] = []
        lines.append("#NEXUS")
        lines.append("")
        lines.append("BEGIN TAXA;")
        lines.append("    DIMENSIONS NTAX={0};".format(len(speakers)))
        if speakers:
            lines.append("    TAXLABELS")
            for sp in speakers:
                lines.append("        {0}".format(sp))
            lines.append("    ;")
        lines.append("END;")
        lines.append("")
        lines.append("BEGIN CHARACTERS;")
        lines.append("    DIMENSIONS NCHAR={0};".format(len(characters)))
        lines.append("    FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS=\"01\";")
        if characters:
            lines.append("    CHARSTATELABELS")
            label_rows_str = []
            for idx, (_key, _group, label) in enumerate(characters, start=1):
                label_rows_str.append("        {0} {1}".format(idx, label))
            lines.append(",\n".join(label_rows_str))
            lines.append("    ;")
        lines.append("    MATRIX")
        for sp in speakers:
            lines.append("        {0}    {1}".format(sp, row_for(sp)))
        lines.append("    ;")
        lines.append("END;")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tier 2 — ELAN / TextGrid export
    # ------------------------------------------------------------------

    def _tool_export_annotations_elan(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Export annotation to ELAN .eaf XML. Preview = first 2000 chars; write requires outputPath."""
        try:
            from elan_export import annotations_to_elan_str, export_elan  # type: ignore[import]
        except Exception as exc:
            raise ChatToolExecutionError("elan_export is not importable: {0}".format(exc))

        speaker = self._normalize_speaker(args.get("speaker"))
        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        ann_path = self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)
        if not ann_path.exists():
            raise ChatToolExecutionError("No annotation found for speaker: {0}".format(speaker))

        try:
            data = json.loads(ann_path.read_text(encoding="utf-8"))
            if dry_run or not output_path_str:
                elan_str = annotations_to_elan_str(data, speaker)
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "preview": elan_str[:2000],
                    "truncated": len(elan_str) > 2000,
                    "totalChars": len(elan_str),
                }
            out_path = self._resolve_project_path(output_path_str, allowed_roots=[self.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            export_elan(data, out_path, speaker)
            return {"success": True, "outputPath": str(out_path)}
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("ELAN export failed: {0}".format(exc)) from exc

    def _tool_export_annotations_textgrid(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Export annotation to Praat TextGrid. Preview = first 2000 chars; write requires outputPath."""
        try:
            from textgrid_io import annotations_to_textgrid_str, write_textgrid  # type: ignore[import]
        except Exception as exc:
            raise ChatToolExecutionError("textgrid_io is not importable: {0}".format(exc))

        speaker = self._normalize_speaker(args.get("speaker"))
        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        ann_path = self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)
        if not ann_path.exists():
            raise ChatToolExecutionError("No annotation found for speaker: {0}".format(speaker))

        try:
            data = json.loads(ann_path.read_text(encoding="utf-8"))
            if dry_run or not output_path_str:
                tg_str = annotations_to_textgrid_str(data, speaker)
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "preview": tg_str[:2000],
                    "truncated": len(tg_str) > 2000,
                    "totalChars": len(tg_str),
                }
            out_path = self._resolve_project_path(output_path_str, allowed_roots=[self.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            write_textgrid(data, out_path, speaker)
            return {"success": True, "outputPath": str(out_path)}
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("TextGrid export failed: {0}".format(exc)) from exc

    # ------------------------------------------------------------------
    # Tier 2 — phonetic rules
    # ------------------------------------------------------------------

    def _tool_phonetic_rules_apply(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize, apply, or compare IPA forms using project phonetic rules."""
        try:
            from compare.phonetic_rules import (  # type: ignore[import]
                apply_rules,
                are_phonetically_equivalent,
                load_rules_from_file,
                normalize_ipa_form,
            )
        except Exception as exc:
            raise ChatToolExecutionError("phonetic_rules is not importable: {0}".format(exc))

        form = str(args.get("form") or "").strip()
        if not form:
            raise ChatToolValidationError("form is required")

        mode = str(args.get("mode") or "normalize").strip().lower()
        inline_rules = args.get("rules")

        if isinstance(inline_rules, list) and inline_rules:
            rules = inline_rules
        else:
            rules = load_rules_from_file(self.phonetic_rules_path)

        try:
            if mode == "normalize":
                result = normalize_ipa_form(form)
                return {"readOnly": True, "mode": "normalize", "form": form, "normalized": result}

            if mode == "apply":
                normalized = normalize_ipa_form(form)
                variants = apply_rules(normalized, rules)
                return {
                    "readOnly": True,
                    "mode": "apply",
                    "form": form,
                    "normalized": normalized,
                    "variants": variants,
                }

            if mode == "equivalence":
                form2 = str(args.get("form2") or "").strip()
                if not form2:
                    raise ChatToolValidationError("form2 is required for equivalence mode")
                is_equiv, score = are_phonetically_equivalent(form, form2, rules)
                return {
                    "readOnly": True,
                    "mode": "equivalence",
                    "form": form,
                    "form2": form2,
                    "isEquivalent": is_equiv,
                    "similarityScore": round(score, 4),
                }

            raise ChatToolValidationError("Unknown mode: {0}".format(mode))
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("phonetic_rules_apply failed: {0}".format(exc)) from exc

    # ------------------------------------------------------------------
    # Tier 2 — transcript reformat
    # ------------------------------------------------------------------

    def _tool_transcript_reformat(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Convert *_coarse.json alignment to CoarseTranscript schema. Dry-run returns parsed object."""
        import os as _os
        import tempfile

        input_path_str = str(args.get("inputPath") or "").strip()
        if not input_path_str:
            raise ChatToolValidationError("inputPath is required")

        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))
        speaker = str(args.get("speaker") or "").strip() or None
        source_wav = str(args.get("sourceWav") or "").strip() or None
        duration_sec_raw = args.get("durationSec")
        duration_sec = float(duration_sec_raw) if duration_sec_raw is not None else None

        input_path = self._resolve_readable_path(input_path_str)
        if not input_path.exists():
            raise ChatToolExecutionError("inputPath does not exist: {0}".format(input_path))

        try:
            from reformat_transcripts import reformat  # type: ignore[import]
        except Exception as exc:
            raise ChatToolExecutionError("reformat_transcripts is not importable: {0}".format(exc))

        try:
            if dry_run or not output_path_str:
                tmp_fd, tmp_str = tempfile.mkstemp(suffix=".json")
                _os.close(tmp_fd)
                tmp_path = Path(tmp_str)
                try:
                    reformat(str(input_path), speaker, source_wav, duration_sec, str(tmp_path))
                    result_data = json.loads(tmp_path.read_text(encoding="utf-8"))
                finally:
                    try:
                        _os.unlink(tmp_str)
                    except OSError:
                        pass
                return {"readOnly": True, "previewOnly": True, "result": result_data}

            out_path = self._resolve_project_path(output_path_str, allowed_roots=[self.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            reformat(str(input_path), speaker, source_wav, duration_sec, str(out_path))
            return {"success": True, "outputPath": str(out_path)}
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("transcript_reformat failed: {0}".format(exc)) from exc

    # ------------------------------------------------------------------
    # Tier 2 — peaks generate
    # ------------------------------------------------------------------

    def _tool_peaks_generate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate waveform peak data; resolves audio from annotation source_audio when only speaker given."""
        try:
            from peaks import (  # type: ignore[import]
                generate_peaks_for_audio,
                build_peaks_payload,
                write_peaks_json,
            )
        except Exception as exc:
            raise ChatToolExecutionError("peaks is not importable: {0}".format(exc))

        speaker_raw = str(args.get("speaker") or "").strip()
        audio_path_str = str(args.get("audioPath") or "").strip()
        output_path_str = str(args.get("outputPath") or "").strip()
        samples_per_pixel = int(args.get("samplesPerPixel") or 512)
        dry_run = bool(args.get("dryRun", False))

        if not speaker_raw and not audio_path_str:
            raise ChatToolValidationError("speaker or audioPath is required")

        if audio_path_str:
            audio_path = self._resolve_readable_path(audio_path_str)
        else:
            speaker = self._normalize_speaker(speaker_raw)
            ann_path = self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)
            if not ann_path.exists():
                raise ChatToolExecutionError("No annotation found for speaker: {0}".format(speaker))
            ann_data = json.loads(ann_path.read_text(encoding="utf-8"))
            source_audio = str(ann_data.get("source_audio") or "").strip()
            if not source_audio:
                raise ChatToolExecutionError(
                    "Speaker {0} annotation has no source_audio field".format(speaker)
                )
            audio_path = self._resolve_readable_path(source_audio)

        if not audio_path.exists():
            raise ChatToolExecutionError("Audio file not found: {0}".format(audio_path))

        try:
            sample_rate, peak_data, total_samples = generate_peaks_for_audio(
                audio_path, samples_per_pixel
            )
        except Exception as exc:
            raise ChatToolExecutionError("peaks generation failed: {0}".format(exc)) from exc

        payload = build_peaks_payload(sample_rate, samples_per_pixel, peak_data)

        if dry_run:
            return {
                "readOnly": True,
                "previewOnly": True,
                "sampleRate": sample_rate,
                "samplesPerPixel": samples_per_pixel,
                "totalSamples": total_samples,
                "peakCount": len(peak_data) // 2,
                "durationSec": round(total_samples / sample_rate, 3) if sample_rate else None,
            }

        if output_path_str:
            out_path = self._resolve_project_path(output_path_str, allowed_roots=[self.project_root])
        elif speaker_raw:
            speaker = self._normalize_speaker(speaker_raw)
            out_path = self.peaks_dir / "{0}.json".format(speaker)
        else:
            out_path = self.peaks_dir / "{0}.json".format(audio_path.stem)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_peaks_json(out_path, payload)
        return {
            "success": True,
            "outputPath": str(out_path),
            "sampleRate": sample_rate,
            "samplesPerPixel": samples_per_pixel,
            "totalSamples": total_samples,
            "peakCount": len(peak_data) // 2,
            "durationSec": round(total_samples / sample_rate, 3) if sample_rate else None,
        }

    # ------------------------------------------------------------------
    # Tier 3 — infrastructure / preflight
    # ------------------------------------------------------------------

    def _tool_source_index_validate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a speaker manifest entry or full manifest; optionally write source_index.json."""
        try:
            from source_index import validate_speaker, transform_speaker, build_source_index  # type: ignore[import]
        except Exception as exc:
            raise ChatToolExecutionError("source_index is not importable: {0}".format(exc))

        import io as _io

        def _call(fn: Any, *fn_args: Any) -> Tuple[bool, List[str], Any]:
            """Invoke a source_index function; capture stderr and catch SystemExit."""
            old_stderr = sys.stderr
            sys.stderr = _io.StringIO()
            result = None
            try:
                result = fn(*fn_args)
                errors: List[str] = []
                ok = True
            except SystemExit:
                raw = sys.stderr.getvalue()
                errors = [
                    line.replace("ERROR: ", "", 1).strip()
                    for line in raw.strip().splitlines()
                    if line.strip()
                ]
                ok = False
            finally:
                sys.stderr = old_stderr
            return ok, errors, result

        mode = str(args.get("mode") or "speaker").strip().lower()

        if mode == "speaker":
            speaker_id = str(args.get("speakerId") or "").strip()
            if not speaker_id:
                raise ChatToolValidationError("speakerId is required for mode=speaker")
            speaker_data = args.get("speakerData")
            if not isinstance(speaker_data, dict):
                raise ChatToolValidationError("speakerData must be an object for mode=speaker")

            valid, errors, _ = _call(validate_speaker, speaker_id, speaker_data)
            transformed = None
            if valid:
                ok2, errs2, transformed = _call(transform_speaker, speaker_id, speaker_data)
                if not ok2:
                    valid = False
                    errors = errs2

            return {
                "readOnly": True,
                "mode": "speaker",
                "speakerId": speaker_id,
                "valid": valid,
                "errors": errors,
                "transformed": transformed,
            }

        if mode == "full":
            manifest = args.get("manifest")
            if not isinstance(manifest, dict):
                raise ChatToolValidationError("manifest must be an object for mode=full")
            output_path_str = str(args.get("outputPath") or "").strip()

            valid, errors, source_index = _call(build_source_index, manifest)

            if not valid or source_index is None:
                return {"readOnly": True, "mode": "full", "valid": False, "errors": errors}

            speaker_count = len(source_index.get("speakers") or {})
            wav_count = sum(
                len(v.get("source_wavs") or [])
                for v in (source_index.get("speakers") or {}).values()
            )

            if output_path_str and not bool(args.get("dryRun", False)):
                out_path = self._resolve_project_path(output_path_str, allowed_roots=[self.project_root])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(source_index, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                return {
                    "success": True,
                    "mode": "full",
                    "valid": True,
                    "errors": [],
                    "speakerCount": speaker_count,
                    "wavCount": wav_count,
                    "outputPath": str(out_path),
                }

            return {
                "readOnly": True,
                "previewOnly": True,
                "mode": "full",
                "valid": True,
                "errors": [],
                "speakerCount": speaker_count,
                "wavCount": wav_count,
                "sourceIndex": source_index,
                "dryRun": bool(args.get("dryRun", False)),
            }

        raise ChatToolValidationError("mode must be 'speaker' or 'full'")

    def _tool_jobs_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_jobs_list(self, args)


    def _tool_job_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_job_status(self, args)


    def _tool_job_logs(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_job_logs(self, args)


    def _tool_jobs_list_active(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_jobs_list_active(self, args)


    def _tool_detect_timestamp_offset(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_detect_timestamp_offset(self, args)

    def _tool_detect_timestamp_offset_from_pair(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_detect_timestamp_offset_from_pair(self, args)

    def _tool_apply_timestamp_offset(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_apply_timestamp_offset(self, args)

    def _annotation_path_for_speaker(self, speaker: str) -> Optional[Path]:
        canonical = self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)
        if canonical.is_file():
            return canonical
        legacy = self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_LEGACY_FILENAME_SUFFIX)
        if legacy.is_file():
            return legacy
        return canonical

    def _tool_cognate_compute_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if cognate_compute_module is None:
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "unavailable",
                "message": "compare.cognate_compute module is unavailable",
            }

        threshold = _coerce_float(args.get("threshold"), 0.60)
        if threshold <= 0:
            raise ChatToolValidationError("threshold must be > 0")

        include_similarity = bool(args.get("includeSimilarity", True))
        max_concepts = int(args.get("maxConcepts", 40) or 40)

        speaker_values = args.get("speakers")
        speaker_filter: List[str] = []
        if isinstance(speaker_values, list):
            seen: Dict[str, bool] = {}
            for raw_speaker in speaker_values:
                speaker = _normalize_space(raw_speaker)
                if speaker and speaker not in seen:
                    seen[speaker] = True
                    speaker_filter.append(speaker)

        concept_values = args.get("conceptIds")
        concept_filter: List[str] = []
        if isinstance(concept_values, list):
            seen_concepts: Dict[str, bool] = {}
            for raw_concept in concept_values:
                concept_id = _normalize_concept_id(raw_concept)
                if concept_id and concept_id not in seen_concepts:
                    seen_concepts[concept_id] = True
                    concept_filter.append(concept_id)

        contact_override_raw = args.get("contactLanguages")
        contact_override: List[str] = []
        if isinstance(contact_override_raw, list):
            contact_override = [str(item).strip().lower() for item in contact_override_raw if str(item).strip()]

        contact_languages_from_config, refs_by_concept, form_selections_by_concept = cognate_compute_module.load_contact_language_data(
            self.sil_config_path
        )
        contact_languages = contact_override or contact_languages_from_config

        forms_by_concept, discovered_speakers = cognate_compute_module.load_annotations(self.annotations_dir)

        speaker_filter_set = set(speaker_filter)
        concept_filter_set = set(concept_filter)

        filtered_forms: Dict[str, List[Any]] = {}
        for raw_concept_id, records in forms_by_concept.items():
            concept_id = _normalize_concept_id(raw_concept_id)
            if not concept_id:
                continue
            if concept_filter_set and concept_id not in concept_filter_set:
                continue

            kept: List[Any] = []
            for record in records:
                speaker = _normalize_space(getattr(record, "speaker", ""))
                if speaker_filter_set and speaker not in speaker_filter_set:
                    continue
                kept.append(record)

            if kept:
                filtered_forms[concept_id] = kept

        if concept_filter:
            selected_concepts = [concept for concept in concept_filter if concept in filtered_forms]
        else:
            selected_concepts = sorted(filtered_forms.keys(), key=_concept_sort_key)

        truncated = len(selected_concepts) > max_concepts
        if truncated:
            selected_concepts = selected_concepts[:max_concepts]
            filtered_forms = {
                concept_id: filtered_forms.get(concept_id, [])
                for concept_id in selected_concepts
                if concept_id in filtered_forms
            }

        concept_specs = [
            cognate_compute_module.ConceptSpec(concept_id=concept_id, label="")
            for concept_id in selected_concepts
        ]

        cognate_sets = cognate_compute_module._compute_cognate_sets_with_lingpy(
            filtered_forms,
            concept_specs,
            threshold,
        )

        similarity: Dict[str, Any] = {}
        if include_similarity:
            similarity = cognate_compute_module.compute_similarity_scores(
                forms_by_concept=filtered_forms,
                concepts=concept_specs,
                contact_languages=contact_languages,
                refs_by_concept=refs_by_concept,
                form_selections_by_concept=form_selections_by_concept,
            )

        if speaker_filter:
            speakers_included = sorted([speaker for speaker in discovered_speakers if speaker in speaker_filter_set])
        else:
            speakers_included = sorted(discovered_speakers)

        preview_payload = {
            "computed_at": _utc_now_iso(),
            "config": {
                "contact_languages": list(contact_languages),
                "speakers_included": speakers_included,
                "concepts_included": selected_concepts,
                "lexstat_threshold": round(float(threshold), 3),
            },
            "cognate_sets": cognate_sets,
            "similarity": similarity,
            "borrowing_flags": {},
            "manual_overrides": {},
        }

        return {
            "readOnly": True,
            "previewOnly": True,
            "appliedToProjectState": False,
            "truncated": truncated,
            "maxConcepts": max_concepts,
            "summary": {
                "conceptCount": len(preview_payload["config"]["concepts_included"]),
                "speakerCount": len(preview_payload["config"]["speakers_included"]),
                "hasSimilarity": include_similarity,
            },
            "enrichmentsPreview": preview_payload,
            "note": "Preview only. parse-enrichments.json was not modified.",
        }

    def _segments_from_payload(self, payload: Sequence[Any]) -> List[Any]:
        if cross_speaker_match_module is None:
            return []

        segments: List[Any] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue

            start_sec = _coerce_float(item.get("start", item.get("startSec", 0.0)), 0.0)
            end_sec = _coerce_float(item.get("end", item.get("endSec", start_sec)), start_sec)
            if end_sec < start_sec:
                end_sec = start_sec

            text = _normalize_space(item.get("text"))
            ipa = _normalize_space(item.get("ipa"))
            ortho = _normalize_space(item.get("ortho", text))

            token_source = "{0} {1}".format(ipa, text)
            tokens = [token for token in TOKEN_RE.findall(token_source.lower()) if token]
            deduped_tokens: List[str] = []
            seen: Dict[str, bool] = {}
            for token in tokens:
                if token in seen:
                    continue
                seen[token] = True
                deduped_tokens.append(token)

            segments.append(
                cross_speaker_match_module.SegmentRecord(
                    index=index,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    text=text,
                    ipa=ipa,
                    ortho=ortho,
                    tokens=deduped_tokens,
                )
            )

        segments.sort(key=lambda row: (float(getattr(row, "start_sec", 0.0)), float(getattr(row, "end_sec", 0.0))))
        for new_index, segment in enumerate(segments):
            segment.index = new_index

        return segments

    def _tool_cross_speaker_match_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if cross_speaker_match_module is None:
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "unavailable",
                "message": "compare.cross_speaker_match module is unavailable",
            }

        top_k = int(args.get("topK", 5) or 5)
        min_confidence = _coerce_float(args.get("minConfidence"), 0.35)
        min_confidence = max(0.0, min(1.0, min_confidence))
        max_concepts = int(args.get("maxConcepts", 100) or 100)

        speaker = _normalize_space(args.get("speaker"))
        raw_segments: List[Any] = []
        source_label = ""

        stt_job_id = _normalize_space(args.get("sttJobId"))
        if stt_job_id:
            if self._get_job_snapshot is None:
                raise ChatToolExecutionError("Job snapshot callback is unavailable")

            snapshot = self._get_job_snapshot(stt_job_id)
            if snapshot is None:
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "status": "not_found",
                    "jobId": stt_job_id,
                    "message": "Unknown sttJobId",
                }

            if snapshot.get("type") != "stt":
                raise ChatToolValidationError("sttJobId does not point to an STT job")

            if snapshot.get("status") != "complete":
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "status": snapshot.get("status"),
                    "jobId": stt_job_id,
                    "progress": snapshot.get("progress"),
                    "message": "STT job is not complete yet",
                }

            result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
            if not speaker:
                speaker = _normalize_space(result.get("speaker") or snapshot.get("meta", {}).get("speaker"))

            segments_obj = result.get("segments")
            if isinstance(segments_obj, list):
                raw_segments = segments_obj
                source_label = "sttJob:{0}".format(stt_job_id)

        if not raw_segments:
            inline_segments = args.get("sttSegments")
            if isinstance(inline_segments, list):
                raw_segments = inline_segments
                source_label = "inline"

        if not raw_segments:
            raise ChatToolValidationError("Provide sttJobId or sttSegments")

        if not speaker:
            speaker = "unknown"

        segments = self._segments_from_payload(raw_segments)
        profiles = cross_speaker_match_module.load_concept_profiles(self.annotations_dir)
        rules = cross_speaker_match_module.load_rules_from_file(self.phonetic_rules_path)

        result_payload = cross_speaker_match_module.match_cross_speaker(
            speaker_id=speaker,
            segments=segments,
            profiles=profiles,
            rules=rules,
            top_k=max(1, int(top_k)),
            min_confidence=min_confidence,
        )

        matches = result_payload.get("matches") if isinstance(result_payload, dict) else []
        if not isinstance(matches, list):
            matches = []

        truncated = len(matches) > max_concepts
        if truncated and isinstance(result_payload, dict):
            result_payload["matches"] = matches[:max_concepts]

        return {
            "readOnly": True,
            "previewOnly": True,
            "appliedToProjectState": False,
            "source": source_label,
            "summary": {
                "segmentCount": len(segments),
                "profileCount": len(profiles),
                "matchConceptCount": len(result_payload.get("matches", [])) if isinstance(result_payload, dict) else 0,
                "truncated": truncated,
                "maxConcepts": max_concepts,
            },
            "matchPreview": result_payload,
            "note": "Preview only. No annotation/enrichment writes were performed.",
        }

    def _tool_spectrogram_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_spectrogram_preview(self, args)


    # ------------------------------------------------------------------
    # Contact lexeme / reference form lookup
    # ------------------------------------------------------------------

    def _tool_contact_lexeme_lookup(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch reference forms for contact languages via the provider registry.

        dryRun controls write behavior:
          dryRun=true  → call ProviderRegistry.fetch_all directly; no filesystem
                         writes; returns a preview of what would be merged.
          dryRun=false → call fetch_and_merge; writes results to
                         sil_contact_languages.json.
        """
        dry_run = bool(args.get("dryRun"))

        try:
            from compare.contact_lexeme_fetcher import fetch_and_merge
        except ImportError:
            return {
                "readOnly": True,
                "status": "unavailable",
                "message": (
                    "compare.contact_lexeme_fetcher module is unavailable. "
                    "Ensure the compare package is importable."
                ),
            }

        concepts_path = self.project_root / "concepts.csv"
        if not concepts_path.exists():
            return {
                "ok": False,
                "error": "concepts.csv not found in project root. Import concepts first.",
            }

        config_path = self.sil_config_path
        if not config_path.exists():
            # Create minimal config so fetch_and_merge can proceed
            import json as _json
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                _json.dump({}, f)

        # Parse arguments
        languages_raw = args.get("languages")
        if isinstance(languages_raw, list) and languages_raw:
            languages = [str(lc).strip().lower() for lc in languages_raw if str(lc).strip()]
        else:
            # Default: read configured languages from sil_contact_languages.json
            import json as _json
            try:
                with open(config_path, encoding="utf-8") as f:
                    sil_config = _json.load(f)
                languages = [k for k, v in sil_config.items() if isinstance(v, dict) and "name" in v]
            except Exception:
                languages = []
            if not languages:
                return {
                    "ok": False,
                    "error": (
                        "No languages specified and none configured in sil_contact_languages.json. "
                        "Provide languages parameter, e.g. [\"ar\", \"fa\"]."
                    ),
                }

        providers_raw = args.get("providers")
        providers = None
        if isinstance(providers_raw, list) and providers_raw:
            providers = [str(p).strip() for p in providers_raw if str(p).strip()]

        overwrite = bool(args.get("overwrite", False))
        max_concepts_raw = args.get("maxConcepts")
        max_concepts: Optional[int] = None
        if isinstance(max_concepts_raw, int) and max_concepts_raw > 0:
            max_concepts = max_concepts_raw

        # Concept filter
        concept_ids_raw = args.get("conceptIds")
        concept_filter = None
        if isinstance(concept_ids_raw, list) and concept_ids_raw:
            project_concepts = self._load_project_concepts()
            label_by_id = {
                str(concept.get("id") or "").strip(): str(concept.get("label") or "").strip()
                for concept in project_concepts
                if str(concept.get("id") or "").strip() and str(concept.get("label") or "").strip()
            }
            label_by_label = {
                str(concept.get("label") or "").strip().lower(): str(concept.get("label") or "").strip()
                for concept in project_concepts
                if str(concept.get("label") or "").strip()
            }
            concept_filter = []
            for raw_concept in concept_ids_raw:
                token = str(raw_concept).strip()
                if not token:
                    continue
                concept_label = label_by_id.get(token) or label_by_label.get(token.lower()) or token
                if concept_label not in concept_filter:
                    concept_filter.append(concept_label)

        if concept_filter is not None and max_concepts is not None:
            concept_filter = concept_filter[:max_concepts]

        # Load ai_config for provider credentials (grokipedia needs API keys)
        ai_config = _read_json_file(self.config_path, {})

        # If concept filter is given, write a temporary concepts CSV with only those
        import tempfile
        import csv as _csv
        if concept_filter:
            tmp_concepts = Path(tempfile.mktemp(suffix=".csv"))
            try:
                with open(tmp_concepts, "w", newline="", encoding="utf-8") as f:
                    writer = _csv.DictWriter(f, fieldnames=["id", "concept_en"])
                    writer.writeheader()
                    for i, c in enumerate(concept_filter, 1):
                        writer.writerow({"id": str(i), "concept_en": c})
                effective_concepts_path = tmp_concepts
            except Exception:
                effective_concepts_path = concepts_path
                concept_filter = None
        else:
            effective_concepts_path = concepts_path
            tmp_concepts = None

        try:
            if dry_run:
                # Preview path — load sil_config for language_meta, call the provider
                # registry directly, never touch the filesystem. Imported lazily here
                # (not at the top of the handler) because the provider registry pulls
                # in optional deps like pycldf/pylexibank that the write path doesn't
                # need — hoisting it would regress write-path availability when those
                # deps are missing.
                try:
                    from compare.providers.registry import ProviderRegistry, PROVIDER_PRIORITY
                except ImportError as exc:
                    return {
                        "ok": False,
                        "error": (
                            "Provider registry unavailable for dryRun preview: {0}. "
                            "Re-run with dryRun=false to fall back to fetch_and_merge."
                        ).format(exc),
                    }
                import csv as _csv_preview
                import json as _json_preview
                try:
                    with open(config_path, encoding="utf-8") as f:
                        sil_config_preview = _json_preview.load(f)
                except Exception:
                    sil_config_preview = {}
                language_meta = {k: v for k, v in sil_config_preview.items() if isinstance(v, dict)}

                with open(effective_concepts_path, newline="", encoding="utf-8") as f:
                    reader = _csv_preview.DictReader(f)
                    preview_concepts = [
                        (row.get("concept_en") or "").strip()
                        for row in reader
                        if (row.get("concept_en") or "").strip()
                    ]
                if max_concepts is not None:
                    preview_concepts = preview_concepts[:max_concepts]

                registry = ProviderRegistry(ai_config if isinstance(ai_config, dict) else {})
                fetched = registry.fetch_all(
                    concepts=preview_concepts,
                    language_codes=languages,
                    language_meta=language_meta,
                    priority_order=providers,
                )
                filled = {
                    lc: sum(1 for forms in fetched.get(lc, {}).values() if forms)
                    for lc in languages
                }

                sample_forms: Dict[str, Dict[str, List[str]]] = {}
                for lc in languages:
                    sample: Dict[str, List[str]] = {}
                    for concept_en, forms in list(fetched.get(lc, {}).items())[:5]:
                        if forms:
                            sample[concept_en] = forms
                    sample_forms[lc] = sample

                return {
                    "ok": True,
                    "dryRun": True,
                    "readOnly": True,
                    "previewOnly": True,
                    "languages": languages,
                    "filled": filled,
                    "totalConceptsFetched": sum(filled.values()),
                    "providersUsed": providers or list(PROVIDER_PRIORITY),
                    "sampleForms": sample_forms,
                    "message": (
                        "DRY RUN — fetched reference forms for {0} language(s); "
                        "no writes to sil_contact_languages.json. "
                        "Re-run with dryRun=false to persist these results."
                    ).format(len(languages)),
                }

            filled = fetch_and_merge(
                concepts_path=effective_concepts_path,
                config_path=config_path,
                language_codes=languages,
                providers=providers,
                overwrite=overwrite,
                ai_config=ai_config if isinstance(ai_config, dict) else {},
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": "Contact lexeme fetch failed: {0}".format(exc),
            }
        finally:
            if tmp_concepts and tmp_concepts.exists():
                try:
                    tmp_concepts.unlink()
                except Exception:
                    pass

        # Read back what was fetched to provide a summary
        import json as _json
        try:
            with open(config_path, encoding="utf-8") as f:
                updated_config = _json.load(f)
        except Exception:
            updated_config = {}

        sample_forms = {}
        for lc in languages:
            lang_data = updated_config.get(lc, {})
            concepts_data = lang_data.get("concepts", {})
            sample = {}
            for concept_en, forms in list(concepts_data.items())[:5]:
                sample[concept_en] = forms if isinstance(forms, list) else []
            sample_forms[lc] = sample

        return {
            "ok": True,
            "dryRun": False,
            "readOnly": False,
            "previewOnly": False,
            "languages": languages,
            "filled": filled,
            "totalConceptsFetched": sum(filled.values()),
            "providersUsed": providers or [
                "csv_override", "lingpy_wordlist", "pycldf", "pylexibank",
                "asjp", "cldf", "wikidata", "wiktionary", "grokipedia", "literature",
            ],
            "overwrite": overwrite,
            "configPath": str(config_path),
            "sampleForms": sample_forms,
            "message": (
                "Fetched reference forms for {0} language(s). "
                "Total concepts filled: {1}. "
                "Results written to sil_contact_languages.json. "
                "Use cognate_compute_preview with contactLanguages to compare."
            ).format(len(languages), sum(filled.values())),
        }

    # ------------------------------------------------------------------
    # Tag-import helpers
    # ------------------------------------------------------------------

    def _load_project_concepts(self) -> List[Dict[str, Any]]:
        """Load project concepts from concepts.csv. Returns list of {id, label} dicts."""
        concepts_path = self.project_root / "concepts.csv"
        if not concepts_path.exists():
            return []
        import csv as _csv
        concepts: List[Dict[str, Any]] = []
        try:
            with open(concepts_path, newline="", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    cid = str(row.get("id") or "").strip()
                    label = str(row.get("concept_en") or "").strip()
                    if cid and label:
                        concepts.append({"id": cid, "label": label})
        except Exception:
            pass
        return concepts

    def _display_readable_path(self, path: Path) -> str:
        """Return a project-relative path if possible, else the absolute path."""
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError:
            return str(path)

    def _tool_read_audio_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_read_audio_info(self, args)


    def _tool_read_csv_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_read_csv_preview(self, args)


    def _tool_read_text_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_read_text_preview(self, args)


    def _tool_import_tag_csv(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_import_tag_csv(self, args)

    def _tool_prepare_tag_import(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_prepare_tag_import(self, args)

    # ------------------------------------------------------------------
    # Speaker onboarding via chat
    # ------------------------------------------------------------------

    def _resolve_onboard_source(self, raw_path: str, *, must_be_audio: bool) -> Path:
        return _resolve_onboard_source(self, raw_path, must_be_audio=must_be_audio)

    def _resolve_processed_json_source(self, raw_path: str, field_name: str) -> Path:
        return _resolve_processed_json_source(self, raw_path, field_name)

    def _resolve_processed_csv_source(self, raw_path: str, field_name: str) -> Path:
        return _resolve_processed_csv_source(self, raw_path, field_name)

    def _extract_concepts_from_annotation(self, annotation_payload: Dict[str, Any]) -> List[Dict[str, str]]:
        return _extract_concepts_from_annotation(self, annotation_payload)

    def _write_concepts_csv(self, concepts: Sequence[Dict[str, str]]) -> int:
        return _write_concepts_csv(self, concepts)

    def _write_project_json_for_processed_import(
        self,
        speaker: str,
        project_id: str,
        language_code: str,
        concept_total: int,
    ) -> None:
        _write_project_json_for_processed_import(self, speaker, project_id, language_code, concept_total)

    def _write_source_index_for_processed_import(
        self,
        speaker: str,
        audio_rel: str,
        duration_sec: float,
        file_size_bytes: int,
        peaks_rel: Optional[str],
        transcript_csv_rel: Optional[str],
    ) -> None:
        _write_source_index_for_processed_import(
            self,
            speaker,
            audio_rel,
            duration_sec,
            file_size_bytes,
            peaks_rel,
            transcript_csv_rel,
        )

    def _tool_import_processed_speaker(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_import_processed_speaker(self, args)

    def _tool_onboard_speaker_import(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_onboard_speaker_import(self, args)

    # ------------------------------------------------------------------
    # Persistent chat memory (parse-memory.md)
    # ------------------------------------------------------------------

    def _tool_parse_memory_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_parse_memory_read(self, args)

    def _tool_parse_memory_upsert_section(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_parse_memory_upsert_section(self, args)


__all__ = [
    "ChatToolError",
    "ChatToolValidationError",
    "ChatToolExecutionError",
    "ChatToolSpec",
    "DEFAULT_MCP_TOOL_NAMES",
    "ParseChatTools",
]
