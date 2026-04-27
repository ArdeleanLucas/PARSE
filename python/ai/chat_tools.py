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
    "retranscribe_with_boundaries_start",
    "retranscribe_with_boundaries_status",
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
    tool_retranscribe_with_boundaries_start,
    tool_stt_start,
    tool_stt_word_level_start,
)
from ai.tools.artifact_tools import (
    ARTIFACT_TOOL_SPECS,
        peaks_generate as tool_peaks_generate,
    source_index_validate as tool_source_index_validate,
)
from ai.tools.comparative_tools import (
    COMPARATIVE_TOOL_SPECS,
    cognate_compute_preview as tool_cognate_compute_preview,
    cross_speaker_match_preview as tool_cross_speaker_match_preview,
    segments_from_payload,
)
from ai.tools.contact_lexeme_tools import (
    CONTACT_LEXEME_TOOL_SPECS,
    contact_lexeme_lookup as tool_contact_lexeme_lookup,
    load_project_concepts,
)
from ai.tools.enrichment_tools import (
    ENRICHMENT_TOOL_SPECS,
    enrichments_read as tool_enrichments_read,
    enrichments_write as tool_enrichments_write,
    lexeme_notes_read as tool_lexeme_notes_read,
    lexeme_notes_write as tool_lexeme_notes_write,
)
from ai.tools.export_tools import (
    EXPORT_TOOL_SPECS,
    build_nexus_text,
    export_annotations_csv as tool_export_annotations_csv,
    export_annotations_elan as tool_export_annotations_elan,
    export_annotations_textgrid as tool_export_annotations_textgrid,
    export_lingpy_tsv as tool_export_lingpy_tsv,
    export_nexus as tool_export_nexus,
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
    tool_retranscribe_with_boundaries_status,
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
from ai.tools.transform_tools import (
    TRANSFORM_TOOL_SPECS,
    phonetic_rules_apply as tool_phonetic_rules_apply,
    transcript_reformat as tool_transcript_reformat,
)

REGISTRY: Dict[str, ChatToolSpec] = {
    **PROJECT_READ_TOOL_SPECS,
    **PREVIEW_TOOL_SPECS,
    **JOB_STATUS_TOOL_SPECS,
    **TAG_IMPORT_TOOL_SPECS,
    **OFFSET_DETECTION_TOOL_SPECS,
    **OFFSET_APPLY_TOOL_SPECS,
    **ACOUSTIC_STARTER_TOOL_SPECS,
    **PIPELINE_ORCHESTRATION_TOOL_SPECS,
    **SPEAKER_IMPORT_TOOL_SPECS,
    **MEMORY_TOOL_SPECS,
    **COMPARATIVE_TOOL_SPECS,
    **CONTACT_LEXEME_TOOL_SPECS,
    **ENRICHMENT_TOOL_SPECS,
    **EXPORT_TOOL_SPECS,
    **TRANSFORM_TOOL_SPECS,
    **ARTIFACT_TOOL_SPECS,
}

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
            **PIPELINE_ORCHESTRATION_TOOL_SPECS,
            **SPEAKER_IMPORT_TOOL_SPECS,
            **MEMORY_TOOL_SPECS,
            **COMPARATIVE_TOOL_SPECS,
            **CONTACT_LEXEME_TOOL_SPECS,
            **ENRICHMENT_TOOL_SPECS,
            **EXPORT_TOOL_SPECS,
            **TRANSFORM_TOOL_SPECS,
            **ARTIFACT_TOOL_SPECS,
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
            "retranscribe_with_boundaries_start",
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

        if tool_name == "retranscribe_with_boundaries_start":
            return (
                _project_loaded_condition(),
                _tool_condition(
                    "ortho_words_intervals_present",
                    "The requested speaker must already have non-empty tiers.ortho_words intervals — boundary-constrained STT slices the audio at those windows and has nothing to do without them.",
                    kind=TOOL_CONDITION_KIND_PROJECT_STATE,
                ),
            )

        if tool_name in {
            "stt_status",
            "stt_word_level_status",
            "forced_align_status",
            "ipa_transcribe_acoustic_status",
            "retranscribe_with_boundaries_status",
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
            "retranscribe_with_boundaries_start": "boundary_constrained_stt_job_started",
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
            "retranscribe_with_boundaries_status",
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

    def _tool_retranscribe_with_boundaries_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_retranscribe_with_boundaries_start(self, args)

    def _tool_retranscribe_with_boundaries_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_retranscribe_with_boundaries_status(self, args)

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

    def _tool_audio_normalize_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_audio_normalize_start(self, args)

    def _tool_audio_normalize_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_audio_normalize_status(self, args)

    def _tool_enrichments_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_enrichments_read(self, args)

    def _tool_enrichments_write(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_enrichments_write(self, args)

    def _tool_lexeme_notes_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_lexeme_notes_read(self, args)

    def _tool_lexeme_notes_write(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_lexeme_notes_write(self, args)

    def _tool_export_annotations_csv(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_export_annotations_csv(self, args)

    def _tool_export_lingpy_tsv(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_export_lingpy_tsv(self, args)

    def _tool_export_nexus(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_export_nexus(self, args)

    def _build_nexus_text(self) -> str:
        return build_nexus_text(self)

    def _tool_export_annotations_elan(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_export_annotations_elan(self, args)

    def _tool_export_annotations_textgrid(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_export_annotations_textgrid(self, args)

    def _tool_phonetic_rules_apply(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_phonetic_rules_apply(self, args)

    def _tool_transcript_reformat(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_transcript_reformat(self, args)

    def _tool_peaks_generate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_peaks_generate(self, args)

    def _tool_source_index_validate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_source_index_validate(self, args)

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

    def _tool_cognate_compute_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_cognate_compute_preview(self, args)

    def _segments_from_payload(self, payload: Sequence[Any]) -> List[Any]:
        return segments_from_payload(self, payload)

    def _tool_cross_speaker_match_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_cross_speaker_match_preview(self, args)

    def _tool_spectrogram_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_spectrogram_preview(self, args)

    def _tool_contact_lexeme_lookup(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return tool_contact_lexeme_lookup(self, args)

    def _load_project_concepts(self) -> List[Dict[str, Any]]:
        return load_project_concepts(self)

    def _display_readable_path(self, path: Path) -> str:
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
    "REGISTRY",
    "ParseChatTools",
]
