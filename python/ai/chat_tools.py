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


class ParseChatTools:
    """Strict read-only tool allowlist for PARSE chat."""

    def __init__(
        self,
        project_root: Path,
        config_path: Optional[Path] = None,
        docs_root: Optional[Path] = None,
        start_stt_job: Optional[Callable[[str, str, Optional[str]], str]] = None,
        get_job_snapshot: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
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
        self._onboard_speaker = onboard_speaker
        self._start_compute_job = start_compute_job
        self._pipeline_state = pipeline_state
        self._start_normalize_job = start_normalize_job
        self._list_active_jobs = list_active_jobs

        self._tool_specs: Dict[str, ChatToolSpec] = {
            "project_context_read": ChatToolSpec(
                name="project_context_read",
                description=(
                    "Read high-level PARSE project context (project metadata, source index summary, "
                    "annotation inventory, and enrichment summary). Read-only."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "include": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "string",
                                "enum": [
                                    "project",
                                    "source_index",
                                    "annotation_inventory",
                                    "enrichments_summary",
                                    "ai_config",
                                    "constraints",
                                ],
                            },
                        },
                        "maxSpeakers": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                },
            ),
            "annotation_read": ChatToolSpec(
                name="annotation_read",
                description=(
                    "Read one speaker annotation JSON safely from annotations/<speaker>.parse.json "
                    "with optional concept filtering. Read-only."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "conceptIds": {
                            "type": "array",
                            "maxItems": 250,
                            "items": {"type": "string", "minLength": 1, "maxLength": 64},
                        },
                        "includeTiers": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "string",
                                "enum": ["ipa", "ortho", "concept", "speaker"],
                            },
                        },
                        "maxIntervals": {"type": "integer", "minimum": 1, "maximum": 5000},
                    },
                },
            ),
            "detect_timestamp_offset": ChatToolSpec(
                name="detect_timestamp_offset",
                description=(
                    "Detect a constant timestamp offset between a speaker's annotation "
                    "intervals and STT segments for the same audio. Uses monotonic "
                    "anchor-segment alignment (chosen matches must visit anchors and "
                    "segments in increasing time order) so false matches to similar-"
                    "sounding words elsewhere in the recording can't elect the wrong "
                    "direction. Anchors are sampled across the timeline by quantile "
                    "by default — pass anchorDistribution='earliest' to use the legacy "
                    "first-N selection. Read-only; returns offsetSec, confidence, "
                    "spreadSec, direction, warnings, and the matched anchor↔segment "
                    "pairs so callers can sanity-check before applying."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "sttJobId": {"type": "string", "minLength": 1, "maxLength": 128},
                        "nAnchors": {"type": "integer", "minimum": 2, "maximum": 50},
                        "bucketSec": {"type": "number", "minimum": 0.1, "maximum": 30.0},
                        "minMatchScore": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "anchorDistribution": {"type": "string", "enum": ["quantile", "earliest"]},
                    },
                },
            ),
            "detect_timestamp_offset_from_pair": ChatToolSpec(
                name="detect_timestamp_offset_from_pair",
                description=(
                    "Compute a timestamp offset from one or more trusted "
                    "(csvTime, audioTime) pairs — no STT, no statistics-on-text, "
                    "no false matches. Use this when the user (or you) already "
                    "knows where one or more lexemes actually are in the audio.\n\n"
                    "Two argument shapes are accepted:\n"
                    " - Single pair: pass speaker + audioTimeSec + (csvTimeSec OR conceptId)\n"
                    " - Multiple pairs: pass speaker + pairs=[{...}, {...}]. With "
                    "two or more pairs the offset is the median of per-pair offsets, "
                    "and the response carries the MAD spread plus warnings if any "
                    "pair disagrees with the consensus by more than ~2 s.\n\n"
                    "The response shape is the same as detect_timestamp_offset, so "
                    "the offsetSec can be passed straight into apply_timestamp_offset."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "audioTimeSec": {"type": "number", "minimum": 0.0},
                        "csvTimeSec": {"type": "number", "minimum": 0.0},
                        "conceptId": {"type": "string", "minLength": 1, "maxLength": 128},
                        "pairs": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 32,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["audioTimeSec"],
                                "properties": {
                                    "audioTimeSec": {"type": "number", "minimum": 0.0},
                                    "csvTimeSec": {"type": "number", "minimum": 0.0},
                                    "conceptId": {"type": "string", "minLength": 1, "maxLength": 128},
                                },
                            },
                        },
                    },
                },
            ),
            "apply_timestamp_offset": ChatToolSpec(
                name="apply_timestamp_offset",
                description=(
                    "Shift every annotation interval (start and end) by offsetSec for the "
                    "given speaker. Mutates annotations/<speaker>.parse.json. Use dryRun=true "
                    "first to preview the shift, then dryRun=false to write."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "offsetSec", "dryRun"],
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID whose annotation intervals will be shifted.",
                        },
                        "offsetSec": {
                            "type": "number",
                            "description": "Seconds to add to every interval start/end; negative values pull timestamps earlier.",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, preview the timestamp shift without writing annotations/<speaker>.parse.json.",
                        },
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "speaker_annotation_exists",
                        "The target speaker must already have an annotation file under annotations/.",
                        kind="file_presence",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "annotation_timestamps_shifted",
                        "When dryRun=false, the speaker's annotation intervals are rewritten with the requested offset.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "stt_start": ChatToolSpec(
                name="stt_start",
                description=(
                    "Start a bounded STT background job for a project audio file. "
                    "Returns a jobId for polling with stt_status."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "sourceWav"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "sourceWav": {"type": "string", "minLength": 1, "maxLength": 512},
                        "language": {"type": "string", "minLength": 1, "maxLength": 32},
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, validate inputs and preview the STT job without launching it.",
                        },
                    },
                },
            ),
            "stt_status": ChatToolSpec(
                name="stt_status",
                description="Read status/progress of an existing STT job.",
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["jobId"],
                    "properties": {
                        "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                        "includeSegments": {"type": "boolean"},
                        "maxSegments": {"type": "integer", "minimum": 1, "maximum": 300},
                    },
                },
            ),
            # ── Tier 1 acoustic alignment: word-level STT ──────────────
            "stt_word_level_start": ChatToolSpec(
                name="stt_word_level_start",
                description=(
                    "Start a word-level STT job (Tier 1 acoustic alignment). "
                    "Segments are returned with a nested words[] array of "
                    "(word, start, end, prob) spans from faster-whisper's "
                    "word_timestamps=True output. Mirrors stt_start but the "
                    "name is explicit about Tier 1 semantics so agents can "
                    "distinguish word-level jobs from plain sentence-level "
                    "STT. Returns a jobId for polling with stt_word_level_status."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "sourceWav"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "sourceWav": {"type": "string", "minLength": 1, "maxLength": 512},
                        "language": {"type": "string", "minLength": 1, "maxLength": 32},
                        "dryRun": {"type": "boolean"},
                    },
                },
            ),
            "stt_word_level_status": ChatToolSpec(
                name="stt_word_level_status",
                description=(
                    "Read status of a Tier 1 word-level STT job. When "
                    "includeSegments=true the returned segments include the "
                    "nested words[] payload produced by word_timestamps=True."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["jobId"],
                    "properties": {
                        "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                        "includeSegments": {"type": "boolean"},
                        "includeWords": {"type": "boolean"},
                        "maxSegments": {"type": "integer", "minimum": 1, "maximum": 300},
                    },
                },
            ),
            # ── Tier 2 acoustic alignment: wav2vec2 forced alignment ──
            "forced_align_start": ChatToolSpec(
                name="forced_align_start",
                description=(
                    "Start a Tier 2 forced-alignment job for a speaker. Runs "
                    "torchaudio.functional.forced_align against "
                    "facebook/wav2vec2-xlsr-53-espeak-cv-ft on each word window "
                    "from the speaker's Tier 1 STT output, producing tight per-"
                    "word (and optional per-phoneme) boundaries. G2P is used "
                    "only internally to build CTC targets and is discarded; no "
                    "G2P output is persisted. Returns a jobId for polling with "
                    "forced_align_status."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "overwrite": {
                            "type": "boolean",
                            "description": "When true, replaces an existing aligned artifact (default: false).",
                        },
                        "language": {
                            "type": "string",
                            "minLength": 2,
                            "maxLength": 8,
                            "description": "espeak-ng language code for the internal G2P step (default: ku)",
                        },
                        "padMs": {"type": "integer", "minimum": 0, "maximum": 500},
                        "emitPhonemes": {"type": "boolean"},
                        "dryRun": {"type": "boolean"},
                    },
                },
            ),
            "forced_align_status": ChatToolSpec(
                name="forced_align_status",
                description="Read status/progress of an existing Tier 2 forced-alignment job.",
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["jobId"],
                    "properties": {
                        "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                    },
                },
            ),
            # ── Tier 3 acoustic alignment: wav2vec2-only IPA ──────────
            "ipa_transcribe_acoustic_start": ChatToolSpec(
                name="ipa_transcribe_acoustic_start",
                description=(
                    "Start a Tier 3 acoustic IPA job. Runs "
                    "facebook/wav2vec2-xlsr-53-espeak-cv-ft CTC on each ortho "
                    "interval's audio window and writes the decoded phoneme "
                    "string into the speaker's IPA tier. wav2vec2 is the ONLY "
                    "IPA engine — there are no text-based fallbacks. Equivalent "
                    "to the ipa_only compute job exposed in the UI under "
                    "Actions → Run IPA transcription. Returns a jobId for "
                    "polling with ipa_transcribe_acoustic_status."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "overwrite": {
                            "type": "boolean",
                            "description": "When true, replaces existing non-empty IPA cells (default: false).",
                        },
                        "dryRun": {"type": "boolean"},
                    },
                },
            ),
            "ipa_transcribe_acoustic_status": ChatToolSpec(
                name="ipa_transcribe_acoustic_status",
                description="Read status/progress of an existing Tier 3 acoustic IPA job.",
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["jobId"],
                    "properties": {
                        "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                    },
                },
            ),
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
            "spectrogram_preview": ChatToolSpec(
                name="spectrogram_preview",
                description=(
                    "Read-only placeholder/backend hook for spectrogram preview requests. "
                    "Validates bounds and reports capability status."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["sourceWav", "startSec", "endSec"],
                    "properties": {
                        "sourceWav": {"type": "string", "minLength": 1, "maxLength": 512},
                        "startSec": {"type": "number", "minimum": 0.0},
                        "endSec": {"type": "number", "minimum": 0.0},
                        "windowSize": {
                            "type": "integer",
                            "enum": [256, 512, 1024, 2048, 4096],
                        },
                    },
                },
            ),
            "read_audio_info": ChatToolSpec(
                name="read_audio_info",
                description=(
                    "Read metadata for a WAV file in the project audio directory: duration, "
                    "sample rate, channels, sample width, frame count, and file size. "
                    "Read-only; does not return audio samples."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["sourceWav"],
                    "properties": {
                        "sourceWav": {"type": "string", "minLength": 1, "maxLength": 512},
                    },
                },
            ),
            "read_csv_preview": ChatToolSpec(
                name="read_csv_preview",
                description=(
                    "Read first N rows of any CSV file and return column names, delimiter, "
                    "total row count, and a sample. Defaults to concepts.csv in project root "
                    "if no path given. Path must stay within the project root. Read-only."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "csvPath": {"type": "string", "maxLength": 512},
                        "maxRows": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
                    },
                },
            ),
            "read_text_preview": ChatToolSpec(
                name="read_text_preview",
                description=(
                    "Read a Markdown/text file preview from workspace or docs root. "
                    "Allowed extensions: .md, .markdown, .txt, .rst. Read-only."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string", "minLength": 1, "maxLength": 1024},
                        "startLine": {"type": "integer", "minimum": 1, "maximum": 200000, "default": 1},
                        "maxLines": {"type": "integer", "minimum": 1, "maximum": 400, "default": 120},
                        "maxChars": {"type": "integer", "minimum": 200, "maximum": 50000, "default": 12000},
                    },
                },
            ),
            "import_tag_csv": ChatToolSpec(
                name="import_tag_csv",
                description=(
                    "Import a CSV file as a custom tag list. Matches CSV rows to project concept IDs "
                    "by label (case-insensitive), numeric ID, or fuzzy match (edit distance <= 1). "
                    "When dryRun=true returns a preview of matched/unmatched rows and asks for tag name. "
                    "When dryRun=false and tagName is provided, creates the tag and writes parse-tags.json. "
                    "Always use dryRun=true first, then dryRun=false after explicit user confirmation."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["dryRun"],
                    "properties": {
                        "csvPath": {"type": "string", "maxLength": 512},
                        "tagName": {"type": "string", "minLength": 1, "maxLength": 100},
                        "color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                        "labelColumn": {"type": "string", "maxLength": 64},
                        "dryRun": {"type": "boolean"},
                    },
                },
            ),
            "prepare_tag_import": ChatToolSpec(
                name="prepare_tag_import",
                description=(
                    "Create or update a tag with a list of concept IDs and write to parse-tags.json. "
                    "Always use dryRun=true first to preview, then dryRun=false after user confirms."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["tagName", "conceptIds", "dryRun"],
                    "properties": {
                        "tagName": {"type": "string", "minLength": 1, "maxLength": 100},
                        "color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                        "conceptIds": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 500,
                            "items": {"type": "string", "minLength": 1, "maxLength": 64},
                        },
                        "dryRun": {"type": "boolean"},
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
            "onboard_speaker_import": ChatToolSpec(
                name="onboard_speaker_import",
                description=(
                    "Import a speaker's audio source from on-disk paths (and optional transcription CSV). "
                    "Copies files into audio/original/<speaker>/, scaffolds an annotation record on the "
                    "first import, and appends the source to source_index.json. sourceWav/sourceCsv may "
                    "be absolute paths under PARSE_EXTERNAL_READ_ROOTS (set to '*' for no sandbox) or "
                    "paths under the project audio/ directory. "
                    "Multi-source speakers: call this tool once per audio source. The first import "
                    "defaults to is_primary=true; subsequent imports default to is_primary=false. "
                    "When a speaker already has registered sources, the response flags "
                    "`virtualTimelineRequired=true` — PARSE does not yet auto-align multiple WAVs "
                    "across a shared virtual timeline, so annotation spanning them must be coordinated "
                    "manually or deferred. "
                    "Gated by dryRun: call dryRun=true first to preview planned copies/registrations, "
                    "then dryRun=false after the user confirms."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "sourceWav", "dryRun"],
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID to create or extend in the current project.",
                        },
                        "sourceWav": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1024,
                            "description": "Absolute or project-relative path to the source audio file to copy into the workspace.",
                        },
                        "sourceCsv": {
                            "type": "string",
                            "maxLength": 1024,
                            "description": "Optional transcript CSV to store alongside the imported source WAV.",
                        },
                        "isPrimary": {
                            "type": "boolean",
                            "description": "Flag this WAV as the speaker's primary source. Defaults to true when the speaker has no existing sources.",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, preview only — no file copies or source_index.json writes.",
                        },
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "source_audio_readable",
                        "The sourceWav path must resolve to a readable audio file within the allowed import roots.",
                        kind="file_presence",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "speaker_source_registered",
                        "When dryRun=false, the source audio is copied into the workspace and source_index.json / project metadata are updated.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "import_processed_speaker": ChatToolSpec(
                name="import_processed_speaker",
                description=(
                    "Import a speaker from existing processed artifacts when lexemes are already timestamped to a WAV. "
                    "Copies a working WAV plus annotation JSON (and optional peaks JSON / legacy transcript CSV) into the "
                    "PARSE workspace, writes concepts.csv, updates project.json and source_index.json, and preserves the "
                    "annotation's timestamp alignment to the working WAV. Call dryRun=true first, then dryRun=false "
                    "after confirmation."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "workingWav", "annotationJson", "dryRun"],
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID to import into the PARSE workspace.",
                        },
                        "workingWav": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1024,
                            "description": "Path to the processed/working WAV whose timestamps already align with the annotation JSON.",
                        },
                        "annotationJson": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1024,
                            "description": "Path to the timestamp-bearing annotation JSON to copy into annotations/.",
                        },
                        "peaksJson": {
                            "type": "string",
                            "maxLength": 1024,
                            "description": "Optional precomputed peaks JSON aligned to the working WAV.",
                        },
                        "transcriptCsv": {
                            "type": "string",
                            "maxLength": 1024,
                            "description": "Optional legacy transcript CSV to preserve in the imported workspace.",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, preview the file-copy and metadata-write plan without mutating the workspace.",
                        },
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "processed_artifacts_readable",
                        "The working WAV and annotation JSON must both exist and be readable.",
                        kind="file_presence",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "processed_speaker_imported",
                        "When dryRun=false, the processed speaker artifacts are copied into the workspace and project/source-index metadata are updated.",
                        kind="filesystem_write",
                    ),
                ),
            ),
            "parse_memory_read": ChatToolSpec(
                name="parse_memory_read",
                description=(
                    "Read PARSE's persistent chat memory markdown (parse-memory.md). This is "
                    "where speaker provenance, file origins, user preferences, and session "
                    "context are recorded. Read-only. Returns the full document bounded by "
                    "maxBytes, or a specific `## Section` when section is provided."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "section": {
                            "type": "string",
                            "maxLength": 200,
                            "description": "Heading text (without leading `##`). If given, only that section is returned.",
                        },
                        "maxBytes": {
                            "type": "integer",
                            "minimum": 512,
                            "maximum": MEMORY_MAX_BYTES,
                            "description": "Cap on bytes returned. Defaults to full file (up to {0} bytes).".format(MEMORY_MAX_BYTES),
                        },
                    },
                },
            ),
            "parse_memory_upsert_section": ChatToolSpec(
                name="parse_memory_upsert_section",
                description=(
                    "Create or replace a `## Section` block in parse-memory.md. Use for "
                    "persisting user preferences, speaker notes, onboarding decisions, and "
                    "file provenance that should survive across chat turns. Gated by dryRun — "
                    "call dryRun=true first to preview the resulting block, then dryRun=false "
                    "after the user confirms. The existing block under the same heading is "
                    "overwritten; other sections are left untouched."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["section", "body", "dryRun"],
                    "properties": {
                        "section": {"type": "string", "minLength": 1, "maxLength": 200},
                        "body": {"type": "string", "minLength": 1, "maxLength": 16000},
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, return the rewritten file preview without writing.",
                        },
                    },
                },
            ),
            "speakers_list": ChatToolSpec(
                name="speakers_list",
                description=(
                    "List every speaker with an annotation file under ``annotations/``. "
                    "Read-only. Use as the starting point for a batch pipeline run — pair "
                    "with ``pipeline_state_batch`` to see which speakers are ready to "
                    "process. Filters out non-annotation entries (e.g. a ``backups/`` "
                    "directory) so the list is directly usable as input to ``pipeline_run``."
                ),
                parameters={"type": "object", "additionalProperties": False, "properties": {}},
            ),
            "pipeline_state_read": ChatToolSpec(
                name="pipeline_state_read",
                description=(
                    "Preflight one speaker. Read-only. Returns per-step "
                    "``{done, intervals|segments, can_run, reason, "
                    "coverage_start_sec, coverage_end_sec, "
                    "coverage_fraction, full_coverage}`` plus top-level "
                    "``duration_sec``. "
                    "IMPORTANT: ``done`` only means 'the tier has ≥1 "
                    "non-empty interval'. That is NOT the same as 'the "
                    "entire WAV was processed' — a tier whose 128 "
                    "intervals only cover the first 30 seconds of a "
                    "6-minute recording is still ``done: true`` but "
                    "``full_coverage: false``. Gate re-run decisions on "
                    "``full_coverage``, not ``done``."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                    },
                },
            ),
            "pipeline_state_batch": ChatToolSpec(
                name="pipeline_state_batch",
                description=(
                    "Preflight multiple speakers at once. Read-only. "
                    "With no arguments, probes every speaker from "
                    "``speakers_list``. Supply ``speakers`` to "
                    "restrict. Each row carries the same per-step "
                    "fields as ``pipeline_state_read``, including "
                    "``full_coverage`` — the actual 'was the entire "
                    "WAV processed?' signal (as distinct from "
                    "``done``, which only checks for ≥1 non-empty "
                    "interval). Top-level summary counts "
                    "``blockedSpeakers`` (any step can_run=false) and "
                    "``partialCoverageSpeakers`` (any STT/ORTH/IPA "
                    "step has full_coverage=false). Ideal for "
                    "answering 'can I kick off a full batch and walk "
                    "away?' without surprises."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speakers": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1, "maxLength": 200},
                            "maxItems": 200,
                            "description": "Optional speaker-id subset. Omit for every annotated speaker.",
                        },
                    },
                },
            ),
            "pipeline_run": ChatToolSpec(
                name="pipeline_run",
                description=(
                    "Kick off a transcription pipeline for ONE speaker — the same "
                    "``full_pipeline`` compute the UI uses. Supports any subset of "
                    "``normalize / stt / ortho / ipa`` in canonical order. Setting "
                    "``steps: ['ortho']`` with ``overwrites: {ortho: true}`` runs the "
                    "razhan model full-file against this speaker's working WAV and "
                    "overwrites the ortho tier. Returns a jobId; poll via "
                    "``compute_status`` (compute_type=\"full_pipeline\") until "
                    "``status=complete``. Steps run step-resilient: a failing STT will "
                    "not abort ORTH/IPA for the same speaker."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker", "steps"],
                    "properties": {
                        "speaker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Speaker ID whose pipeline should run.",
                        },
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["normalize", "stt", "ortho", "ipa"],
                            },
                            "minItems": 1,
                            "maxItems": 4,
                            "description": "Ordered pipeline subset to execute for this speaker.",
                        },
                        "overwrites": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "normalize": {"type": "boolean"},
                                "stt": {"type": "boolean"},
                                "ortho": {"type": "boolean"},
                                "ipa": {"type": "boolean"},
                            },
                            "description": (
                                "Per-step overwrite flags. Steps flagged false will "
                                "skip when their tier / cache is already populated; "
                                "flagged true will replace the existing data."
                            ),
                        },
                        "language": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 32,
                            "description": (
                                "Optional language override forwarded to STT + ORTH "
                                "(razhan). Empty / omitted = auto-detect for STT, "
                                "``sd`` for ORTH (razhan's fine-tuning target)."
                            ),
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, preview the planned compute payload without starting a background job.",
                        },
                    },
                },
                mutability="mutating",
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "speaker_ready_for_pipeline",
                        "The target speaker must exist in the current project and have the files needed for the requested steps.",
                        kind="project_state",
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "pipeline_job_started",
                        "When dryRun=false, a full_pipeline background job is created and can be polled via compute_status.",
                        kind="job_state",
                    ),
                ),
            ),
            "compute_status": ChatToolSpec(
                name="compute_status",
                description=(
                    "Poll any compute job (full_pipeline, ortho, ipa, contact-lexemes, …) "
                    "by jobId. Read-only. Returns the job snapshot with status, progress, "
                    "message, and — for completed jobs — the full ``result`` payload. "
                    "For pipeline jobs the result includes per-step status and summary "
                    "counts so the agent can reason about success/skip/error cells."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["jobId"],
                    "properties": {
                        "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                        "computeType": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                            "description": (
                                "Optional expected compute type (e.g. "
                                "\"full_pipeline\"). If provided, the tool validates "
                                "the job's type matches before returning the snapshot."
                            ),
                        },
                    },
                },
            ),
            "audio_normalize_start": ChatToolSpec(
                name="audio_normalize_start",
                description=(
                    "Start an audio normalization job for a speaker (two-pass ffmpeg loudnorm: "
                    "mono, 44.1 kHz, -16 LUFS). Returns a jobId; poll with audio_normalize_status. "
                    "sourceWav is optional — defaults to the speaker's primary source audio."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker"],
                    "properties": {
                        "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                        "sourceWav": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "description": "Project-relative or absolute path to source WAV. Omit to use primary source.",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "If true, preview the normalize job without launching ffmpeg.",
                        },
                    },
                },
            ),
            "audio_normalize_status": ChatToolSpec(
                name="audio_normalize_status",
                description=(
                    "Poll status of a normalize job started with audio_normalize_start. "
                    "Returns status, progress, error, and result when complete."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["jobId"],
                    "properties": {
                        "jobId": {"type": "string", "minLength": 1, "maxLength": 128},
                    },
                },
            ),
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
            "jobs_list_active": ChatToolSpec(
                name="jobs_list_active",
                description=(
                    "List all currently-running jobs in the PARSE job registry "
                    "(STT, normalize, compute, onboard, etc.). "
                    "Returns type, status, progress, speaker, and message for each active job. "
                    "Useful for recovering jobIds after a session restart."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {},
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
        if tool_name in {"project_context_read", "speakers_list", "jobs_list_active"}:
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
        include_values = args.get("include")
        if not isinstance(include_values, list) or not include_values:
            include = [
                "project",
                "source_index",
                "annotation_inventory",
                "enrichments_summary",
                "constraints",
            ]
        else:
            include = [str(value) for value in include_values]

        max_speakers = int(args.get("maxSpeakers", 50) or 50)

        out: Dict[str, Any] = {
            "readOnly": True,
            "previewOnly": True,
            "fetchedAt": _utc_now_iso(),
        }

        if "project" in include:
            out["project"] = _read_json_file(self.project_json_path, {})

        if "source_index" in include:
            source_index = _read_json_file(self.source_index_path, {})
            speakers_block = source_index.get("speakers") if isinstance(source_index, dict) else {}
            speaker_summary: Dict[str, Any] = {}
            if isinstance(speakers_block, dict):
                speaker_names = sorted(speakers_block.keys())
                truncated = len(speaker_names) > max_speakers
                for speaker in speaker_names[:max_speakers]:
                    payload = speakers_block.get(speaker)
                    if not isinstance(payload, dict):
                        continue

                    source_wavs = payload.get("source_wavs")
                    if not isinstance(source_wavs, list):
                        source_wavs = []

                    primary_filename = ""
                    for source_entry in source_wavs:
                        if isinstance(source_entry, dict) and source_entry.get("is_primary"):
                            primary_filename = _normalize_space(source_entry.get("filename"))
                            break
                    if not primary_filename and source_wavs:
                        first = source_wavs[0]
                        if isinstance(first, dict):
                            primary_filename = _normalize_space(first.get("filename"))

                    speaker_summary[speaker] = {
                        "sourceCount": len(source_wavs),
                        "primarySource": primary_filename,
                        "hasCsv": bool(payload.get("has_csv")),
                    }

                out["source_index"] = {
                    "speakerCount": len(speaker_names),
                    "speakers": speaker_summary,
                    "truncated": truncated,
                    "maxSpeakers": max_speakers,
                }
            else:
                out["source_index"] = {
                    "speakerCount": 0,
                    "speakers": {},
                    "truncated": False,
                    "maxSpeakers": max_speakers,
                }

        if "annotation_inventory" in include:
            inventory = {
                "directory": str(self.annotations_dir),
                "exists": self.annotations_dir.exists(),
                "fileCount": 0,
                "sample": [],
            }
            if self.annotations_dir.exists() and self.annotations_dir.is_dir():
                files = sorted([path.name for path in self.annotations_dir.glob("*.json")])
                inventory["fileCount"] = len(files)
                inventory["sample"] = files[:20]
            out["annotation_inventory"] = inventory

        if "enrichments_summary" in include:
            enrichments = _read_json_file(self.enrichments_path, {})
            config = enrichments.get("config") if isinstance(enrichments, dict) else {}
            cognate_sets = enrichments.get("cognate_sets") if isinstance(enrichments, dict) else {}
            similarity = enrichments.get("similarity") if isinstance(enrichments, dict) else {}
            out["enrichments_summary"] = {
                "computedAt": (enrichments.get("computed_at") if isinstance(enrichments, dict) else None),
                "conceptCount": len(cognate_sets) if isinstance(cognate_sets, dict) else 0,
                "similarityConceptCount": len(similarity) if isinstance(similarity, dict) else 0,
                "speakersIncluded": (
                    list(config.get("speakers_included", []))
                    if isinstance(config, dict)
                    else []
                ),
            }

        if "ai_config" in include:
            ai_config = _read_json_file(self.config_path, {})
            chat_config = ai_config.get("chat") if isinstance(ai_config, dict) else {}
            llm_config = ai_config.get("llm") if isinstance(ai_config, dict) else {}
            out["ai_config"] = {
                "llm": {
                    "provider": _normalize_space(llm_config.get("provider")) if isinstance(llm_config, dict) else "",
                    "model": _normalize_space(llm_config.get("model")) if isinstance(llm_config, dict) else "",
                    "api_key_env": _normalize_space(llm_config.get("api_key_env")) if isinstance(llm_config, dict) else "",
                },
                "chat": {
                    "provider": _normalize_space(chat_config.get("provider")) if isinstance(chat_config, dict) else "",
                    "model": _normalize_space(chat_config.get("model")) if isinstance(chat_config, dict) else "",
                    "reasoning_effort": _normalize_space(chat_config.get("reasoning_effort")) if isinstance(chat_config, dict) else "",
                    "read_only": bool(chat_config.get("read_only", True)) if isinstance(chat_config, dict) else True,
                    "attachments_supported": bool(chat_config.get("attachments_supported", False)) if isinstance(chat_config, dict) else False,
                    "max_user_message_chars": _coerce_int(chat_config.get("max_user_message_chars", 8000), 8000) if isinstance(chat_config, dict) else 8000,
                    "max_session_messages": _coerce_int(chat_config.get("max_session_messages", 200), 200) if isinstance(chat_config, dict) else 200,
                },
            }

        if "constraints" in include:
            out["constraints"] = {
                "mode": "mostly-read-only",
                "writesAllowed": False,
                "writeAllowedTools": sorted(WRITE_ALLOWED_TOOL_NAMES),
                "attachmentsSupported": False,
                "readOnlyNotice": READ_ONLY_NOTICE,
                "toolAllowlist": self.tool_names(),
                "safeRoots": [str(self.project_root / "annotations"), str(self.project_root / "audio"), str(self.project_root / "config")],
            }

        return out

    def _tier_intervals(self, annotation: Mapping[str, Any], tier_name: str) -> List[Dict[str, Any]]:
        tiers = annotation.get("tiers") if isinstance(annotation, Mapping) else None
        if not isinstance(tiers, Mapping):
            return []

        target = None
        if tier_name in tiers and isinstance(tiers.get(tier_name), Mapping):
            target = tiers.get(tier_name)
        else:
            for key, value in tiers.items():
                if isinstance(key, str) and key.lower() == tier_name.lower() and isinstance(value, Mapping):
                    target = value
                    break

        if not isinstance(target, Mapping):
            return []

        intervals = target.get("intervals")
        if not isinstance(intervals, list):
            return []

        out: List[Dict[str, Any]] = []
        for item in intervals:
            if isinstance(item, dict):
                start = _coerce_float(item.get("start"), 0.0)
                end = _coerce_float(item.get("end"), start)
                text = str(item.get("text") or "")
                if end < start:
                    continue
                out.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text,
                    }
                )

        out.sort(key=lambda row: (float(row.get("start", 0.0)), float(row.get("end", 0.0))))
        return out

    def _tool_annotation_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        speaker = self._normalize_speaker(args.get("speaker"))
        include_tiers = args.get("includeTiers")
        if isinstance(include_tiers, list) and include_tiers:
            tiers = [str(item).strip().lower() for item in include_tiers if str(item).strip()]
        else:
            tiers = ["ipa", "ortho", "concept", "speaker"]

        max_intervals = int(args.get("maxIntervals", 500) or 500)

        concept_ids_raw = args.get("conceptIds")
        concept_filter: List[str] = []
        if isinstance(concept_ids_raw, list):
            seen: Dict[str, bool] = {}
            for value in concept_ids_raw:
                concept_id = _normalize_concept_id(value)
                if concept_id and concept_id not in seen:
                    seen[concept_id] = True
                    concept_filter.append(concept_id)

        path = self._annotation_path_for_speaker(speaker)
        if path is None:
            return {
                "readOnly": True,
                "speaker": speaker,
                "status": "not_found",
                "message": "Annotation file not found for speaker",
            }

        annotation = _read_json_file(path, {})
        if not isinstance(annotation, dict):
            raise ChatToolExecutionError("Annotation file is not a JSON object")

        concept_intervals = self._tier_intervals(annotation, "concept")

        selected_ranges: List[Tuple[float, float]] = []
        if concept_filter:
            for interval in concept_intervals:
                concept_id = _normalize_concept_id(interval.get("text"))
                if concept_id in concept_filter:
                    selected_ranges.append((float(interval["start"]), float(interval["end"])))

        def interval_selected(interval: Mapping[str, Any]) -> bool:
            if not selected_ranges:
                return True

            start = _coerce_float(interval.get("start"), 0.0)
            end = _coerce_float(interval.get("end"), start)
            for range_start, range_end in selected_ranges:
                if (min(end, range_end) - max(start, range_start)) > 0:
                    return True
                if abs(start - range_start) <= 0.0005 and abs(end - range_end) <= 0.0005:
                    return True
            return False

        tier_payload: Dict[str, Any] = {}
        truncation: Dict[str, bool] = {}

        for tier_name in tiers:
            intervals = self._tier_intervals(annotation, tier_name)
            filtered = [interval for interval in intervals if interval_selected(interval)]
            truncated = len(filtered) > max_intervals
            tier_payload[tier_name] = filtered[:max_intervals]
            truncation[tier_name] = truncated

        return {
            "readOnly": True,
            "speaker": speaker,
            "source": str(path),
            "conceptFilter": concept_filter,
            "tiers": tier_payload,
            "truncated": truncation,
            "maxIntervals": max_intervals,
            "metadata": annotation.get("metadata") if isinstance(annotation.get("metadata"), dict) else {},
        }

    def _tool_stt_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._start_stt_job is None:
            raise ChatToolExecutionError("STT start callback is unavailable")

        speaker = self._normalize_speaker(args.get("speaker"))
        source_wav = str(args.get("sourceWav") or "").strip()
        if not source_wav:
            raise ChatToolValidationError("sourceWav is required")

        safe_path = self._resolve_project_path(source_wav, allowed_roots=[self.audio_dir])
        project_relative = str(safe_path.relative_to(self.project_root))

        language_raw = args.get("language")
        language = str(language_raw).strip() if language_raw is not None else None
        if language == "":
            language = None

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "dry_run",
                "tool": "stt_start",
                "plan": {
                    "speaker": speaker,
                    "sourceWav": project_relative,
                    "language": language,
                },
                "message": "Dry run. Would start an STT job for the requested audio file.",
            }

        job_id = self._start_stt_job(speaker, project_relative, language)

        return {
            "readOnly": True,
            "previewOnly": True,
            "jobId": job_id,
            "status": "running",
            "speaker": speaker,
            "sourceWav": project_relative,
            "message": "STT job started. Poll with stt_status.",
        }

    def _tool_stt_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._get_job_snapshot is None:
            raise ChatToolExecutionError("Job snapshot callback is unavailable")

        job_id = str(args.get("jobId") or "").strip()
        if not job_id:
            raise ChatToolValidationError("jobId is required")

        include_segments = bool(args.get("includeSegments", False))
        max_segments = int(args.get("maxSegments", 30) or 30)

        snapshot = self._get_job_snapshot(job_id)
        if snapshot is None:
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "not_found",
                "message": "Unknown jobId",
            }

        if snapshot.get("type") != "stt":
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "invalid_job_type",
                "expected": "stt",
                "actual": snapshot.get("type"),
            }

        result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
        payload: Dict[str, Any] = {
            "readOnly": True,
            "jobId": job_id,
            "status": snapshot.get("status"),
            "progress": snapshot.get("progress"),
            "segmentsProcessed": snapshot.get("segmentsProcessed"),
            "totalSegments": snapshot.get("totalSegments"),
            "error": snapshot.get("error"),
            "speaker": result.get("speaker"),
            "sourceWav": result.get("sourceWav"),
        }

        if include_segments and isinstance(result.get("segments"), list):
            segments = result.get("segments", [])
            payload["segments"] = segments[:max_segments]
            payload["segmentsTruncated"] = len(segments) > max_segments
            payload["segmentCount"] = len(segments)

        return payload

    # ------------------------------------------------------------------
    # Tier 1/2/3 acoustic alignment tools (from feat/acoustic-alignment-ipa)
    # ------------------------------------------------------------------

    def _tool_stt_word_level_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Start a Tier 1 word-level STT job.

        STT now always runs with word_timestamps=True (Tier 1), so this
        delegates to the same callback as stt_start but the tool name
        documents the expectation that segments[].words[] is present in
        the output.
        """
        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "dry_run",
                "tool": "stt_word_level_start",
                "speaker": self._normalize_speaker(args.get("speaker")),
                "note": (
                    "Dry run. Tier 1 STT would run with word_timestamps=True; "
                    "segments would include a nested words[] array."
                ),
            }

        payload = self._tool_stt_start(args)
        payload["tier"] = "tier1_word_level"
        payload["message"] = (
            "Word-level STT job started. Poll with stt_word_level_status."
        )
        return payload

    def _tool_stt_word_level_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read status of a Tier 1 job. includeWords defaults to True."""
        include_words = bool(args.get("includeWords", True))
        # Reuse the base handler; it already returns segments whose items
        # carry the nested words[] key when word_timestamps was enabled.
        delegated = self._tool_stt_status(args)
        delegated["tier"] = "tier1_word_level"
        # Strip nested words[] only if the caller explicitly opted out.
        if not include_words and isinstance(delegated.get("segments"), list):
            for seg in delegated["segments"]:
                if isinstance(seg, dict) and "words" in seg:
                    seg.pop("words", None)
            delegated["wordsOmitted"] = True
        return delegated

    def _tool_forced_align_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Start a Tier 2 forced-alignment compute job."""
        speaker = self._normalize_speaker(args.get("speaker"))

        language_raw = args.get("language")
        language = str(language_raw).strip() if language_raw is not None else "ku"
        if not language:
            language = "ku"

        pad_ms_raw = args.get("padMs", 100)
        try:
            pad_ms = int(pad_ms_raw)
        except (TypeError, ValueError):
            pad_ms = 100
        pad_ms = max(0, min(500, pad_ms))

        emit_phonemes = bool(args.get("emitPhonemes", True))
        overwrite = bool(args.get("overwrite", False))

        payload_body: Dict[str, Any] = {
            "speaker": speaker,
            "overwrite": overwrite,
            "language": language,
            "padMs": pad_ms,
            "emitPhonemes": emit_phonemes,
        }

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "dry_run",
                "tool": "forced_align_start",
                "plan": payload_body,
                "note": (
                    "Dry run. Would launch a forced_align compute job against "
                    "facebook/wav2vec2-xlsr-53-espeak-cv-ft. G2P output is "
                    "used only to build CTC targets and is never persisted."
                ),
            }

        if self._start_compute_job is None:
            raise ChatToolExecutionError(
                "Compute-job start callback is unavailable — wire ParseChatTools "
                "with start_compute_job to enable Tier 2 forced alignment."
            )

        job_id = self._start_compute_job("forced_align", payload_body)

        return {
            "readOnly": True,
            "previewOnly": True,
            "jobId": job_id,
            "status": "running",
            "tier": "tier2_forced_align",
            "speaker": speaker,
            "message": "Forced-alignment job started. Poll with forced_align_status.",
        }

    def _tool_forced_align_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read status of a Tier 2 forced-alignment compute job."""
        return self._generic_compute_status(
            args,
            expected_type="forced_align",
            tier_label="tier2_forced_align",
        )

    def _tool_ipa_transcribe_acoustic_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Start a Tier 3 acoustic IPA job (wav2vec2 on audio slices)."""
        speaker = self._normalize_speaker(args.get("speaker"))
        overwrite = bool(args.get("overwrite", False))

        payload_body: Dict[str, Any] = {
            "speaker": speaker,
            "overwrite": overwrite,
        }

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "dry_run",
                "tool": "ipa_transcribe_acoustic_start",
                "plan": payload_body,
                "note": (
                    "Dry run. Would launch the ipa_only compute job, running "
                    "facebook/wav2vec2-xlsr-53-espeak-cv-ft CTC on each ortho "
                    "interval's audio window. No text-based IPA paths exist."
                ),
            }

        if self._start_compute_job is None:
            raise ChatToolExecutionError(
                "Compute-job start callback is unavailable — wire ParseChatTools "
                "with start_compute_job to enable Tier 3 acoustic IPA."
            )

        job_id = self._start_compute_job("ipa_only", payload_body)

        return {
            "readOnly": True,
            "previewOnly": True,
            "jobId": job_id,
            "status": "running",
            "tier": "tier3_acoustic_ipa",
            "speaker": speaker,
            "overwrite": overwrite,
            "message": (
                "Acoustic IPA job started. Poll with "
                "ipa_transcribe_acoustic_status."
            ),
        }

    def _tool_ipa_transcribe_acoustic_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read status of a Tier 3 acoustic IPA compute job."""
        return self._generic_compute_status(
            args,
            expected_type="ipa_only",
            tier_label="tier3_acoustic_ipa",
        )

    def _generic_compute_status(
        self,
        args: Dict[str, Any],
        *,
        expected_type: str,
        tier_label: str,
    ) -> Dict[str, Any]:
        """Shared status reader for Tier 2/3 compute jobs."""
        if self._get_job_snapshot is None:
            raise ChatToolExecutionError("Job snapshot callback is unavailable")

        job_id = str(args.get("jobId") or "").strip()
        if not job_id:
            raise ChatToolValidationError("jobId is required")

        snapshot = self._get_job_snapshot(job_id)
        if snapshot is None:
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "not_found",
                "tier": tier_label,
                "message": "Unknown jobId",
            }

        actual_type = str(snapshot.get("type") or snapshot.get("computeType") or "").strip().lower()
        if actual_type and actual_type not in {
            expected_type,
            expected_type.replace("_", "-"),
            "compute:{0}".format(expected_type),
        }:
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "invalid_job_type",
                "tier": tier_label,
                "expected": expected_type,
                "actual": actual_type,
            }

        return {
            "readOnly": True,
            "jobId": job_id,
            "tier": tier_label,
            "status": snapshot.get("status"),
            "progress": snapshot.get("progress"),
            "message": snapshot.get("message"),
            "error": snapshot.get("error"),
            "result": snapshot.get("result"),
        }

    # ------------------------------------------------------------------
    # Pipeline preflight + run + status tools (from feat/mcp-pipeline-tools)
    # ------------------------------------------------------------------

    def _tool_speakers_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List all annotated speakers under ``annotations/``.

        Filters to entries that look like real annotation records — either
        ``<speaker>.parse.json`` or ``<speaker>.json`` — so accidental
        sibling directories (e.g. ``backups/``) don't pollute the list.
        """
        speakers: set[str] = set()
        if self.annotations_dir.is_dir():
            for entry in self.annotations_dir.iterdir():
                if not entry.is_file():
                    continue
                name = entry.name
                if name.endswith(".parse.json"):
                    speakers.add(name[: -len(".parse.json")])
                elif name.endswith(".json") and not name.endswith(".parse.json"):
                    speakers.add(name[: -len(".json")])

        ordered = sorted(speakers)
        return {
            "readOnly": True,
            "speakers": ordered,
            "count": len(ordered),
        }

    def _tool_pipeline_state_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._pipeline_state is None:
            raise ChatToolExecutionError("pipeline state callback is unavailable")
        speaker = self._normalize_speaker(args.get("speaker"))
        try:
            state = self._pipeline_state(speaker)
        except Exception as exc:
            raise ChatToolExecutionError("pipeline state lookup failed: {0}".format(exc)) from exc
        if not isinstance(state, dict):
            raise ChatToolExecutionError("pipeline state callback returned non-object")
        payload = {"readOnly": True, "speaker": speaker}
        payload.update(state)
        return payload

    def _tool_pipeline_state_batch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._pipeline_state is None:
            raise ChatToolExecutionError("pipeline state callback is unavailable")

        requested = args.get("speakers")
        if requested is None:
            # Default to every annotated speaker on disk.
            inventory = self._tool_speakers_list({})
            speakers = list(inventory.get("speakers") or [])
        elif isinstance(requested, list):
            speakers = []
            for raw in requested:
                normalized = self._normalize_speaker(raw)
                if normalized and normalized not in speakers:
                    speakers.append(normalized)
        else:
            raise ChatToolValidationError("speakers must be a list")

        results: List[Dict[str, Any]] = []
        blocked = 0
        partial_coverage = 0
        for speaker in speakers:
            try:
                state = self._pipeline_state(speaker)
                if not isinstance(state, dict):
                    state = {}
            except Exception as exc:
                state = {"error": str(exc)}
            # Flatten one row per speaker for easy grid reading.
            row: Dict[str, Any] = {"speaker": speaker}
            row.update(state)
            results.append(row)
            # A speaker is "blocked" if ANY step currently can_run=False;
            # "partial coverage" if ANY STT/ORTH/IPA step has done=true
            # but full_coverage=false (work was started but doesn't span
            # the whole WAV — likely constrained to stale timestamps).
            step_any_blocked = False
            step_any_partial = False
            for step_name in ("normalize", "stt", "ortho", "ipa"):
                step = state.get(step_name) if isinstance(state, dict) else None
                if not isinstance(step, dict):
                    continue
                if step.get("can_run") is False:
                    step_any_blocked = True
                if step_name in ("stt", "ortho", "ipa"):
                    if step.get("done") and step.get("full_coverage") is False:
                        step_any_partial = True
            if step_any_blocked:
                blocked += 1
            if step_any_partial:
                partial_coverage += 1

        return {
            "readOnly": True,
            "count": len(results),
            "blockedSpeakers": blocked,
            "partialCoverageSpeakers": partial_coverage,
            "rows": results,
        }

    def _tool_pipeline_run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # Reuses the same start_compute_job callback that powers the Tier
        # 2/3 acoustic tools above; full_pipeline is one compute type
        # among many dispatched from server._run_compute_job.
        if self._start_compute_job is None:
            raise ChatToolExecutionError("start_compute_job callback is unavailable")

        speaker = self._normalize_speaker(args.get("speaker"))
        raw_steps = args.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ChatToolValidationError("steps must be a non-empty list")
        valid = {"normalize", "stt", "ortho", "ipa"}
        steps: List[str] = []
        for raw in raw_steps:
            s = str(raw or "").strip().lower()
            if s not in valid:
                raise ChatToolValidationError("invalid step: {0!r}".format(raw))
            if s not in steps:
                steps.append(s)

        overwrites_raw = args.get("overwrites") or {}
        if not isinstance(overwrites_raw, dict):
            raise ChatToolValidationError("overwrites must be an object")
        overwrites: Dict[str, bool] = {}
        for k, v in overwrites_raw.items():
            kk = str(k or "").strip().lower()
            if kk not in valid:
                raise ChatToolValidationError("invalid overwrite key: {0!r}".format(k))
            overwrites[kk] = bool(v)

        language_raw = args.get("language")
        language = str(language_raw).strip() if isinstance(language_raw, str) else ""

        payload: Dict[str, Any] = {"speaker": speaker, "steps": steps, "overwrites": overwrites}
        if language:
            payload["language"] = language

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "dry_run",
                "tool": "pipeline_run",
                "plan": payload,
                "message": "Dry run. Would start a full_pipeline compute job for this speaker.",
            }

        try:
            job_id = self._start_compute_job("full_pipeline", payload)
        except Exception as exc:
            raise ChatToolExecutionError("pipeline start failed: {0}".format(exc)) from exc

        return {
            "jobId": str(job_id),
            "status": "running",
            "speaker": speaker,
            "steps": steps,
            "overwrites": overwrites,
            "computeType": "full_pipeline",
            "message": "Pipeline job started. Poll with compute_status.",
        }

    def _tool_compute_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._get_job_snapshot is None:
            raise ChatToolExecutionError("Job snapshot callback is unavailable")

        job_id = str(args.get("jobId") or "").strip()
        if not job_id:
            raise ChatToolValidationError("jobId is required")
        expected = str(args.get("computeType") or "").strip().lower()

        snapshot = self._get_job_snapshot(job_id)
        if snapshot is None:
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "not_found",
                "message": "Unknown jobId",
            }

        job_type = str(snapshot.get("type") or "")
        if expected and job_type != "compute:{0}".format(expected):
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "invalid_job_type",
                "expected": "compute:{0}".format(expected),
                "actual": job_type,
            }

        payload: Dict[str, Any] = {
            "readOnly": True,
            "jobId": job_id,
            "type": job_type,
            "status": snapshot.get("status"),
            "progress": snapshot.get("progress"),
            "message": snapshot.get("message"),
            "error": snapshot.get("error"),
            "result": snapshot.get("result"),
        }
        return payload

    # ------------------------------------------------------------------
    # Tier 1 — audio normalize
    # ------------------------------------------------------------------

    def _tool_audio_normalize_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Start a two-pass ffmpeg loudnorm job; returns jobId for polling."""
        if self._start_normalize_job is None:
            raise ChatToolExecutionError("normalize callback is unavailable")

        speaker = self._normalize_speaker(args.get("speaker"))
        source_wav: Optional[str] = str(args.get("sourceWav") or "").strip() or None

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "dry_run",
                "tool": "audio_normalize_start",
                "plan": {
                    "speaker": speaker,
                    "sourceWav": source_wav,
                },
                "message": "Dry run. Would start an audio normalize job for this speaker.",
            }

        try:
            job_id = self._start_normalize_job(speaker, source_wav)
        except Exception as exc:
            raise ChatToolExecutionError("normalize start failed: {0}".format(exc)) from exc

        return {
            "jobId": str(job_id),
            "status": "running",
            "speaker": speaker,
            "message": "Normalize job started. Poll with audio_normalize_status.",
        }

    def _tool_audio_normalize_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Poll a normalize job; validates job type == 'normalize' before returning."""
        if self._get_job_snapshot is None:
            raise ChatToolExecutionError("Job snapshot callback is unavailable")

        job_id = str(args.get("jobId") or "").strip()
        if not job_id:
            raise ChatToolValidationError("jobId is required")

        snapshot = self._get_job_snapshot(job_id)
        if snapshot is None:
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "not_found",
                "message": "Unknown jobId",
            }

        if snapshot.get("type") != "normalize":
            return {
                "readOnly": True,
                "jobId": job_id,
                "status": "invalid_job_type",
                "expected": "normalize",
                "actual": snapshot.get("type"),
            }

        return {
            "readOnly": True,
            "jobId": job_id,
            "type": "normalize",
            "status": snapshot.get("status"),
            "progress": snapshot.get("progress"),
            "message": snapshot.get("message"),
            "error": snapshot.get("error"),
            "result": snapshot.get("result"),
        }

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

    def _tool_jobs_list_active(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return all running jobs from the PARSE job registry for session-restart recovery."""
        if self._list_active_jobs is None:
            raise ChatToolExecutionError("list_active_jobs callback is unavailable")
        try:
            jobs = self._list_active_jobs()
        except Exception as exc:
            raise ChatToolExecutionError("jobs_list_active failed: {0}".format(exc)) from exc
        return {"readOnly": True, "jobs": jobs, "count": len(jobs)}

    def _tool_detect_timestamp_offset(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Proxy detect_offset_detailed against the speaker's annotation + STT job.

        Returns the rich payload (direction, spread, warnings, matched
        anchor↔segment pairs) so MCP / chat clients can sanity-check before
        calling apply_timestamp_offset. Anchor selection defaults to
        quantile sampling across the timeline (less biased toward the
        truncated head) and the selector now requires monotonic
        alignment unless no chain of length ≥ 2 is possible.
        """
        try:
            from compare import (
                anchors_from_intervals,
                detect_offset_detailed,
                load_rules_from_file,
                segments_from_raw,
            )
        except Exception as exc:
            raise ChatToolExecutionError(
                "compare/offset_detect.py is not importable: {0}".format(exc)
            )

        speaker_raw = str(args.get("speaker") or "").strip()
        if not speaker_raw or not SPEAKER_PATTERN.match(speaker_raw):
            raise ChatToolValidationError("speaker is required and must match {0}".format(SPEAKER_PATTERN.pattern))
        speaker = speaker_raw

        annotation_path = self._annotation_path_for_speaker(speaker)
        if annotation_path is None or not annotation_path.is_file():
            raise ChatToolValidationError(
                "No annotation file found for speaker '{0}'".format(speaker)
            )

        try:
            record = json.loads(annotation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ChatToolExecutionError("Failed to read annotation: {0}".format(exc))

        intervals = self._collect_offset_anchor_intervals(record)
        if not intervals:
            raise ChatToolValidationError(
                "Speaker '{0}' has no annotated intervals to use as offset anchors".format(speaker)
            )

        n_anchors = max(2, min(50, int(args.get("nAnchors") or 12)))
        bucket_sec = max(0.1, float(args.get("bucketSec") or 1.0))
        min_match_score = max(0.0, min(1.0, float(args.get("minMatchScore") or 0.56)))
        distribution = str(args.get("anchorDistribution") or "quantile").strip().lower()
        if distribution not in {"quantile", "earliest"}:
            distribution = "quantile"

        stt_segments: Optional[List[Any]] = None
        stt_job_id = str(args.get("sttJobId") or "").strip()
        if stt_job_id:
            if self._get_job_snapshot is None:
                raise ChatToolExecutionError("Job snapshot callback is unavailable")
            snapshot = self._get_job_snapshot(stt_job_id)
            if snapshot is None:
                raise ChatToolValidationError("Unknown sttJobId")
            if snapshot.get("type") != "stt":
                raise ChatToolValidationError("sttJobId is not an STT job")
            if snapshot.get("status") != "complete":
                raise ChatToolValidationError("STT job has not completed")
            result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
            seg_payload = result.get("segments")
            if isinstance(seg_payload, list):
                stt_segments = seg_payload

        if stt_segments is None:
            raise ChatToolValidationError(
                "sttJobId is required for detect_timestamp_offset; pass the jobId of a "
                "completed stt_start run for this speaker, or call "
                "detect_timestamp_offset_from_pair if you already know one true "
                "(csvTime, audioTime) pair."
            )

        rules_path = self.phonetic_rules_path
        try:
            rules = load_rules_from_file(rules_path) if rules_path.exists() else []
        except Exception:
            rules = []

        anchors = anchors_from_intervals(intervals, n_anchors, distribution=distribution)
        if not anchors:
            raise ChatToolValidationError(
                "No usable anchors with both timestamp and text in annotation"
            )
        segments = segments_from_raw(stt_segments)
        if not segments:
            raise ChatToolValidationError("STT input contained no usable segments")

        try:
            detailed = detect_offset_detailed(
                anchors=anchors,
                segments=segments,
                rules=rules,
                bucket_sec=bucket_sec,
                min_match_score=min_match_score,
            )
        except ValueError as exc:
            raise ChatToolExecutionError(str(exc))

        return self._format_offset_detect_payload(
            speaker=speaker,
            offset_sec=float(detailed.offset_sec),
            confidence=float(detailed.confidence),
            n_matched=int(detailed.n_matched),
            total_anchors=len(anchors),
            total_segments=len(segments),
            method=detailed.method,
            spread_sec=float(detailed.spread_sec),
            matches=list(detailed.matches),
            anchor_distribution=distribution,
            annotation_path=annotation_path,
        )

    def _tool_detect_timestamp_offset_from_pair(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Compute the offset from one or more trusted (csv_time, audio_time) pairs.

        Single pair: pass ``audioTimeSec`` + (``csvTimeSec`` or ``conceptId``).
        Multiple pairs: pass ``pairs=[{...}, {...}]``. The reported offset is
        the median of per-pair offsets; spread is the median absolute
        deviation, surfaced as a warning when pairs disagree by > 2 s.
        """
        import math as _math
        import statistics as _statistics

        speaker_raw = str(args.get("speaker") or "").strip()
        if not speaker_raw or not SPEAKER_PATTERN.match(speaker_raw):
            raise ChatToolValidationError("speaker is required and must match {0}".format(SPEAKER_PATTERN.pattern))
        speaker = speaker_raw

        annotation_path = self._annotation_path_for_speaker(speaker)
        record_cache: Optional[Dict[str, Any]] = None

        def _record() -> Dict[str, Any]:
            nonlocal record_cache
            if record_cache is None:
                if annotation_path is None or not annotation_path.is_file():
                    raise ChatToolValidationError(
                        "No annotation file found for speaker '{0}'".format(speaker)
                    )
                try:
                    record_cache = json.loads(annotation_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ChatToolExecutionError("Failed to read annotation: {0}".format(exc))
            return record_cache

        # Normalise to a list of raw-pair dicts.
        raw_pairs: List[Dict[str, Any]]
        if "pairs" in args and args["pairs"] is not None:
            raw_pairs = args["pairs"] if isinstance(args["pairs"], list) else []
            if not raw_pairs:
                raise ChatToolValidationError("pairs must be a non-empty array")
        else:
            raw_pairs = [
                {
                    "audioTimeSec": args.get("audioTimeSec"),
                    "csvTimeSec": args.get("csvTimeSec"),
                    "conceptId": args.get("conceptId"),
                }
            ]

        matches: List[Dict[str, Any]] = []
        offsets: List[float] = []

        for raw in raw_pairs:
            if not isinstance(raw, dict):
                raise ChatToolValidationError("Each pair must be a JSON object")
            try:
                audio_time = float(raw.get("audioTimeSec"))
            except (TypeError, ValueError):
                raise ChatToolValidationError("audioTimeSec is required for every pair")
            if not _math.isfinite(audio_time) or audio_time < 0:
                raise ChatToolValidationError("audioTimeSec must be finite and non-negative")

            anchor_csv_time: Optional[float] = None
            anchor_label: Optional[str] = None

            csv_raw = raw.get("csvTimeSec")
            concept_raw = raw.get("conceptId")
            if csv_raw is not None and (not isinstance(csv_raw, str) or csv_raw != ""):
                try:
                    anchor_csv_time = float(csv_raw)
                except (TypeError, ValueError):
                    raise ChatToolValidationError("csvTimeSec must be a number when provided")
                if not _math.isfinite(anchor_csv_time) or anchor_csv_time < 0:
                    raise ChatToolValidationError("csvTimeSec must be finite and non-negative")
                anchor_label = "csvTimeSec={0:.3f}s".format(anchor_csv_time)
            elif concept_raw is not None and str(concept_raw).strip():
                concept_id = str(concept_raw).strip()
                interval = self._find_concept_interval(_record(), concept_id)
                if interval is None:
                    raise ChatToolValidationError(
                        "No annotation interval found for concept '{0}'".format(concept_id)
                    )
                anchor_csv_time = float(interval["start"])
                anchor_label = "concept '{0}' @ {1:.3f}s".format(concept_id, anchor_csv_time)
            else:
                raise ChatToolValidationError("Each pair needs either csvTimeSec or conceptId")

            offset_sec = round(audio_time - float(anchor_csv_time), 3)
            offsets.append(offset_sec)
            matches.append(
                {
                    "anchor_index": -1,
                    "anchor_text": anchor_label or "",
                    "anchor_start": float(anchor_csv_time),
                    "segment_index": -1,
                    "segment_text": "(user-supplied audio time)",
                    "segment_start": float(audio_time),
                    "score": 1.0,
                    "offset_sec": offset_sec,
                }
            )

        median_offset = round(_statistics.median(offsets), 3)
        if len(offsets) >= 2:
            deviations = [abs(o - median_offset) for o in offsets]
            spread = round(_statistics.median(deviations), 3)
            max_deviation = max(deviations)
            # Use the worst pair's deviation (not just MAD) so a single
            # outlier in three consistent pairs still drops confidence.
            confidence = max(0.5, min(0.99, 0.99 - (max_deviation / 60.0)))
        else:
            spread = 0.0
            confidence = 0.99

        return self._format_offset_detect_payload(
            speaker=speaker,
            offset_sec=median_offset,
            confidence=float(confidence),
            n_matched=len(matches),
            total_anchors=len(matches),
            total_segments=0,
            method="manual_pair",
            spread_sec=float(spread),
            matches=matches,
            anchor_distribution="manual",
            annotation_path=annotation_path,
        )

    def _format_offset_detect_payload(
        self,
        *,
        speaker: str,
        offset_sec: float,
        confidence: float,
        n_matched: int,
        total_anchors: int,
        total_segments: int,
        method: str,
        spread_sec: float,
        matches: List[Dict[str, Any]],
        anchor_distribution: str,
        annotation_path: Optional[Path],
    ) -> Dict[str, Any]:
        """Mirror of server._offset_detect_payload kept here so MCP / chat
        clients see the same shape regardless of whether the request came
        in via HTTP or via in-process tool execution."""
        if abs(offset_sec) < 1e-3:
            direction = "none"
            direction_label = "no shift needed"
        elif offset_sec > 0:
            direction = "later"
            direction_label = "{0:.3f} s later (toward the end)".format(offset_sec)
        else:
            direction = "earlier"
            direction_label = "{0:.3f} s earlier (toward the start)".format(abs(offset_sec))

        reliable = bool(
            n_matched >= 3 and confidence >= 0.5 and (spread_sec <= 2.0 or n_matched == 1)
        )
        warnings: List[str] = []
        if n_matched < 3 and method != "manual_pair":
            warnings.append(
                "Only {0} anchor match{1} were found — apply with caution.".format(
                    n_matched, "" if n_matched == 1 else "es"
                )
            )
        if spread_sec > 2.0:
            warnings.append(
                "Match offsets disagree by ±{0:.2f}s — the detected value may be noisy.".format(spread_sec)
            )
        if confidence < 0.5 and method != "manual_pair":
            warnings.append(
                "Low confidence; consider re-running STT or using "
                "detect_timestamp_offset_from_pair with a manual single-anchor pair."
            )
        if method == "bucket_vote":
            warnings.append(
                "Monotonic alignment failed; fell back to bucket vote which is more vulnerable to false matches."
            )

        payload: Dict[str, Any] = {
            "readOnly": True,
            "speaker": speaker,
            "offsetSec": float(offset_sec),
            "confidence": float(confidence),
            "nAnchors": int(n_matched),
            "totalAnchors": int(total_anchors),
            "totalSegments": int(total_segments),
            "method": method,
            "spreadSec": float(spread_sec),
            "direction": direction,
            "directionLabel": direction_label,
            "anchorDistribution": anchor_distribution,
            "reliable": reliable,
            "warnings": warnings,
            "matches": matches,
        }
        if annotation_path is not None:
            try:
                payload["annotationPath"] = str(annotation_path.relative_to(self.project_root))
            except ValueError:
                payload["annotationPath"] = str(annotation_path)
        return payload

    def _find_concept_interval(self, record: Any, concept_id: str) -> Optional[Dict[str, Any]]:
        if not isinstance(record, dict) or not concept_id:
            return None
        needle = str(concept_id).strip()
        if not needle:
            return None
        tiers = record.get("tiers")
        if not isinstance(tiers, dict):
            return None
        for tier_key in ("concept", "ortho", "ipa"):
            tier = tiers.get(tier_key)
            if not isinstance(tier, dict):
                continue
            intervals = tier.get("intervals")
            if not isinstance(intervals, list):
                continue
            for raw in intervals:
                if not isinstance(raw, dict):
                    continue
                start = raw.get("start", raw.get("xmin"))
                text = str(raw.get("text") or "").strip()
                cid = str(raw.get("concept_id") or raw.get("conceptId") or "").strip()
                if cid != needle and text != needle:
                    continue
                try:
                    start_f = float(start) if start is not None else None
                except (TypeError, ValueError):
                    continue
                if start_f is None or start_f < 0:
                    continue
                return {"start": start_f, "text": text}
        return None

    def _tool_apply_timestamp_offset(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add ``offsetSec`` to every interval start/end in the speaker's annotation.

        Negative offsets clamp to 0. ``dryRun=true`` returns a preview of the
        first few shifted intervals without writing.
        """
        speaker_raw = str(args.get("speaker") or "").strip()
        if not speaker_raw or not SPEAKER_PATTERN.match(speaker_raw):
            raise ChatToolValidationError("speaker is required and must match {0}".format(SPEAKER_PATTERN.pattern))
        speaker = speaker_raw

        if "offsetSec" not in args:
            raise ChatToolValidationError("offsetSec is required")
        try:
            offset_sec = float(args.get("offsetSec"))
        except (TypeError, ValueError):
            raise ChatToolValidationError("offsetSec must be a number")
        import math as _math
        if not _math.isfinite(offset_sec):
            raise ChatToolValidationError("offsetSec must be a finite number")
        if abs(offset_sec) < 1e-6:
            raise ChatToolValidationError("offsetSec is effectively zero — nothing to apply")

        if "dryRun" not in args:
            raise ChatToolValidationError("dryRun is required (use true to preview)")
        dry_run = bool(args.get("dryRun"))

        annotation_path = self._annotation_path_for_speaker(speaker)
        if annotation_path is None or not annotation_path.is_file():
            raise ChatToolValidationError(
                "No annotation file found for speaker '{0}'".format(speaker)
            )

        try:
            record = json.loads(annotation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ChatToolExecutionError("Failed to read annotation: {0}".format(exc))

        shifted_count, preview = self._shift_annotation_intervals(record, offset_sec)
        if shifted_count == 0:
            raise ChatToolValidationError("No intervals were shifted")

        if dry_run:
            return {
                "readOnly": True,
                "dryRun": True,
                "speaker": speaker,
                "offsetSec": offset_sec,
                "wouldShiftIntervals": shifted_count,
                "preview": preview,
            }

        if isinstance(record, dict):
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            metadata["modified"] = _utc_now_iso()
            record["metadata"] = metadata

        try:
            annotation_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            raise ChatToolExecutionError("Failed to write annotation: {0}".format(exc))

        return {
            "readOnly": False,
            "dryRun": False,
            "speaker": speaker,
            "appliedOffsetSec": offset_sec,
            "shiftedIntervals": shifted_count,
            "annotationPath": str(annotation_path.relative_to(self.project_root)),
        }

    def _annotation_path_for_speaker(self, speaker: str) -> Optional[Path]:
        canonical = self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)
        if canonical.is_file():
            return canonical
        legacy = self.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_LEGACY_FILENAME_SUFFIX)
        if legacy.is_file():
            return legacy
        return canonical

    def _collect_offset_anchor_intervals(self, record: Any) -> List[Dict[str, Any]]:
        if not isinstance(record, dict):
            return []
        tiers = record.get("tiers")
        if not isinstance(tiers, dict):
            return []
        for tier_key in ("ortho", "ipa", "concept"):
            tier = tiers.get(tier_key)
            if not isinstance(tier, dict):
                continue
            intervals = tier.get("intervals")
            if not isinstance(intervals, list):
                continue
            collected: List[Dict[str, Any]] = []
            for raw in intervals:
                if not isinstance(raw, dict):
                    continue
                start = raw.get("start", raw.get("xmin"))
                end = raw.get("end", raw.get("xmax"))
                text = raw.get("text")
                try:
                    start_f = float(start) if start is not None else None
                    end_f = float(end) if end is not None else None
                except (TypeError, ValueError):
                    continue
                if start_f is None or end_f is None or end_f < start_f:
                    continue
                if not str(text or "").strip():
                    continue
                collected.append({"start": start_f, "end": end_f, "text": str(text).strip()})
            if collected:
                return collected
        return []

    def _shift_annotation_intervals(
        self, record: Any, offset_sec: float
    ) -> Tuple[int, List[Dict[str, Any]]]:
        if not isinstance(record, dict):
            return 0, []
        tiers = record.get("tiers")
        if not isinstance(tiers, dict):
            return 0, []

        shifted = 0
        preview: List[Dict[str, Any]] = []
        for tier_key, tier in tiers.items():
            if not isinstance(tier, dict):
                continue
            intervals = tier.get("intervals")
            if not isinstance(intervals, list):
                continue
            for raw in intervals:
                if not isinstance(raw, dict):
                    continue
                try:
                    start_f = float(raw.get("start", raw.get("xmin")))
                    end_f = float(raw.get("end", raw.get("xmax")))
                except (TypeError, ValueError):
                    continue
                new_start = max(0.0, start_f + offset_sec)
                new_end = max(new_start, end_f + offset_sec)
                raw["start"] = new_start
                raw["end"] = new_end
                if "xmin" in raw:
                    raw["xmin"] = new_start
                if "xmax" in raw:
                    raw["xmax"] = new_end
                shifted += 1
                if len(preview) < 5:
                    preview.append({
                        "tier": tier_key,
                        "from": [start_f, end_f],
                        "to": [new_start, new_end],
                    })
        return shifted, preview

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

        contact_languages_from_config, refs_by_concept = cognate_compute_module.load_contact_language_data(
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
        source_wav = str(args.get("sourceWav") or "").strip()
        if not source_wav:
            raise ChatToolValidationError("sourceWav is required")

        start_sec = _coerce_float(args.get("startSec"), 0.0)
        end_sec = _coerce_float(args.get("endSec"), 0.0)
        if end_sec <= start_sec:
            raise ChatToolValidationError("endSec must be greater than startSec")

        window_size = int(args.get("windowSize", 2048) or 2048)

        safe_audio = self._resolve_project_path(source_wav, allowed_roots=[self.audio_dir])

        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "placeholder",
            "message": (
                "Spectrogram preview backend hook acknowledged, but binary/image generation "
                "is not wired in this MVP."
            ),
            "request": {
                "sourceWav": str(safe_audio.relative_to(self.project_root)),
                "startSec": round(start_sec, 3),
                "endSec": round(end_sec, 3),
                "windowSize": window_size,
            },
            "backendHook": {
                "implemented": False,
                "plannedEndpoint": "/api/compute/spectrograms",
                "notes": "Client-side spectrogram worker remains the active rendering path.",
            },
        }

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
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

    def _tool_read_audio_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return WAV metadata (duration, sample rate, channels) via stdlib wave."""
        import wave as _wave

        source_wav = str(args.get("sourceWav") or "").strip()
        if not source_wav:
            raise ChatToolValidationError("sourceWav is required")

        # Relative paths are anchored at audio/ for continuity with earlier
        # behavior. Absolute paths go through the broader readable-path
        # resolver so PARSE_EXTERNAL_READ_ROOTS (including "*") applies.
        candidate = Path(source_wav).expanduser()
        if candidate.is_absolute():
            safe_audio = self._resolve_readable_path(source_wav)
        else:
            safe_audio = self._resolve_project_path(source_wav, allowed_roots=[self.audio_dir])

        if not safe_audio.exists() or not safe_audio.is_file():
            return {"ok": False, "error": "File not found: {0}".format(safe_audio)}

        if safe_audio.suffix.lower() != ".wav":
            return {"ok": False, "error": "Not a .wav file: {0}".format(safe_audio.name)}

        try:
            with _wave.open(str(safe_audio), "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                frame_rate = wav.getframerate()
                n_frames = wav.getnframes()
        except _wave.Error as exc:
            return {"ok": False, "error": "Invalid WAV file: {0}".format(exc)}
        except Exception as exc:
            return {"ok": False, "error": "Failed to read audio file: {0}".format(exc)}

        duration_sec = (n_frames / frame_rate) if frame_rate > 0 else 0.0

        return {
            "ok": True,
            "path": self._display_readable_path(safe_audio),
            "channels": channels,
            "sampleWidthBytes": sample_width,
            "sampleRateHz": frame_rate,
            "numFrames": n_frames,
            "durationSec": round(duration_sec, 3),
            "fileSizeBytes": safe_audio.stat().st_size,
        }

    def _tool_read_csv_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read first N rows of a CSV file, sandboxed to project + external read roots."""
        import csv as _csv
        raw_path = str(args.get("csvPath") or "").strip()
        max_rows = int(args.get("maxRows") or 20)

        if raw_path:
            csv_path = self._resolve_readable_path(raw_path)
        else:
            csv_path = self.project_root / "concepts.csv"

        if not csv_path.exists():
            return {"ok": False, "error": "File not found: {0}".format(csv_path)}

        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                sample = f.read(8192)

            delimiter = ","
            try:
                dialect = _csv.Sniffer().sniff(sample, delimiters=",\t;")
                delimiter = dialect.delimiter
            except Exception:
                pass

            rows: list = []
            total = 0
            columns: list = []
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = _csv.DictReader(f, delimiter=delimiter)
                columns = list(reader.fieldnames or [])
                for row in reader:
                    total += 1
                    if len(rows) < max_rows:
                        rows.append(dict(row))

            return {
                "ok": True,
                "path": str(csv_path),
                "delimiter": delimiter,
                "columns": columns,
                "totalRows": total,
                "sampleRows": rows,
                "maxRowsShown": min(max_rows, total),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _tool_read_text_preview(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read a bounded Markdown/text preview from workspace/docs root."""
        raw_path = str(args.get("path") or "").strip()
        start_line = int(args.get("startLine") or 1)
        max_lines = int(args.get("maxLines") or 120)
        max_chars = int(args.get("maxChars") or 12000)

        extra_roots: List[Path] = []
        if self.docs_root is not None:
            extra_roots.append(self.docs_root)

        try:
            text_path = self._resolve_readable_path(raw_path, extra_roots=extra_roots)
        except ChatToolValidationError as exc:
            return {"ok": False, "error": str(exc)}

        extension = text_path.suffix.lower()
        if extension not in TEXT_PREVIEW_EXTENSIONS:
            return {
                "ok": False,
                "error": "Unsupported file type: {0}. Allowed: {1}".format(
                    extension or "(none)", ", ".join(sorted(TEXT_PREVIEW_EXTENSIONS))
                ),
            }

        if not text_path.exists() or not text_path.is_file():
            return {"ok": False, "error": "File not found: {0}".format(text_path)}

        try:
            lines = text_path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            return {"ok": False, "error": "Failed to read text file: {0}".format(exc)}

        if start_line < 1:
            start_line = 1

        start_idx = start_line - 1
        if start_idx >= len(lines):
            return {
                "ok": True,
                "path": str(text_path),
                "lineStart": start_line,
                "lineEnd": start_line,
                "totalLines": len(lines),
                "truncated": False,
                "content": "",
                "message": "startLine is beyond end-of-file",
            }

        selected = lines[start_idx:start_idx + max_lines]
        content = "\n".join(selected)
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars]
            truncated = True
        if (start_idx + max_lines) < len(lines):
            truncated = True

        return {
            "ok": True,
            "path": str(text_path),
            "lineStart": start_line,
            "lineEnd": start_line + max(0, len(selected) - 1),
            "totalLines": len(lines),
            "truncated": truncated,
            "content": content,
        }

    def _tool_import_tag_csv(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Match CSV rows to project concept IDs and optionally create a tag."""
        import csv as _csv

        raw_path = str(args.get("csvPath") or "").strip()
        tag_name = str(args.get("tagName") or "").strip()
        color = str(args.get("color") or "#4461d4").strip()
        label_column = str(args.get("labelColumn") or "").strip()
        dry_run = bool(args.get("dryRun", True))

        # Resolve CSV path
        if raw_path:
            csv_path = Path(raw_path).expanduser()
            if not csv_path.is_absolute():
                csv_path = self.project_root / csv_path
            csv_path = csv_path.resolve()
        else:
            csv_path = self.project_root / "concepts.csv"

        if not csv_path.exists():
            return {"ok": False, "error": "CSV file not found: {0}".format(csv_path)}

        # Load project concepts for matching
        project_concepts = self._load_project_concepts()
        if not project_concepts:
            return {"ok": False, "error": "No project concepts loaded. concepts.csv not found in project root."}

        # Build lookup tables
        label_to_id: Dict[str, str] = {c["label"].lower(): c["id"] for c in project_concepts}
        id_to_label: Dict[str, str] = {c["id"]: c["label"] for c in project_concepts}

        # Read input CSV
        delimiter = ","
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                sample = f.read(8192)
            try:
                dialect = _csv.Sniffer().sniff(sample, delimiters=",\t;")
                delimiter = dialect.delimiter
            except Exception:
                pass
        except Exception as exc:
            return {"ok": False, "error": "Could not read CSV: {0}".format(exc)}

        # Detect label column
        csv_rows: list = []
        fieldnames: list = []
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = _csv.DictReader(f, delimiter=delimiter)
                fieldnames = list(reader.fieldnames or [])
                csv_rows = [dict(row) for row in reader]
        except Exception as exc:
            return {"ok": False, "error": "CSV parse error: {0}".format(exc)}

        if not label_column:
            hints = {"concept", "label", "english", "name", "gloss", "concept_en"}
            for col in fieldnames:
                if col.lower() in hints:
                    label_column = col
                    break
            if not label_column and fieldnames:
                label_column = fieldnames[0]

        # Match each row
        matched: list = []
        unmatched: list = []

        def _edit_distance(a: str, b: str) -> int:
            a, b = a.lower(), b.lower()
            if len(a) > len(b):
                a, b = b, a
            prev = list(range(len(b) + 1))
            for i, ca in enumerate(a):
                curr = [i + 1]
                for j, cb in enumerate(b):
                    curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (0 if ca == cb else 1)))
                prev = curr
            return prev[-1]

        for row in csv_rows:
            raw_label = str(row.get(label_column) or "").strip()
            if not raw_label:
                continue
            concept_id = None
            # 1. Exact case-insensitive label match
            concept_id = label_to_id.get(raw_label.lower())
            # 2. Numeric ID match
            if not concept_id and raw_label in id_to_label:
                concept_id = raw_label
            # 3. Fuzzy edit-distance <= 1
            if not concept_id:
                for lbl, cid in label_to_id.items():
                    if _edit_distance(raw_label, lbl) <= 1:
                        concept_id = cid
                        break
            if concept_id:
                matched.append({"csvLabel": raw_label, "conceptId": concept_id, "conceptLabel": id_to_label.get(concept_id, "")})
            else:
                unmatched.append({"csvLabel": raw_label})

        result: Dict[str, Any] = {
            "ok": True,
            "matchedCount": len(matched),
            "unmatchedCount": len(unmatched),
            "matched": matched,
            "unmatched": unmatched,
            "dryRun": dry_run,
        }

        if not tag_name:
            result["needsTagName"] = True
            result["message"] = "Found {0} matches and {1} unmatched. What should this tag be called?".format(len(matched), len(unmatched))
            return result

        if dry_run:
            result["preview"] = True
            result["message"] = "Will create tag {0!r} with {1} concepts. Call again with dryRun=false to confirm.".format(tag_name, len(matched))
            return result

        # dryRun=false — create the tag
        concept_ids = [m["conceptId"] for m in matched]
        return self._tool_prepare_tag_import({
            "tagName": tag_name,
            "color": color,
            "conceptIds": concept_ids,
            "dryRun": False,
        })

    def _tool_prepare_tag_import(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a named tag with concept IDs in parse-tags.json."""
        import json as _json
        import re as _re

        tag_name = str(args.get("tagName") or "").strip()
        color = str(args.get("color") or "#4461d4").strip()
        concept_ids = [str(c).strip() for c in (args.get("conceptIds") or []) if str(c).strip()]
        dry_run = bool(args.get("dryRun", True))

        if not tag_name:
            return {"ok": False, "error": "tagName is required"}
        if not concept_ids:
            return {"ok": False, "error": "conceptIds must not be empty"}

        # Slugify tag name to ID
        tag_id = _re.sub(r"[^a-z0-9]+", "-", tag_name.lower()).strip("-") or "tag"

        if dry_run:
            return {
                "ok": True,
                "dryRun": True,
                "preview": True,
                "tagId": tag_id,
                "tagName": tag_name,
                "color": color,
                "conceptCount": len(concept_ids),
                "message": "Will create tag {0!r} (id={1}) with {2} concepts. Call with dryRun=false to apply.".format(tag_name, tag_id, len(concept_ids)),
            }

        # Load existing tags
        tags: list = []
        if self.tags_path.exists():
            try:
                with open(self.tags_path, "r", encoding="utf-8") as f:
                    existing = _json.load(f)
                if isinstance(existing, list):
                    tags = existing
            except Exception:
                tags = []

        # Upsert: update if tag_id exists, else append
        found = False
        for tag in tags:
            if tag.get("id") == tag_id:
                # Additive merge — never remove existing concept assignments
                existing_ids = set(tag.get("concepts") or [])
                existing_ids.update(concept_ids)
                tag["concepts"] = sorted(existing_ids)
                tag["label"] = tag_name
                tag["color"] = color
                found = True
                break
        if not found:
            tags.append({
                "id": tag_id,
                "label": tag_name,
                "color": color,
                "concepts": sorted(set(concept_ids)),
            })

        # Write parse-tags.json
        try:
            with open(self.tags_path, "w", encoding="utf-8") as f:
                _json.dump(tags, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            return {"ok": False, "error": "Failed to write parse-tags.json: {0}".format(exc)}

        return {
            "ok": True,
            "dryRun": False,
            "tagId": tag_id,
            "tagName": tag_name,
            "color": color,
            "assignedCount": len(concept_ids),
            "totalTagsInFile": len(tags),
            "message": "Tag {0!r} created with {1} concepts. Refresh Compare to see it.".format(tag_name, len(concept_ids)),
        }

    # ------------------------------------------------------------------
    # Speaker onboarding via chat
    # ------------------------------------------------------------------

    def _resolve_onboard_source(self, raw_path: str, *, must_be_audio: bool) -> Path:
        """Resolve a sourceWav/sourceCsv argument.

        Accepts absolute paths under PARSE_EXTERNAL_READ_ROOTS, or absolute/relative
        paths that land under the project root (typically under audio/). Ensures the
        file exists and, for audio, has a supported extension.
        """
        resolved = self._resolve_readable_path(raw_path)

        if not resolved.exists() or not resolved.is_file():
            raise ChatToolValidationError("Source file not found: {0}".format(resolved))

        if must_be_audio:
            suffix = resolved.suffix.lower()
            if suffix not in ONBOARD_AUDIO_EXTENSIONS:
                raise ChatToolValidationError(
                    "Unsupported audio format: {0} (allowed: {1})".format(
                        suffix or "(none)", ", ".join(sorted(ONBOARD_AUDIO_EXTENSIONS))
                    )
                )
        else:
            if resolved.suffix.lower() != ".csv":
                raise ChatToolValidationError("sourceCsv must have a .csv extension")

        return resolved

    def _resolve_processed_json_source(self, raw_path: str, field_name: str) -> Path:
        resolved = self._resolve_readable_path(raw_path)
        if not resolved.exists() or not resolved.is_file():
            raise ChatToolValidationError("{0} not found: {1}".format(field_name, resolved))
        if resolved.suffix.lower() != ".json":
            raise ChatToolValidationError("{0} must have a .json extension".format(field_name))
        return resolved

    def _resolve_processed_csv_source(self, raw_path: str, field_name: str) -> Path:
        resolved = self._resolve_readable_path(raw_path)
        if not resolved.exists() or not resolved.is_file():
            raise ChatToolValidationError("{0} not found: {1}".format(field_name, resolved))
        if resolved.suffix.lower() != ".csv":
            raise ChatToolValidationError("{0} must have a .csv extension".format(field_name))
        return resolved

    def _extract_concepts_from_annotation(self, annotation_payload: Dict[str, Any]) -> List[Dict[str, str]]:
        tiers = annotation_payload.get("tiers") if isinstance(annotation_payload, dict) else {}
        if not isinstance(tiers, dict):
            raise ChatToolValidationError("annotationJson must contain a tiers object")

        concept_tier = tiers.get("concept")
        if not isinstance(concept_tier, dict):
            raise ChatToolValidationError("annotationJson is missing tiers.concept")

        intervals = concept_tier.get("intervals")
        if not isinstance(intervals, list):
            raise ChatToolValidationError("annotationJson tiers.concept.intervals must be a list")

        concept_re = re.compile(r"^\s*#?(\d+)\s*[:.-]\s*(.+?)\s*$")
        existing_concepts = self._load_project_concepts()
        existing_id_by_label = {
            _normalize_space(item.get("label")).casefold(): _normalize_space(item.get("id"))
            for item in existing_concepts
            if _normalize_space(item.get("id")) and _normalize_space(item.get("label"))
        }
        existing_label_by_id = {
            _normalize_space(item.get("id")): _normalize_space(item.get("label"))
            for item in existing_concepts
            if _normalize_space(item.get("id")) and _normalize_space(item.get("label"))
        }
        reserved_numeric_ids = {
            _normalize_space(item.get("id"))
            for item in existing_concepts
            if _normalize_space(item.get("id"))
        }
        for raw_interval in intervals:
            if not isinstance(raw_interval, dict):
                continue
            text = _normalize_space(raw_interval.get("text"))
            if not text:
                continue
            match = concept_re.match(text)
            if match:
                reserved_numeric_ids.add(_normalize_space(match.group(1)))

        concepts: List[Dict[str, str]] = []
        seen_ids = set()
        fallback_index = 1

        def _resolve_by_label(label_text: str) -> str:
            nonlocal fallback_index
            existing_concept_id = existing_id_by_label.get(label_text.casefold())
            if existing_concept_id and existing_concept_id not in seen_ids:
                return existing_concept_id
            while str(fallback_index) in reserved_numeric_ids or str(fallback_index) in seen_ids:
                fallback_index += 1
            assigned = str(fallback_index)
            fallback_index += 1
            return assigned

        for raw_interval in intervals:
            if not isinstance(raw_interval, dict):
                continue
            text = _normalize_space(raw_interval.get("text"))
            if not text:
                continue
            match = concept_re.match(text)
            if match:
                claimed_id = _normalize_space(match.group(1))
                label = _normalize_space(match.group(2))
                # Guard against ID collisions with a different existing label:
                # when another speaker has already registered `claimed_id` with
                # a different label, prefer matching by label (or assigning a
                # fresh id) so we don't clobber the existing concept.
                existing_label_for_id = existing_label_by_id.get(claimed_id)
                if existing_label_for_id and existing_label_for_id.casefold() != label.casefold():
                    concept_id = _resolve_by_label(label)
                else:
                    concept_id = claimed_id
            else:
                label = text
                concept_id = _resolve_by_label(label)
            if not concept_id or not label or concept_id in seen_ids:
                continue
            seen_ids.add(concept_id)
            concepts.append({"id": concept_id, "label": label})

        if not concepts:
            raise ChatToolValidationError("annotationJson does not contain importable concept intervals")

        concepts.sort(key=lambda item: _concept_sort_key(item["id"]))
        return concepts

    def _write_concepts_csv(self, concepts: Sequence[Dict[str, str]]) -> int:
        import csv as _csv

        merged: Dict[str, str] = {item["id"]: item["label"] for item in self._load_project_concepts() if item.get("id") and item.get("label")}
        for item in concepts:
            concept_id = _normalize_space(item.get("id"))
            label = _normalize_space(item.get("label"))
            if concept_id and label:
                merged[concept_id] = label

        ordered = sorted(merged.items(), key=lambda kv: _concept_sort_key(kv[0]))
        concepts_path = self.project_root / "concepts.csv"
        concepts_path.parent.mkdir(parents=True, exist_ok=True)
        with open(concepts_path, "w", newline="", encoding="utf-8") as handle:
            writer = _csv.DictWriter(handle, fieldnames=["id", "concept_en"])
            writer.writeheader()
            for concept_id, label in ordered:
                writer.writerow({"id": concept_id, "concept_en": label})
        return len(ordered)

    def _write_project_json_for_processed_import(
        self,
        speaker: str,
        project_id: str,
        language_code: str,
        concept_total: int,
    ) -> None:
        project = _read_json_file(self.project_json_path, {})
        if not isinstance(project, dict):
            project = {}

        speakers_block = project.get("speakers")
        if isinstance(speakers_block, list):
            speakers_block = {str(item).strip(): {} for item in speakers_block if str(item).strip()}
        elif not isinstance(speakers_block, dict):
            speakers_block = {}
        speakers_block.setdefault(speaker, {})
        project["speakers"] = speakers_block

        resolved_project_id = _normalize_space(project.get("project_id")) or _normalize_space(project_id) or "parse-project"
        project["project_id"] = resolved_project_id
        project_name = _normalize_space(project.get("name") or project.get("project_name"))
        if not project_name:
            project_name = resolved_project_id.replace("-", " ").title()
        project["name"] = project_name
        project["sourceIndex"] = "source_index.json"
        project["audio_dir"] = "audio"
        project["annotations_dir"] = "annotations"

        language_block = project.get("language") if isinstance(project.get("language"), dict) else {}
        language_block["code"] = _normalize_space(language_block.get("code") or language_code) or "und"
        project["language"] = language_block

        project["concepts"] = {
            "source": "concepts.csv",
            "id_column": "id",
            "label_column": "concept_en",
            "total": int(concept_total),
        }

        self.project_json_path.parent.mkdir(parents=True, exist_ok=True)
        self.project_json_path.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_source_index_for_processed_import(
        self,
        speaker: str,
        audio_rel: str,
        duration_sec: float,
        file_size_bytes: int,
        peaks_rel: Optional[str],
        transcript_csv_rel: Optional[str],
    ) -> None:
        source_index = _read_json_file(self.source_index_path, {})
        if not isinstance(source_index, dict):
            source_index = {}
        speakers_block = source_index.get("speakers")
        if not isinstance(speakers_block, dict):
            speakers_block = {}
            source_index["speakers"] = speakers_block

        speaker_entry = speakers_block.get(speaker)
        if not isinstance(speaker_entry, dict):
            speaker_entry = {}

        current_source = {
            "filename": Path(audio_rel).name,
            "path": audio_rel,
            "duration_sec": float(duration_sec),
            "file_size_bytes": int(file_size_bytes),
            "is_primary": True,
            "added_at": _utc_now_iso(),
        }
        existing_sources = speaker_entry.get("source_wavs") if isinstance(speaker_entry.get("source_wavs"), list) else []
        merged_sources = [item for item in existing_sources if isinstance(item, dict)]
        match_index = -1
        for idx, entry in enumerate(merged_sources):
            entry_path = _normalize_space(entry.get("path"))
            if entry_path == audio_rel:
                match_index = idx
                break
        if match_index >= 0:
            merged_sources[match_index] = current_source
        else:
            merged_sources.append(current_source)
        for entry in merged_sources:
            if not isinstance(entry, dict):
                continue
            entry["is_primary"] = _normalize_space(entry.get("path")) == audio_rel
        speaker_entry["source_wavs"] = merged_sources

        if peaks_rel:
            speaker_entry["peaks_file"] = peaks_rel
        else:
            speaker_entry.pop("peaks_file", None)
        speaker_entry["has_csv"] = False
        notes = ["imported from processed artifacts"]
        if transcript_csv_rel:
            speaker_entry["legacy_transcript_csv"] = transcript_csv_rel
            notes.append("legacy transcript csv copied")
        else:
            speaker_entry.pop("legacy_transcript_csv", None)
        speaker_entry["notes"] = "; ".join(notes)
        speakers_block[speaker] = speaker_entry

        self.source_index_path.parent.mkdir(parents=True, exist_ok=True)
        self.source_index_path.write_text(json.dumps(source_index, indent=2, ensure_ascii=False), encoding="utf-8")

    def _tool_import_processed_speaker(self, args: Dict[str, Any]) -> Dict[str, Any]:
        import shutil

        speaker = self._normalize_speaker(args.get("speaker"))
        working_wav_raw = str(args.get("workingWav") or "").strip()
        annotation_json_raw = str(args.get("annotationJson") or "").strip()
        if not working_wav_raw:
            raise ChatToolValidationError("workingWav is required")
        if not annotation_json_raw:
            raise ChatToolValidationError("annotationJson is required")

        working_wav = self._resolve_onboard_source(working_wav_raw, must_be_audio=True)
        annotation_json = self._resolve_processed_json_source(annotation_json_raw, "annotationJson")

        peaks_json: Optional[Path] = None
        peaks_json_raw = str(args.get("peaksJson") or "").strip()
        if peaks_json_raw:
            peaks_json = self._resolve_processed_json_source(peaks_json_raw, "peaksJson")

        transcript_csv: Optional[Path] = None
        transcript_csv_raw = str(args.get("transcriptCsv") or "").strip()
        if transcript_csv_raw:
            transcript_csv = self._resolve_processed_csv_source(transcript_csv_raw, "transcriptCsv")

        dry_run = bool(args.get("dryRun"))

        annotation_payload = _read_json_file(annotation_json, None)
        if not isinstance(annotation_payload, dict):
            raise ChatToolValidationError("annotationJson must contain a JSON object")

        annotation_speaker = _normalize_space(annotation_payload.get("speaker"))
        if annotation_speaker and annotation_speaker != speaker:
            raise ChatToolValidationError(
                "annotationJson speaker {0!r} does not match requested speaker {1!r}".format(annotation_speaker, speaker)
            )

        annotation_source_audio = _normalize_space(annotation_payload.get("source_audio"))
        if annotation_source_audio and Path(annotation_source_audio).name != working_wav.name:
            raise ChatToolValidationError(
                "annotationJson source_audio points at a different WAV: {0}".format(annotation_source_audio)
            )

        concepts = self._extract_concepts_from_annotation(annotation_payload)
        metadata = annotation_payload.get("metadata") if isinstance(annotation_payload.get("metadata"), dict) else {}
        language_code = _normalize_space(metadata.get("language_code")) or "und"
        project_id = _normalize_space(annotation_payload.get("project_id")) or "parse-project"
        duration_sec = _coerce_float(annotation_payload.get("source_audio_duration_sec"), 0.0)

        audio_dest = self.audio_dir / "working" / speaker / working_wav.name
        annotation_dest = self.annotations_dir / (speaker + ".json")
        peaks_dest = self.peaks_dir / (speaker + ".json") if peaks_json else None
        transcript_dest = (
            self.project_root / "imports" / "legacy" / speaker / transcript_csv.name
            if transcript_csv else None
        )

        plan: Dict[str, Any] = {
            "speaker": speaker,
            "workingWav": str(working_wav),
            "annotationJson": str(annotation_json),
            "peaksJson": str(peaks_json) if peaks_json else None,
            "transcriptCsv": str(transcript_csv) if transcript_csv else None,
            "audioDest": self._display_readable_path(audio_dest),
            "annotationDest": self._display_readable_path(annotation_dest),
            "peaksDest": self._display_readable_path(peaks_dest) if peaks_dest else None,
            "transcriptDest": self._display_readable_path(transcript_dest) if transcript_dest else None,
            "conceptCount": len(concepts),
            "languageCode": language_code,
            "projectId": project_id,
            "wavSizeBytes": working_wav.stat().st_size,
            "annotationSizeBytes": annotation_json.stat().st_size,
            "peaksSizeBytes": peaks_json.stat().st_size if peaks_json else None,
        }

        if dry_run:
            return {
                "ok": True,
                "dryRun": True,
                "plan": plan,
                "message": "Preview only. Run again with dryRun=false to copy processed artifacts and register the speaker.",
            }

        audio_dest.parent.mkdir(parents=True, exist_ok=True)
        annotation_dest.parent.mkdir(parents=True, exist_ok=True)
        if peaks_dest is not None:
            peaks_dest.parent.mkdir(parents=True, exist_ok=True)
        if transcript_dest is not None:
            transcript_dest.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(working_wav, audio_dest)
        if peaks_json is not None and peaks_dest is not None:
            shutil.copy2(peaks_json, peaks_dest)
        if transcript_csv is not None and transcript_dest is not None:
            shutil.copy2(transcript_csv, transcript_dest)

        annotation_out = copy.deepcopy(annotation_payload)
        annotation_out["speaker"] = speaker
        annotation_out["source_audio"] = self._display_readable_path(audio_dest)
        annotation_dest.write_text(json.dumps(annotation_out, indent=2, ensure_ascii=False), encoding="utf-8")

        concept_total = self._write_concepts_csv(concepts)
        self._write_project_json_for_processed_import(speaker, project_id, language_code, concept_total)
        self._write_source_index_for_processed_import(
            speaker=speaker,
            audio_rel=self._display_readable_path(audio_dest),
            duration_sec=duration_sec,
            file_size_bytes=audio_dest.stat().st_size,
            peaks_rel=self._display_readable_path(peaks_dest) if peaks_dest else None,
            transcript_csv_rel=self._display_readable_path(transcript_dest) if transcript_dest else None,
        )

        return {
            "ok": True,
            "dryRun": False,
            "plan": plan,
            "conceptCount": concept_total,
            "message": "Speaker {0!r} imported from processed artifacts.".format(speaker),
        }

    def _tool_onboard_speaker_import(self, args: Dict[str, Any]) -> Dict[str, Any]:
        speaker = self._normalize_speaker(args.get("speaker"))

        source_wav_raw = str(args.get("sourceWav") or "").strip()
        if not source_wav_raw:
            raise ChatToolValidationError("sourceWav is required")

        wav_path = self._resolve_onboard_source(source_wav_raw, must_be_audio=True)

        csv_path: Optional[Path] = None
        source_csv_raw = str(args.get("sourceCsv") or "").strip()
        if source_csv_raw:
            csv_path = self._resolve_onboard_source(source_csv_raw, must_be_audio=False)

        dry_run = bool(args.get("dryRun"))
        is_primary_arg = args.get("isPrimary")

        # Existing source index state — used for preview and to decide the default is_primary.
        source_index = _read_json_file(self.source_index_path, {})
        speakers_block = source_index.get("speakers") if isinstance(source_index, dict) else {}
        existing_entry = speakers_block.get(speaker) if isinstance(speakers_block, dict) else None
        existing_sources = (
            existing_entry.get("source_wavs", [])
            if isinstance(existing_entry, dict)
            else []
        )
        existing_filenames = [
            str(entry.get("filename", ""))
            for entry in existing_sources
            if isinstance(entry, dict)
        ]
        already_registered = wav_path.name in existing_filenames

        if is_primary_arg is None:
            is_primary = not existing_sources and not already_registered
        else:
            is_primary = bool(is_primary_arg)

        target_dir = self.audio_dir / "original" / speaker
        wav_dest = target_dir / wav_path.name
        csv_dest = (target_dir / csv_path.name) if csv_path else None

        # Multi-source speakers require a virtual-timeline to align
        # annotations across WAVs. PARSE doesn't auto-build one yet, so flag
        # it explicitly so the agent raises the gap with the user instead of
        # silently writing two disjoint source entries.
        projected_source_count = len(existing_sources) + (0 if already_registered else 1)
        virtual_timeline_required = projected_source_count > 1
        virtual_timeline_note = ""
        if virtual_timeline_required:
            virtual_timeline_note = (
                "Speaker {0!r} will have {1} source WAVs after this import. PARSE does not "
                "yet auto-align multiple WAVs on a shared virtual timeline. Flag downstream "
                "annotation/alignment as pending until a virtual-timeline workflow is in "
                "place; annotations authored against one WAV will not transfer to the other "
                "without manual reconciliation."
            ).format(speaker, projected_source_count)

        plan: Dict[str, Any] = {
            "speaker": speaker,
            "sourceWav": str(wav_path),
            "sourceCsv": str(csv_path) if csv_path else None,
            "wavDest": self._display_readable_path(wav_dest),
            "csvDest": self._display_readable_path(csv_dest) if csv_dest else None,
            "isPrimary": is_primary,
            "newSpeaker": not isinstance(existing_entry, dict),
            "alreadyRegistered": already_registered,
            "wavSizeBytes": wav_path.stat().st_size,
            "csvSizeBytes": csv_path.stat().st_size if csv_path else None,
            "projectedSourceCount": projected_source_count,
            "virtualTimelineRequired": virtual_timeline_required,
        }
        if virtual_timeline_note:
            plan["virtualTimelineNote"] = virtual_timeline_note

        if dry_run:
            return {
                "ok": True,
                "dryRun": True,
                "plan": plan,
                "message": (
                    "Preview only. Run again with dryRun=false to copy the audio into "
                    "audio/original/{speaker}/ and register it in source_index.json."
                ).format(speaker=speaker),
            }

        if self._onboard_speaker is None:
            return {
                "ok": False,
                "dryRun": False,
                "error": (
                    "Onboarding callback is not wired in this chat runtime — cannot "
                    "write to the project. Run the PARSE server (scripts/parse-run.sh) "
                    "and retry."
                ),
                "plan": plan,
            }

        try:
            callback_result = self._onboard_speaker(speaker, wav_path, csv_path, is_primary)
        except Exception as exc:
            return {
                "ok": False,
                "dryRun": False,
                "error": "Onboarding failed: {0}".format(exc),
                "plan": plan,
            }

        out: Dict[str, Any] = {
            "ok": True,
            "dryRun": False,
            "plan": plan,
            "message": (
                "Speaker {0!r} imported. {1}".format(speaker, virtual_timeline_note).strip()
                if virtual_timeline_note
                else "Speaker {0!r} imported.".format(speaker)
            ),
        }
        if isinstance(callback_result, dict):
            out.update(callback_result)
        return out

    # ------------------------------------------------------------------
    # Persistent chat memory (parse-memory.md)
    # ------------------------------------------------------------------

    @staticmethod
    def _memory_normalize_heading(raw: str) -> str:
        return " ".join(str(raw or "").strip().split())

    @classmethod
    def _memory_match_section(cls, section: str, heading_line: str) -> bool:
        stripped = heading_line.strip()
        if not stripped.startswith("##"):
            return False
        heading_text = stripped.lstrip("#").strip()
        return heading_text.lower() == section.lower()

    @classmethod
    def _memory_split_sections(cls, content: str) -> List[Tuple[str, str]]:
        """Return [(heading_line_or_empty, body_text), ...] preserving order.

        The first entry has heading_line="" and contains any prelude before the
        first `##` heading. Subsequent entries start with their heading line.
        """
        lines = content.splitlines(keepends=True)
        sections: List[Tuple[str, List[str]]] = [("", [])]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## ") or stripped == "##":
                sections.append((line.rstrip("\n"), []))
            else:
                sections[-1][1].append(line)
        return [(heading, "".join(body)) for heading, body in sections]

    def _memory_read_raw(self) -> str:
        if not self.memory_path.exists():
            return ""
        try:
            return self.memory_path.read_text(encoding="utf-8")
        except Exception as exc:
            raise ChatToolExecutionError("Failed to read parse-memory.md: {0}".format(exc))

    def _tool_parse_memory_read(self, args: Dict[str, Any]) -> Dict[str, Any]:
        section_arg = self._memory_normalize_heading(args.get("section"))
        max_bytes_raw = args.get("maxBytes")
        try:
            max_bytes = int(max_bytes_raw) if max_bytes_raw is not None else MEMORY_MAX_BYTES
        except (TypeError, ValueError):
            max_bytes = MEMORY_MAX_BYTES
        max_bytes = max(512, min(MEMORY_MAX_BYTES, max_bytes))

        path_display = self._display_readable_path(self.memory_path)

        if not self.memory_path.exists():
            return {
                "ok": True,
                "path": path_display,
                "exists": False,
                "content": "",
                "sections": [],
                "message": "parse-memory.md does not exist yet. Use parse_memory_upsert_section to create it.",
            }

        raw = self._memory_read_raw()
        parsed = self._memory_split_sections(raw)
        section_headings = [
            heading_line.lstrip("#").strip()
            for heading_line, _body in parsed
            if heading_line
        ]

        if section_arg:
            for heading_line, body in parsed:
                if heading_line and self._memory_match_section(section_arg, heading_line):
                    content = "{0}\n{1}".format(heading_line, body).strip("\n")
                    truncated = False
                    encoded = content.encode("utf-8")
                    if len(encoded) > max_bytes:
                        content = encoded[:max_bytes].decode("utf-8", errors="ignore")
                        truncated = True
                    return {
                        "ok": True,
                        "path": path_display,
                        "exists": True,
                        "section": section_arg,
                        "content": content,
                        "truncated": truncated,
                        "sections": section_headings,
                    }
            return {
                "ok": True,
                "path": path_display,
                "exists": True,
                "section": section_arg,
                "found": False,
                "content": "",
                "sections": section_headings,
                "message": "Section not found. Existing sections: {0}".format(
                    ", ".join(section_headings) or "(none)"
                ),
            }

        encoded = raw.encode("utf-8")
        truncated = len(encoded) > max_bytes
        content = encoded[:max_bytes].decode("utf-8", errors="ignore") if truncated else raw

        return {
            "ok": True,
            "path": path_display,
            "exists": True,
            "content": content,
            "truncated": truncated,
            "totalBytes": len(encoded),
            "sections": section_headings,
        }

    def _tool_parse_memory_upsert_section(self, args: Dict[str, Any]) -> Dict[str, Any]:
        section = self._memory_normalize_heading(args.get("section"))
        if not section:
            raise ChatToolValidationError("section is required")

        body = str(args.get("body") or "").rstrip()
        if not body:
            raise ChatToolValidationError("body is required")

        dry_run = bool(args.get("dryRun"))

        # Ensure parse-memory.md lives somewhere writable (project root or under it).
        try:
            self.memory_path.relative_to(self.project_root)
        except ValueError:
            # Absolute custom location is allowed; just make sure the parent exists.
            pass

        existing = self._memory_read_raw()
        sections = self._memory_split_sections(existing) if existing else [("", "")]

        rendered_heading = "## {0}".format(section)
        rendered_section = "{0}\n{1}\n".format(rendered_heading, body)

        updated_parts: List[str] = []
        replaced = False
        for heading_line, section_body in sections:
            if heading_line and self._memory_match_section(section, heading_line):
                updated_parts.append(rendered_section)
                replaced = True
            elif not heading_line:
                # Prelude (before first ## heading)
                updated_parts.append(section_body)
            else:
                updated_parts.append("{0}\n{1}".format(heading_line, section_body))

        if not replaced:
            # Append a new section at end, ensuring a blank line separator.
            preface = "".join(updated_parts)
            if preface and not preface.endswith("\n"):
                preface = preface + "\n"
            if preface and not preface.endswith("\n\n"):
                preface = preface + "\n"
            if not preface:
                preface = "# PARSE chat memory\n\n"
            updated_content = preface + rendered_section
        else:
            updated_content = "".join(updated_parts)
            if not updated_content.endswith("\n"):
                updated_content = updated_content + "\n"

        if len(updated_content.encode("utf-8")) > MEMORY_MAX_BYTES:
            return {
                "ok": False,
                "error": "parse-memory.md would exceed {0} bytes. Trim an old section first.".format(MEMORY_MAX_BYTES),
            }

        path_display = self._display_readable_path(self.memory_path)

        if dry_run:
            return {
                "ok": True,
                "dryRun": True,
                "path": path_display,
                "section": section,
                "action": "replace" if replaced else "create",
                "previewSection": rendered_section,
                "totalBytesAfter": len(updated_content.encode("utf-8")),
            }

        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            self.memory_path.write_text(updated_content, encoding="utf-8")
        except Exception as exc:
            return {"ok": False, "error": "Failed to write parse-memory.md: {0}".format(exc)}

        return {
            "ok": True,
            "dryRun": False,
            "path": path_display,
            "section": section,
            "action": "replace" if replaced else "create",
            "totalBytesAfter": len(updated_content.encode("utf-8")),
            "message": "parse-memory.md {0}d section {1!r}.".format(
                "update" if replaced else "create",
                section,
            ),
        }


__all__ = [
    "ChatToolError",
    "ChatToolValidationError",
    "ChatToolExecutionError",
    "ChatToolSpec",
    "DEFAULT_MCP_TOOL_NAMES",
    "ParseChatTools",
]
