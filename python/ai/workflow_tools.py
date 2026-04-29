#!/usr/bin/env python3
"""High-level PARSE workflow macros for agent-friendly MCP usage.

These tools compose the existing low-level ParseChatTools handlers into a small
set of end-to-end workflows. They intentionally live outside chat_tools.py so
that the low-level 47-tool surface remains stable and focused, while agents get
safe, discoverable one-call workflows.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .chat_tools import (
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
    ParseChatTools,
    TOOL_CONDITION_KIND_FILE_PRESENCE,
    TOOL_CONDITION_KIND_FILESYSTEM_WRITE,
    TOOL_CONDITION_KIND_INPUT_SHAPE,
    TOOL_CONDITION_KIND_JOB_STATE,
    TOOL_CONDITION_KIND_PROJECT_STATE,
    TOOL_MUTABILITY_MUTATING,
    TOOL_MUTABILITY_READ_ONLY,
    _deepcopy_jsonable,
    _normalize_concept_id,
    _normalize_space,
    _project_loaded_condition,
    _read_json_file,
    _tool_condition,
    _utc_now_iso,
    _validate_schema,
)

DEFAULT_MCP_WORKFLOW_TOOL_NAMES: Tuple[str, ...] = (
    "run_full_annotation_pipeline",
    "prepare_compare_mode",
    "export_complete_lingpy_dataset",
)

_TERMINAL_JOB_STATUSES = {"complete", "completed", "done", "error", "failed", "not_found", "invalid_job_type"}


class WorkflowTools:
    """Composite PARSE workflow macros built on top of ParseChatTools handlers."""

    def __init__(
        self,
        project_root: Path,
        config_path: Optional[Path] = None,
        docs_root: Optional[Path] = None,
        start_stt_job: Optional[Callable[[str, str, Optional[str]], str]] = None,
        get_job_snapshot: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        external_read_roots: Optional[Sequence[Path]] = None,
        memory_path: Optional[Path] = None,
        onboard_speaker: Optional[Callable[[str, Path, Optional[Path], bool], Dict[str, Any]]] = None,
        start_compute_job: Optional[Callable[[str, Dict[str, Any]], str]] = None,
        pipeline_state: Optional[Callable[[str], Dict[str, Any]]] = None,
        start_normalize_job: Optional[Callable[[str, Optional[str]], str]] = None,
        list_active_jobs: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self._parse_tools = ParseChatTools(
            project_root=self.project_root,
            config_path=config_path,
            docs_root=docs_root,
            start_stt_job=start_stt_job,
            get_job_snapshot=get_job_snapshot,
            external_read_roots=external_read_roots,
            memory_path=memory_path,
            onboard_speaker=onboard_speaker,
            start_compute_job=start_compute_job,
            pipeline_state=pipeline_state,
            start_normalize_job=start_normalize_job,
            list_active_jobs=list_active_jobs,
        )
        self.concepts_path = self.project_root / "concepts.csv"
        self.annotations_dir = self.project_root / "annotations"
        self.enrichments_path = self.project_root / "parse-enrichments.json"

        self._tool_specs: Dict[str, ChatToolSpec] = {
            "run_full_annotation_pipeline": ChatToolSpec(
                name="run_full_annotation_pipeline",
                description=(
                    "Run the high-level annotation workflow for one speaker. In run_mode='full' "
                    "it preserves the legacy speaker-wide STT → forced-align → IPA sequence; "
                    "in concept-scoped modes it starts one full_pipeline compute job restricted "
                    "to all concept windows or manually edited concept windows."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["speaker_id", "concept_list"],
                    "properties": {
                        "speaker_id": {"type": "string", "minLength": 1, "maxLength": 200},
                        "concept_list": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 500,
                            "items": {"type": "string", "minLength": 1, "maxLength": 64},
                            "description": "Concept IDs used for workflow reporting and final annotation summary filtering.",
                        },
                        "run_mode": {
                            "type": "string",
                            "enum": ["full", "concept-windows", "edited-only"],
                            "default": "full",
                            "description": "full preserves the legacy speaker-wide path; concept-windows and edited-only run the backend compute pipeline on concept windows.",
                        },
                        "concept_ids": {
                            "type": "array",
                            "maxItems": 500,
                            "items": {"type": "string", "minLength": 1, "maxLength": 64},
                            "description": "Optional exact concept IDs for scoped run modes. When omitted, concept-windows selects all concept rows and edited-only selects manually adjusted rows.",
                        },
                        "dryRun": {"type": "boolean", "description": "Validate inputs and preview the planned workflow without starting jobs."},
                    },
                },
                mutability=TOOL_MUTABILITY_MUTATING,
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "speaker_audio_available",
                        "The requested speaker must resolve to a readable source audio file.",
                        kind=TOOL_CONDITION_KIND_FILE_PRESENCE,
                    ),
                    _tool_condition(
                        "concept_list_provided",
                        "The caller must provide a non-empty concept_list for workflow reporting.",
                        kind=TOOL_CONDITION_KIND_INPUT_SHAPE,
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "annotation_workflow_completed",
                        "When dryRun=false, STT, forced alignment, and acoustic IPA are each started and polled to a terminal status.",
                        kind=TOOL_CONDITION_KIND_JOB_STATE,
                    ),
                ),
            ),
            "prepare_compare_mode": ChatToolSpec(
                name="prepare_compare_mode",
                description=(
                    "Prepare a compare-mode bundle for a concept range across multiple speakers. Loads the "
                    "requested annotations, computes a fresh cognate preview, and derives cross-speaker "
                    "match previews from inline segments built from the selected concept windows."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["concept_range", "speakers"],
                    "properties": {
                        "concept_range": {
                            "description": "Either a range string like '1-25' or an explicit concept ID list.",
                        },
                        "speakers": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 200,
                            "items": {"type": "string", "minLength": 1, "maxLength": 200},
                        },
                        "dryRun": {"type": "boolean", "description": "Preview the resolved speaker + concept scope without computing the full compare bundle."},
                    },
                },
                mutability=TOOL_MUTABILITY_READ_ONLY,
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "compare_scope_provided",
                        "The caller must provide a concept_range and at least one speaker.",
                        kind=TOOL_CONDITION_KIND_INPUT_SHAPE,
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "compare_inputs_available",
                        "The tool returns a structured compare bundle for the selected concepts and speakers.",
                        kind=TOOL_CONDITION_KIND_PROJECT_STATE,
                    ),
                ),
            ),
            "export_complete_lingpy_dataset": ChatToolSpec(
                name="export_complete_lingpy_dataset",
                description=(
                    "Export a complete PARSE phylogenetics bundle using the existing low-level export tools. "
                    "Writes LingPy TSV and NEXUS under exports/lingpy/, and can optionally refresh contact "
                    "lexeme references before export."
                ),
                parameters={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "with_contact_lexemes": {
                            "type": "boolean",
                            "description": "If true, run contact_lexeme_lookup before the export steps.",
                        },
                        "dryRun": {"type": "boolean", "description": "Preview the export bundle and planned artifacts without writing files."},
                    },
                },
                mutability=TOOL_MUTABILITY_MUTATING,
                supports_dry_run=True,
                dry_run_parameter="dryRun",
                preconditions=(
                    _project_loaded_condition(),
                    _tool_condition(
                        "annotations_available_for_export",
                        "At least some annotated project data must exist before exporting LingPy artifacts.",
                        kind=TOOL_CONDITION_KIND_PROJECT_STATE,
                    ),
                ),
                postconditions=(
                    _tool_condition(
                        "export_bundle_written",
                        "When dryRun=false, the LingPy TSV and NEXUS outputs are written inside the project export directory.",
                        kind=TOOL_CONDITION_KIND_FILESYSTEM_WRITE,
                    ),
                ),
            ),
        }

    def iter_tool_specs(self) -> Tuple[ChatToolSpec, ...]:
        return tuple(self._tool_specs[name] for name in self.tool_names())

    def tool_spec(self, tool_name: str) -> ChatToolSpec:
        name = str(tool_name or "").strip()
        if name not in self._tool_specs:
            raise ChatToolValidationError("Tool is not allowlisted: {0}".format(name))
        return self._tool_specs[name]

    def tool_names(self) -> List[str]:
        return sorted(self._tool_specs.keys())

    @classmethod
    def get_all_tool_names(cls) -> List[str]:
        return list(DEFAULT_MCP_WORKFLOW_TOOL_NAMES)

    def execute(self, tool_name: str, raw_args: Any) -> Dict[str, Any]:
        name = str(tool_name or "").strip()
        if name not in self._tool_specs:
            raise ChatToolValidationError("Tool is not allowlisted: {0}".format(name))

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
                    raise ChatToolValidationError("Tool arguments must be valid JSON: {0}".format(exc))
        if not isinstance(args, dict):
            raise ChatToolValidationError("Tool arguments must be a JSON object")

        spec = self._tool_specs[name]
        _validate_schema(args, spec.parameters)

        handler = getattr(self, "_tool_{0}".format(name), None)
        if not callable(handler):
            raise ChatToolExecutionError("Tool handler missing for {0}".format(name))

        result = handler(args)
        if not isinstance(result, dict):
            raise ChatToolExecutionError("Tool handler must return a JSON object")

        return {"tool": name, "ok": True, "result": self._finalize_result(spec, result)}

    def _finalize_result(self, spec: ChatToolSpec, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = _deepcopy_jsonable(payload)
        if spec.mutability == TOOL_MUTABILITY_READ_ONLY:
            result.setdefault("readOnly", True)
            result.setdefault("previewOnly", True)
            result.setdefault("mode", "read-only")
            return result

        preview_only = bool(result.get("previewOnly") or result.get("dryRun"))
        result.setdefault("previewOnly", preview_only)
        result.setdefault("readOnly", preview_only)
        result.setdefault("mode", "read-only" if bool(result.get("readOnly")) else "write-allowed")
        return result

    def _normalize_speaker_id(self, raw_value: Any) -> str:
        return self._parse_tools._normalize_speaker(raw_value)

    def _annotation_path_for_speaker(self, speaker_id: str) -> Path:
        path = self._parse_tools._annotation_path_for_speaker(speaker_id)
        if path is None:
            raise ChatToolExecutionError("Annotation path could not be resolved for speaker: {0}".format(speaker_id))
        return path

    def _load_annotation(self, speaker_id: str) -> Dict[str, Any]:
        path = self._annotation_path_for_speaker(speaker_id)
        payload = _read_json_file(path, {})
        if not isinstance(payload, dict):
            raise ChatToolExecutionError("Annotation file is not a JSON object for speaker: {0}".format(speaker_id))
        return payload

    def _resolve_source_wav(self, speaker_id: str) -> str:
        annotation = self._load_annotation(speaker_id)
        source_audio = str(annotation.get("source_audio") or "").strip()
        if source_audio:
            resolved = self.project_root / source_audio
            if resolved.exists():
                return source_audio

        source_index = _read_json_file(self._parse_tools.source_index_path, {})
        speakers_block = source_index.get("speakers") if isinstance(source_index, dict) else {}
        if isinstance(speakers_block, dict):
            speaker_entry = speakers_block.get(speaker_id)
            if isinstance(speaker_entry, dict):
                source_entries = speaker_entry.get("source_wavs")
                if not isinstance(source_entries, list):
                    source_entries = speaker_entry.get("source_files")
                if isinstance(source_entries, list):
                    chosen: Optional[Dict[str, Any]] = None
                    for entry in source_entries:
                        if isinstance(entry, dict) and entry.get("is_primary"):
                            chosen = entry
                            break
                    if chosen is None:
                        for entry in source_entries:
                            if isinstance(entry, dict):
                                chosen = entry
                                break
                    if isinstance(chosen, dict):
                        raw_path = str(chosen.get("path") or chosen.get("file") or "").strip()
                        filename = str(chosen.get("filename") or "").strip()
                        candidates = [raw_path]
                        if filename:
                            candidates.extend(
                                [
                                    "audio/original/{0}/{1}".format(speaker_id, filename),
                                    "audio/working/{0}/{1}".format(speaker_id, filename),
                                ]
                            )
                        for candidate in candidates:
                            if not candidate:
                                continue
                            resolved = self.project_root / candidate
                            if resolved.exists():
                                return candidate

        raise ChatToolExecutionError("No readable source audio could be resolved for speaker: {0}".format(speaker_id))

    def _resolve_concept_ids(self, concept_range: Any) -> List[str]:
        if isinstance(concept_range, list):
            concept_ids: List[str] = []
            seen: set[str] = set()
            for raw_value in concept_range:
                concept_id = _normalize_concept_id(raw_value)
                if concept_id and concept_id not in seen:
                    seen.add(concept_id)
                    concept_ids.append(concept_id)
            if concept_ids:
                return concept_ids
            raise ChatToolValidationError("concept_range list must contain at least one concept ID")

        text = _normalize_space(concept_range)
        if not text:
            raise ChatToolValidationError("concept_range is required")

        if text.isdigit():
            return [text]

        if "-" in text:
            start_text, end_text = [piece.strip() for piece in text.split("-", 1)]
            if not start_text or not end_text or not start_text.isdigit() or not end_text.isdigit():
                raise ChatToolValidationError("concept_range must be a list, a single concept ID, or a numeric range like '1-25'")
            start_value = int(start_text)
            end_value = int(end_text)
            if end_value < start_value:
                raise ChatToolValidationError("concept_range end must be >= start")
            return [str(value) for value in range(start_value, end_value + 1)]

        raise ChatToolValidationError("concept_range must be a list, a single concept ID, or a numeric range like '1-25'")

    def _load_project_concepts(self) -> List[Dict[str, Any]]:
        return self._parse_tools._load_project_concepts()

    def _first_overlapping_text(self, intervals: Sequence[Dict[str, Any]], start: float, end: float) -> str:
        for interval in intervals:
            interval_start = float(interval.get("start", 0.0) or 0.0)
            interval_end = float(interval.get("end", interval_start) or interval_start)
            if interval_end <= start or interval_start >= end:
                continue
            text = _normalize_space(interval.get("text"))
            if text:
                return text
        return ""

    def _inline_segments_from_annotation(self, annotation_payload: Dict[str, Any], concept_ids: Sequence[str]) -> List[Dict[str, Any]]:
        concept_intervals = self._parse_tools._tier_intervals(annotation_payload, "concept")
        ortho_intervals = self._parse_tools._tier_intervals(annotation_payload, "ortho")
        ipa_intervals = self._parse_tools._tier_intervals(annotation_payload, "ipa")
        concept_filter = {_normalize_concept_id(value) for value in concept_ids}
        segments: List[Dict[str, Any]] = []
        for concept_interval in concept_intervals:
            concept_id = _normalize_concept_id(concept_interval.get("text"))
            if concept_filter and concept_id not in concept_filter:
                continue
            start = float(concept_interval.get("start", 0.0) or 0.0)
            end = float(concept_interval.get("end", start) or start)
            ortho_text = self._first_overlapping_text(ortho_intervals, start, end)
            ipa_text = self._first_overlapping_text(ipa_intervals, start, end)
            segments.append(
                {
                    "start": start,
                    "end": end,
                    "text": ortho_text or concept_id,
                    "ortho": ortho_text,
                    "ipa": ipa_text,
                    "conceptId": concept_id,
                }
            )
        return segments

    def _poll_tool_status(
        self,
        status_handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        *,
        job_id: str,
        include_segments: bool = False,
        max_polls: int = 1200,
        sleep_sec: float = 0.5,
    ) -> Dict[str, Any]:
        status_args: Dict[str, Any] = {"jobId": job_id}
        if include_segments:
            status_args["includeSegments"] = True
        last_payload: Dict[str, Any] = {}
        polls = max(1, int(max_polls))
        for poll_index in range(polls):
            payload = status_handler(status_args)
            last_payload = payload
            status = str(payload.get("status") or "").strip().lower()
            if status in _TERMINAL_JOB_STATUSES:
                return payload
            if sleep_sec > 0 and poll_index + 1 < polls:
                time.sleep(sleep_sec)
        return last_payload

    def _terminal_stage_status(self, payload: Dict[str, Any]) -> str:
        status = str(payload.get("status") or "").strip().lower()
        if status in {"complete", "completed", "done"}:
            return "complete"
        return status or "unknown"

    def _is_complete_stage(self, payload: Dict[str, Any]) -> bool:
        return self._terminal_stage_status(payload) == "complete"

    def _stage_progress_percent(self, completed_stages: int, total_stages: int) -> float:
        if total_stages <= 0:
            return 0.0
        return round((float(completed_stages) / float(total_stages)) * 100.0, 1)

    def _workflow_progress_payload(
        self,
        *,
        completed_stages: int,
        total_stages: int,
        current_stage: Optional[str],
        failed_step: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_completed = max(0, min(int(completed_stages), int(total_stages)))
        percent = self._stage_progress_percent(normalized_completed, total_stages)
        done = failed_step is None and normalized_completed >= int(total_stages) and current_stage is None
        return {
            "completedStages": normalized_completed,
            "totalStages": int(total_stages),
            "percent": 100.0 if done else percent,
            "currentStage": current_stage,
            "failedStep": failed_step,
            "done": done,
        }

    def _stage_event(
        self,
        *,
        event: str,
        stage: str,
        tool: str,
        completed_stages: int,
        total_stages: int,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "event": event,
            "stage": stage,
            "tool": tool,
            "progressPercent": self._stage_progress_percent(completed_stages, total_stages),
            "at": _utc_now_iso(),
        }
        if status is not None:
            payload["status"] = status
        if job_id is not None:
            payload["jobId"] = job_id
        if message:
            payload["message"] = message
        return payload

    def _workflow_failure_payload(
        self,
        *,
        speaker_id: str,
        concept_list: Sequence[str],
        source_wav: Optional[str],
        stages: Sequence[Dict[str, Any]],
        events: Sequence[Dict[str, Any]],
        job_ids: Dict[str, str],
        completed_stages: int,
        total_stages: int,
        failed_step: str,
        failed_tool: str,
        failed_payload: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        stage_status = self._terminal_stage_status(failed_payload or {})
        resolved_message = str(
            error_message
            or ((failed_payload or {}).get("error") if isinstance(failed_payload, dict) else "")
            or ((failed_payload or {}).get("message") if isinstance(failed_payload, dict) else "")
            or "Workflow stage failed"
        ).strip()
        resolved_type = str(error_type or "workflow_stage_failure").strip() or "workflow_stage_failure"
        return {
            "speaker_id": speaker_id,
            "concept_list": list(concept_list),
            "source_wav": source_wav,
            "job_ids": dict(job_ids),
            "stages": list(stages),
            "events": list(events),
            "progress": self._workflow_progress_payload(
                completed_stages=completed_stages,
                total_stages=total_stages,
                current_stage=failed_step,
                failed_step=failed_step,
            ),
            "annotation_summary": None,
            "final_status": "error",
            "failedStep": failed_step,
            "failedTool": failed_tool,
            "error": {
                "type": resolved_type,
                "status": stage_status,
                "message": resolved_message,
                "payload": _deepcopy_jsonable(failed_payload) if isinstance(failed_payload, dict) else None,
            },
            "completed_at": _utc_now_iso(),
        }

    def _tool_run_full_annotation_pipeline(self, args: Dict[str, Any]) -> Dict[str, Any]:
        speaker_id = self._normalize_speaker_id(args.get("speaker_id"))
        concept_list_raw = args.get("concept_list")
        if not isinstance(concept_list_raw, list) or not concept_list_raw:
            raise ChatToolValidationError("concept_list must be a non-empty list")
        concept_list: List[str] = []
        seen_concepts: set[str] = set()
        for raw_value in concept_list_raw:
            concept_id = _normalize_concept_id(raw_value)
            if concept_id and concept_id not in seen_concepts:
                seen_concepts.add(concept_id)
                concept_list.append(concept_id)
        if not concept_list:
            raise ChatToolValidationError("concept_list must contain at least one valid concept ID")

        run_mode = str(args.get("run_mode") or "full").strip().lower().replace("_", "-")
        if run_mode not in {"full", "concept-windows", "edited-only"}:
            raise ChatToolValidationError("run_mode must be one of 'full', 'concept-windows', or 'edited-only'")
        concept_ids_raw = args.get("concept_ids")
        concept_ids: Optional[List[str]] = None
        if concept_ids_raw is not None:
            if not isinstance(concept_ids_raw, list):
                raise ChatToolValidationError("concept_ids must be a list")
            concept_ids = []
            seen_scope: set[str] = set()
            for raw_value in concept_ids_raw:
                concept_id = _normalize_concept_id(raw_value)
                if concept_id and concept_id not in seen_scope:
                    seen_scope.add(concept_id)
                    concept_ids.append(concept_id)

        total_stages = 3
        completed_stages = 0
        events: List[Dict[str, Any]] = []
        stages: List[Dict[str, Any]] = []
        job_ids: Dict[str, str] = {}

        try:
            source_wav = self._resolve_source_wav(speaker_id)
        except Exception as exc:
            events.append(
                self._stage_event(
                    event="stage_failed",
                    stage="preflight",
                    tool="source_audio_resolve",
                    completed_stages=0,
                    total_stages=total_stages,
                    status="error",
                    message=str(exc),
                )
            )
            return self._workflow_failure_payload(
                speaker_id=speaker_id,
                concept_list=concept_list,
                source_wav=None,
                stages=stages,
                events=events,
                job_ids=job_ids,
                completed_stages=0,
                total_stages=total_stages,
                failed_step="preflight",
                failed_tool="source_audio_resolve",
                error_message=str(exc),
                error_type=type(exc).__name__,
            )

        pipeline_state = None
        if self._parse_tools._pipeline_state is not None:
            try:
                pipeline_state = self._parse_tools._tool_pipeline_state_read({"speaker": speaker_id})
            except Exception:
                pipeline_state = None

        if bool(args.get("dryRun", False)):
            if run_mode != "full":
                scoped_stages = [
                    {"stage": "stt", "tool": "pipeline_run", "status": "planned", "run_mode": run_mode},
                    {"stage": "ortho", "tool": "pipeline_run", "status": "planned", "run_mode": run_mode},
                    {"stage": "ipa", "tool": "pipeline_run", "status": "planned", "run_mode": run_mode},
                ]
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "dryRun": True,
                    "speaker_id": speaker_id,
                    "concept_list": concept_list,
                    "run_mode": run_mode,
                    "concept_ids": concept_ids or [],
                    "source_wav": source_wav,
                    "stages": scoped_stages,
                    "events": [
                        self._stage_event(event="stage_planned", stage="stt", tool="pipeline_run", completed_stages=0, total_stages=total_stages, status="planned"),
                        self._stage_event(event="stage_planned", stage="ortho", tool="pipeline_run", completed_stages=0, total_stages=total_stages, status="planned"),
                        self._stage_event(event="stage_planned", stage="ipa", tool="pipeline_run", completed_stages=0, total_stages=total_stages, status="planned"),
                    ],
                    "progress": self._workflow_progress_payload(
                        completed_stages=0,
                        total_stages=total_stages,
                        current_stage="stt",
                    ),
                    "pipeline_state": pipeline_state,
                    "note": "Dry run only. Scoped run would start one full_pipeline job with run_mode={0}.".format(run_mode),
                }
            return {
                "readOnly": True,
                "previewOnly": True,
                "dryRun": True,
                "speaker_id": speaker_id,
                "concept_list": concept_list,
                "source_wav": source_wav,
                "stages": [
                    {"stage": "stt", "tool": "stt_start", "status": "planned"},
                    {"stage": "forced_align", "tool": "forced_align_start", "status": "planned"},
                    {"stage": "ipa", "tool": "ipa_transcribe_acoustic_start", "status": "planned"},
                ],
                "events": [
                    self._stage_event(event="stage_planned", stage="stt", tool="stt_start", completed_stages=0, total_stages=total_stages, status="planned"),
                    self._stage_event(event="stage_planned", stage="forced_align", tool="forced_align_start", completed_stages=0, total_stages=total_stages, status="planned"),
                    self._stage_event(event="stage_planned", stage="ipa", tool="ipa_transcribe_acoustic_start", completed_stages=0, total_stages=total_stages, status="planned"),
                ],
                "progress": self._workflow_progress_payload(
                    completed_stages=0,
                    total_stages=total_stages,
                    current_stage="stt",
                ),
                "pipeline_state": pipeline_state,
                "note": "Dry run only. Full run preserves the legacy speaker-wide workflow.",
            }

        if run_mode != "full":
            full_payload: Dict[str, Any] = {
                "speaker": speaker_id,
                "steps": ["stt", "ortho", "ipa"],
                "overwrites": {"stt": True, "ortho": True, "ipa": True},
                "run_mode": run_mode,
            }
            if concept_ids is not None:
                full_payload["concept_ids"] = list(concept_ids)
            events.append(
                self._stage_event(
                    event="stage_started",
                    stage="full_pipeline",
                    tool="pipeline_run",
                    completed_stages=0,
                    total_stages=1,
                    status="running",
                )
            )
            try:
                if self._parse_tools._start_compute_job is None:
                    raise ChatToolExecutionError("start_compute_job callback is unavailable")
                full_job_id = self._parse_tools._start_compute_job("full_pipeline", full_payload)
                full_job_id = str(full_job_id or "").strip()
                if not full_job_id:
                    raise ChatToolExecutionError("full_pipeline stage did not return a jobId")
                job_ids["full_pipeline"] = full_job_id
                pipeline_status = self._poll_tool_status(
                    lambda status_args: self._parse_tools._tool_compute_status({**status_args, "computeType": "full_pipeline"}),
                    job_id=full_job_id,
                )
            except Exception as exc:
                events.append(
                    self._stage_event(
                        event="stage_failed",
                        stage="full_pipeline",
                        tool="pipeline_run",
                        completed_stages=0,
                        total_stages=1,
                        status="error",
                        job_id=job_ids.get("full_pipeline"),
                        message=str(exc),
                    )
                )
                return self._workflow_failure_payload(
                    speaker_id=speaker_id,
                    concept_list=concept_list,
                    source_wav=source_wav,
                    stages=stages,
                    events=events,
                    job_ids=job_ids,
                    completed_stages=0,
                    total_stages=1,
                    failed_step="full_pipeline",
                    failed_tool="pipeline_run",
                    error_message=str(exc),
                    error_type=type(exc).__name__,
                )

            pipeline_stage_status = self._terminal_stage_status(pipeline_status)
            stages.append({
                "stage": "full_pipeline",
                "tool": "pipeline_run",
                "status": pipeline_stage_status,
                "payload": pipeline_status,
                "run_mode": run_mode,
            })
            if not self._is_complete_stage(pipeline_status):
                events.append(
                    self._stage_event(
                        event="stage_failed",
                        stage="full_pipeline",
                        tool="compute_status",
                        completed_stages=0,
                        total_stages=1,
                        status=pipeline_stage_status,
                        job_id=job_ids.get("full_pipeline"),
                        message=str(pipeline_status.get("error") or pipeline_status.get("message") or pipeline_stage_status),
                    )
                )
                return self._workflow_failure_payload(
                    speaker_id=speaker_id,
                    concept_list=concept_list,
                    source_wav=source_wav,
                    stages=stages,
                    events=events,
                    job_ids=job_ids,
                    completed_stages=0,
                    total_stages=1,
                    failed_step="full_pipeline",
                    failed_tool="compute_status",
                    failed_payload=pipeline_status,
                    error_type="workflow_stage_status",
                )
            events.append(
                self._stage_event(
                    event="stage_completed",
                    stage="full_pipeline",
                    tool="compute_status",
                    completed_stages=1,
                    total_stages=1,
                    status=pipeline_stage_status,
                    job_id=job_ids.get("full_pipeline"),
                )
            )
            return {
                "speaker_id": speaker_id,
                "concept_list": concept_list,
                "run_mode": run_mode,
                "concept_ids": concept_ids or [],
                "source_wav": source_wav,
                "job_ids": dict(job_ids),
                "stages": stages,
                "events": events,
                "progress": self._workflow_progress_payload(
                    completed_stages=1,
                    total_stages=1,
                    current_stage=None,
                ),
                "annotation_summary": pipeline_status.get("result"),
                "final_status": "complete",
                "completed_at": _utc_now_iso(),
            }

        events.append(
            self._stage_event(
                event="stage_started",
                stage="stt",
                tool="stt_start",
                completed_stages=completed_stages,
                total_stages=total_stages,
                status="running",
            )
        )
        try:
            stt_started = self._parse_tools._tool_stt_start({"speaker": speaker_id, "sourceWav": source_wav})
            stt_job_id = str(stt_started.get("jobId") or "").strip()
            if not stt_job_id:
                raise ChatToolExecutionError("STT stage did not return a jobId")
            job_ids["stt"] = stt_job_id
            stt_status = self._poll_tool_status(
                self._parse_tools._tool_stt_status,
                job_id=stt_job_id,
                include_segments=True,
            )
        except Exception as exc:
            events.append(
                self._stage_event(
                    event="stage_failed",
                    stage="stt",
                    tool="stt_start",
                    completed_stages=completed_stages,
                    total_stages=total_stages,
                    status="error",
                    job_id=job_ids.get("stt"),
                    message=str(exc),
                )
            )
            return self._workflow_failure_payload(
                speaker_id=speaker_id,
                concept_list=concept_list,
                source_wav=source_wav,
                stages=stages,
                events=events,
                job_ids=job_ids,
                completed_stages=completed_stages,
                total_stages=total_stages,
                failed_step="stt",
                failed_tool="stt_start",
                error_message=str(exc),
                error_type=type(exc).__name__,
            )

        stt_stage_status = self._terminal_stage_status(stt_status)
        stages.append({"stage": "stt", "tool": "stt_start", "status": stt_stage_status, "payload": stt_status})
        if not self._is_complete_stage(stt_status):
            events.append(
                self._stage_event(
                    event="stage_failed",
                    stage="stt",
                    tool="stt_status",
                    completed_stages=completed_stages,
                    total_stages=total_stages,
                    status=stt_stage_status,
                    job_id=job_ids.get("stt"),
                    message=str(stt_status.get("error") or stt_status.get("message") or stt_stage_status),
                )
            )
            return self._workflow_failure_payload(
                speaker_id=speaker_id,
                concept_list=concept_list,
                source_wav=source_wav,
                stages=stages,
                events=events,
                job_ids=job_ids,
                completed_stages=completed_stages,
                total_stages=total_stages,
                failed_step="stt",
                failed_tool="stt_status",
                failed_payload=stt_status,
                error_type="workflow_stage_status",
            )
        completed_stages += 1
        events.append(
            self._stage_event(
                event="stage_completed",
                stage="stt",
                tool="stt_status",
                completed_stages=completed_stages,
                total_stages=total_stages,
                status=stt_stage_status,
                job_id=job_ids.get("stt"),
            )
        )

        events.append(
            self._stage_event(
                event="stage_started",
                stage="forced_align",
                tool="forced_align_start",
                completed_stages=completed_stages,
                total_stages=total_stages,
                status="running",
            )
        )
        try:
            align_started = self._parse_tools._tool_forced_align_start({"speaker": speaker_id})
            align_job_id = str(align_started.get("jobId") or "").strip()
            if not align_job_id:
                raise ChatToolExecutionError("forced_align stage did not return a jobId")
            job_ids["forced_align"] = align_job_id
            align_status = self._poll_tool_status(
                self._parse_tools._tool_forced_align_status,
                job_id=align_job_id,
            )
        except Exception as exc:
            events.append(
                self._stage_event(
                    event="stage_failed",
                    stage="forced_align",
                    tool="forced_align_start",
                    completed_stages=completed_stages,
                    total_stages=total_stages,
                    status="error",
                    job_id=job_ids.get("forced_align"),
                    message=str(exc),
                )
            )
            return self._workflow_failure_payload(
                speaker_id=speaker_id,
                concept_list=concept_list,
                source_wav=source_wav,
                stages=stages,
                events=events,
                job_ids=job_ids,
                completed_stages=completed_stages,
                total_stages=total_stages,
                failed_step="forced_align",
                failed_tool="forced_align_start",
                error_message=str(exc),
                error_type=type(exc).__name__,
            )

        align_stage_status = self._terminal_stage_status(align_status)
        stages.append({
            "stage": "forced_align",
            "tool": "forced_align_start",
            "status": align_stage_status,
            "payload": align_status,
        })
        if not self._is_complete_stage(align_status):
            events.append(
                self._stage_event(
                    event="stage_failed",
                    stage="forced_align",
                    tool="forced_align_status",
                    completed_stages=completed_stages,
                    total_stages=total_stages,
                    status=align_stage_status,
                    job_id=job_ids.get("forced_align"),
                    message=str(align_status.get("error") or align_status.get("message") or align_stage_status),
                )
            )
            return self._workflow_failure_payload(
                speaker_id=speaker_id,
                concept_list=concept_list,
                source_wav=source_wav,
                stages=stages,
                events=events,
                job_ids=job_ids,
                completed_stages=completed_stages,
                total_stages=total_stages,
                failed_step="forced_align",
                failed_tool="forced_align_status",
                failed_payload=align_status,
                error_type="workflow_stage_status",
            )
        completed_stages += 1
        events.append(
            self._stage_event(
                event="stage_completed",
                stage="forced_align",
                tool="forced_align_status",
                completed_stages=completed_stages,
                total_stages=total_stages,
                status=align_stage_status,
                job_id=job_ids.get("forced_align"),
            )
        )

        events.append(
            self._stage_event(
                event="stage_started",
                stage="ipa",
                tool="ipa_transcribe_acoustic_start",
                completed_stages=completed_stages,
                total_stages=total_stages,
                status="running",
            )
        )
        try:
            ipa_started = self._parse_tools._tool_ipa_transcribe_acoustic_start({"speaker": speaker_id})
            ipa_job_id = str(ipa_started.get("jobId") or "").strip()
            if not ipa_job_id:
                raise ChatToolExecutionError("ipa stage did not return a jobId")
            job_ids["ipa"] = ipa_job_id
            ipa_status = self._poll_tool_status(
                self._parse_tools._tool_ipa_transcribe_acoustic_status,
                job_id=ipa_job_id,
            )
        except Exception as exc:
            events.append(
                self._stage_event(
                    event="stage_failed",
                    stage="ipa",
                    tool="ipa_transcribe_acoustic_start",
                    completed_stages=completed_stages,
                    total_stages=total_stages,
                    status="error",
                    job_id=job_ids.get("ipa"),
                    message=str(exc),
                )
            )
            return self._workflow_failure_payload(
                speaker_id=speaker_id,
                concept_list=concept_list,
                source_wav=source_wav,
                stages=stages,
                events=events,
                job_ids=job_ids,
                completed_stages=completed_stages,
                total_stages=total_stages,
                failed_step="ipa",
                failed_tool="ipa_transcribe_acoustic_start",
                error_message=str(exc),
                error_type=type(exc).__name__,
            )

        ipa_stage_status = self._terminal_stage_status(ipa_status)
        stages.append({
            "stage": "ipa",
            "tool": "ipa_transcribe_acoustic_start",
            "status": ipa_stage_status,
            "payload": ipa_status,
        })
        if not self._is_complete_stage(ipa_status):
            events.append(
                self._stage_event(
                    event="stage_failed",
                    stage="ipa",
                    tool="ipa_transcribe_acoustic_status",
                    completed_stages=completed_stages,
                    total_stages=total_stages,
                    status=ipa_stage_status,
                    job_id=job_ids.get("ipa"),
                    message=str(ipa_status.get("error") or ipa_status.get("message") or ipa_stage_status),
                )
            )
            return self._workflow_failure_payload(
                speaker_id=speaker_id,
                concept_list=concept_list,
                source_wav=source_wav,
                stages=stages,
                events=events,
                job_ids=job_ids,
                completed_stages=completed_stages,
                total_stages=total_stages,
                failed_step="ipa",
                failed_tool="ipa_transcribe_acoustic_status",
                failed_payload=ipa_status,
                error_type="workflow_stage_status",
            )
        completed_stages += 1
        events.append(
            self._stage_event(
                event="stage_completed",
                stage="ipa",
                tool="ipa_transcribe_acoustic_status",
                completed_stages=completed_stages,
                total_stages=total_stages,
                status=ipa_stage_status,
                job_id=job_ids.get("ipa"),
            )
        )

        try:
            annotation_summary = self._parse_tools._tool_annotation_read(
                {
                    "speaker": speaker_id,
                    "conceptIds": concept_list,
                    "includeTiers": ["ipa", "ortho", "concept", "speaker"],
                    "maxIntervals": 5000,
                }
            )
        except Exception as exc:
            events.append(
                self._stage_event(
                    event="stage_failed",
                    stage="postflight",
                    tool="annotation_read",
                    completed_stages=completed_stages,
                    total_stages=total_stages,
                    status="error",
                    message=str(exc),
                )
            )
            return self._workflow_failure_payload(
                speaker_id=speaker_id,
                concept_list=concept_list,
                source_wav=source_wav,
                stages=stages,
                events=events,
                job_ids=job_ids,
                completed_stages=completed_stages,
                total_stages=total_stages,
                failed_step="postflight",
                failed_tool="annotation_read",
                error_message=str(exc),
                error_type=type(exc).__name__,
            )

        return {
            "speaker_id": speaker_id,
            "concept_list": concept_list,
            "source_wav": source_wav,
            "job_ids": dict(job_ids),
            "stages": stages,
            "events": events,
            "progress": self._workflow_progress_payload(
                completed_stages=completed_stages,
                total_stages=total_stages,
                current_stage=None,
            ),
            "annotation_summary": annotation_summary,
            "final_status": "complete",
            "completed_at": _utc_now_iso(),
        }

    def _tool_prepare_compare_mode(self, args: Dict[str, Any]) -> Dict[str, Any]:
        concept_ids = self._resolve_concept_ids(args.get("concept_range"))
        speakers_raw = args.get("speakers")
        if not isinstance(speakers_raw, list) or not speakers_raw:
            raise ChatToolValidationError("speakers must be a non-empty list")
        speakers: List[str] = []
        seen_speakers: set[str] = set()
        for raw_speaker in speakers_raw:
            speaker_id = self._normalize_speaker_id(raw_speaker)
            if speaker_id not in seen_speakers:
                seen_speakers.add(speaker_id)
                speakers.append(speaker_id)

        available = set(self._parse_tools._tool_speakers_list({}).get("speakers") or [])
        missing = [speaker for speaker in speakers if speaker not in available]
        if missing:
            raise ChatToolExecutionError("Unknown speakers for compare workflow: {0}".format(", ".join(missing)))

        if bool(args.get("dryRun", False)):
            return {
                "readOnly": True,
                "previewOnly": True,
                "dryRun": True,
                "concept_ids": concept_ids,
                "speakers": speakers,
                "speaker_count": len(speakers),
                "note": "Dry run only. No compare preview computations were executed.",
            }

        speaker_annotations: Dict[str, Any] = {}
        inline_segments_by_speaker: Dict[str, List[Dict[str, Any]]] = {}
        for speaker_id in speakers:
            annotation_payload = self._parse_tools._tool_annotation_read(
                {
                    "speaker": speaker_id,
                    "conceptIds": concept_ids,
                    "includeTiers": ["ipa", "ortho", "concept", "speaker"],
                    "maxIntervals": 5000,
                }
            )
            speaker_annotations[speaker_id] = annotation_payload
            try:
                annotation_record = self._load_annotation(speaker_id)
                inline_segments_by_speaker[speaker_id] = self._inline_segments_from_annotation(annotation_record, concept_ids)
            except Exception:
                inline_segments_by_speaker[speaker_id] = []

        compare_preview = self._parse_tools._tool_cognate_compute_preview(
            {
                "speakers": speakers,
                "conceptIds": concept_ids,
                "includeSimilarity": True,
                "maxConcepts": max(1, len(concept_ids)),
            }
        )

        cross_speaker_matches: Dict[str, Any] = {}
        for speaker_id in speakers:
            segments = inline_segments_by_speaker.get(speaker_id) or []
            if not segments:
                cross_speaker_matches[speaker_id] = {
                    "readOnly": True,
                    "previewOnly": True,
                    "status": "no_segments",
                    "speaker": speaker_id,
                    "matches": [],
                }
                continue
            cross_speaker_matches[speaker_id] = self._parse_tools._tool_cross_speaker_match_preview(
                {
                    "speaker": speaker_id,
                    "sttSegments": segments,
                    "topK": 3,
                    "maxConcepts": max(1, len(concept_ids)),
                }
            )

        return {
            "readOnly": True,
            "previewOnly": True,
            "concept_ids": concept_ids,
            "speaker_count": len(speakers),
            "speakers": speakers,
            "speaker_annotations": speaker_annotations,
            "compare_preview": compare_preview,
            "cross_speaker_matches": cross_speaker_matches,
            "prepared_at": _utc_now_iso(),
        }

    def _tool_export_complete_lingpy_dataset(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with_contact_lexemes = bool(args.get("with_contact_lexemes", True))
        dry_run = bool(args.get("dryRun", False))
        export_dir = "exports/lingpy"
        lingpy_path = "{0}/wordlist.tsv".format(export_dir)
        nexus_path = "{0}/dataset.nex".format(export_dir)

        stages: List[Dict[str, Any]] = []
        artifacts = {
            "lingpy_tsv": lingpy_path,
            "nexus": nexus_path,
        }

        if with_contact_lexemes:
            contact_payload = self._parse_tools._tool_contact_lexeme_lookup({"dryRun": dry_run})
            stages.append({
                "stage": "contact_lexemes",
                "tool": "contact_lexeme_lookup",
                "status": "preview" if dry_run else "complete",
                "payload": contact_payload,
            })

        lingpy_payload = self._parse_tools._tool_export_lingpy_tsv({"outputPath": lingpy_path, "dryRun": dry_run})
        stages.append({
            "stage": "lingpy_tsv",
            "tool": "export_lingpy_tsv",
            "status": "preview" if dry_run else "complete",
            "payload": lingpy_payload,
        })

        nexus_payload = self._parse_tools._tool_export_nexus({"outputPath": nexus_path, "dryRun": dry_run})
        stages.append({
            "stage": "nexus",
            "tool": "export_nexus",
            "status": "preview" if dry_run else "complete",
            "payload": nexus_payload,
        })

        return {
            "dryRun": dry_run,
            "readOnly": dry_run,
            "previewOnly": dry_run,
            "with_contact_lexemes": with_contact_lexemes,
            "artifacts": artifacts,
            "stages": stages,
            "final_status": "preview" if dry_run else "complete",
            "exported_at": _utc_now_iso(),
        }


__all__ = [
    "DEFAULT_MCP_WORKFLOW_TOOL_NAMES",
    "WorkflowTools",
]
