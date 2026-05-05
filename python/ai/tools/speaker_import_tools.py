from __future__ import annotations

import copy
import csv
from datetime import datetime, timezone
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from ..chat_tools import (
    ONBOARD_AUDIO_EXTENSIONS,
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
    _coerce_float,
    _concept_sort_key,
    _normalize_space,
    _project_loaded_condition,
    _read_json_file,
    _tool_condition,
    _utc_now_iso,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


SPEAKER_IMPORT_TOOL_NAMES = (
    "onboard_speaker_import",
    "import_processed_speaker",
    "csv_only_reimport",
    "revert_csv_reimport",
)


SPEAKER_IMPORT_TOOL_SPECS: Dict[str, ChatToolSpec] = {
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
    "csv_only_reimport": ChatToolSpec(
        name="csv_only_reimport",
        description=(
            "Re-import an already-onboarded speaker from a refreshed Audition cue CSV (and optional comments CSV) "
            "without accepting or copying a WAV. The speaker's existing primary WAV is resolved from source_index.json; "
            "dryRun=true previews the resolved WAV and backup path, while dryRun=false first captures a mandatory backup "
            "under annotations/backups/<timestamp>-<speaker>-csv-reimport/ and then reuses the server onboarding worker."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker", "sourceCsv"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200, "description": "Existing speaker ID to re-import."},
                "sourceCsv": {"type": "string", "minLength": 1, "maxLength": 1024, "description": "Path to the refreshed Audition cue CSV."},
                "commentsCsv": {"type": "string", "maxLength": 1024, "description": "Optional path to the companion Audition comments CSV."},
                "dryRun": {"type": "boolean", "description": "If true, validate and preview the backup path without writing or re-importing."},
            },
        },
        mutability="mutating",
        supports_dry_run=True,
        dry_run_parameter="dryRun",
        preconditions=(
            _project_loaded_condition(),
            _tool_condition("speaker_source_registered", "The speaker must already have a registered WAV in source_index.json.", kind="project_state"),
            _tool_condition("csv_reimport_input_readable", "sourceCsv/commentsCsv must resolve to readable CSV files.", kind="file_presence"),
        ),
        postconditions=(
            _tool_condition("csv_reimport_backup_captured", "When dryRun=false, a manifest-backed backup is captured before annotation/enrichment/concept files are rewritten.", kind="filesystem_write"),
        ),
    ),
    "revert_csv_reimport": ChatToolSpec(
        name="revert_csv_reimport",
        description=(
            "Restore the files captured by a csv_only_reimport backup for one speaker. If backupDir is omitted, "
            "the latest annotations/backups/*-<speaker>-csv-reimport directory is selected. Revert restores only "
            "the filenames listed in manifest.json."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200, "description": "Speaker ID whose csv-reimport backup should be restored."},
                "backupDir": {"type": "string", "maxLength": 1024, "description": "Optional backup directory name or relative path under annotations/backups/."},
                "dryRun": {"type": "boolean", "description": "If true, preview which files would be restored without copying them."},
            },
        },
        mutability="mutating",
        supports_dry_run=True,
        dry_run_parameter="dryRun",
        preconditions=(
            _project_loaded_condition(),
            _tool_condition("csv_reimport_backup_available", "A manifest-backed csv-reimport backup must exist for the requested speaker.", kind="file_presence"),
        ),
        postconditions=(
            _tool_condition("csv_reimport_backup_restored", "When dryRun=false, files listed in the backup manifest are copied back to their project locations.", kind="filesystem_write"),
        ),
    ),
}


def _resolve_onboard_source(tools: "ParseChatTools", raw_path: str, *, must_be_audio: bool) -> Path:
    """Resolve a sourceWav/sourceCsv argument.

    Accepts absolute paths under PARSE_EXTERNAL_READ_ROOTS, or absolute/relative
    paths that land under the project root (typically under audio/). Ensures the
    file exists and, for audio, has a supported extension.
    """
    resolved = tools._resolve_readable_path(raw_path)

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


def _resolve_processed_json_source(tools: "ParseChatTools", raw_path: str, field_name: str) -> Path:
    resolved = tools._resolve_readable_path(raw_path)
    if not resolved.exists() or not resolved.is_file():
        raise ChatToolValidationError("{0} not found: {1}".format(field_name, resolved))
    if resolved.suffix.lower() != ".json":
        raise ChatToolValidationError("{0} must have a .json extension".format(field_name))
    return resolved


def _resolve_processed_csv_source(tools: "ParseChatTools", raw_path: str, field_name: str) -> Path:
    resolved = tools._resolve_readable_path(raw_path)
    if not resolved.exists() or not resolved.is_file():
        raise ChatToolValidationError("{0} not found: {1}".format(field_name, resolved))
    if resolved.suffix.lower() != ".csv":
        raise ChatToolValidationError("{0} must have a .csv extension".format(field_name))
    return resolved


def _extract_concepts_from_annotation(tools: "ParseChatTools", annotation_payload: Dict[str, Any]) -> List[Dict[str, str]]:
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
    existing_concepts = tools._load_project_concepts()
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
    reserved_numeric_ids = set(existing_label_by_id)
    for raw_interval in intervals:
        if not isinstance(raw_interval, dict):
            continue
        explicit_id = _normalize_space(raw_interval.get("concept_id") or raw_interval.get("conceptId"))
        if explicit_id:
            reserved_numeric_ids.add(explicit_id)
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

    def _label_from_text(text: str) -> str:
        match = concept_re.match(text)
        if match:
            return _normalize_space(match.group(2))
        return text

    for raw_interval in intervals:
        if not isinstance(raw_interval, dict):
            continue
        text = _normalize_space(raw_interval.get("text"))
        explicit_id = _normalize_space(raw_interval.get("concept_id") or raw_interval.get("conceptId"))
        if explicit_id:
            concept_id = explicit_id
            label = existing_label_by_id.get(concept_id) or _label_from_text(text)
        else:
            if not text:
                continue
            match = concept_re.match(text)
            if match:
                claimed_id = _normalize_space(match.group(1))
                label = _normalize_space(match.group(2))
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


def _write_concepts_csv(tools: "ParseChatTools", concepts: Sequence[Dict[str, str]]) -> int:
    from concept_registry import merge_concepts_into_root_csv
    from concept_source_item import concept_row_from_item, read_concepts_csv_rows, row_value

    concepts_path = tools.project_root / "concepts.csv"
    try:
        existing_rows = read_concepts_csv_rows(concepts_path)
    except (OSError, csv.Error, UnicodeDecodeError):
        existing_rows = []
    existing_by_id = {
        _normalize_space(row.get("id")): row
        for row in existing_rows
        if _normalize_space(row.get("id")) and row_value(row, "concept_en")
    }
    if existing_by_id:
        needs_write = False
        for item in concepts:
            incoming = concept_row_from_item(item)
            concept_id = _normalize_space(incoming.get("id"))
            label = row_value(incoming, "concept_en")
            if not concept_id or not label:
                continue
            existing = existing_by_id.get(concept_id)
            if existing is None:
                needs_write = True
                break
            for key in ("source_item", "source_survey", "custom_order"):
                if not existing.get(key) and incoming.get(key):
                    needs_write = True
                    break
            if needs_write:
                break
        if not needs_write:
            return len(existing_by_id)

    return merge_concepts_into_root_csv(
        tools.project_root,
        concepts,
        normalize_concept_id=_normalize_space,
        concept_sort_key=_concept_sort_key,
    )


def _copy2_unless_samefile(source: Path, destination: Path) -> bool:
    """Copy ``source`` to ``destination`` unless both paths already name the same file."""

    try:
        if destination.exists() and os.path.samefile(source, destination):
            return False
    except OSError:
        pass
    shutil.copy2(source, destination)
    return True


def _merge_processed_annotation_for_parse_json(
    existing_payload: Any,
    imported_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge a processed import into an existing live ``.parse.json`` annotation.

    Processed imports own only the tiers they actually provide. Existing live-only
    tiers and scratch/review top-level fields are preserved so STT/IPA review state
    is not erased by a manifest-derived speaker refresh.
    """

    if not isinstance(existing_payload, dict):
        return copy.deepcopy(imported_payload)

    merged = copy.deepcopy(existing_payload)
    for key, value in imported_payload.items():
        if key == "tiers":
            continue
        merged[key] = copy.deepcopy(value)

    imported_tiers = imported_payload.get("tiers")
    if not isinstance(imported_tiers, dict):
        return merged
    existing_tiers = merged.get("tiers") if isinstance(merged.get("tiers"), dict) else {}
    merged_tiers = copy.deepcopy(existing_tiers)
    for tier_name, tier_payload in imported_tiers.items():
        if isinstance(tier_payload, dict) and isinstance(tier_payload.get("intervals"), list):
            merged_tiers[tier_name] = copy.deepcopy(tier_payload)
        elif tier_name not in merged_tiers:
            merged_tiers[tier_name] = copy.deepcopy(tier_payload)
    merged["tiers"] = merged_tiers
    return merged


def _write_project_json_for_processed_import(
    tools: "ParseChatTools",
    speaker: str,
    project_id: str,
    language_code: str,
    concept_total: int,
) -> None:
    project = _read_json_file(tools.project_json_path, {})
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

    tools.project_json_path.parent.mkdir(parents=True, exist_ok=True)
    tools.project_json_path.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_source_index_for_processed_import(
    tools: "ParseChatTools",
    speaker: str,
    audio_rel: str,
    duration_sec: float,
    file_size_bytes: int,
    peaks_rel: Optional[str],
    transcript_csv_rel: Optional[str],
) -> None:
    source_index = _read_json_file(tools.source_index_path, {})
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

    tools.source_index_path.parent.mkdir(parents=True, exist_ok=True)
    tools.source_index_path.write_text(json.dumps(source_index, indent=2, ensure_ascii=False), encoding="utf-8")


def _csv_reimport_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _project_relative_or_display(tools: "ParseChatTools", path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(tools.project_root).as_posix()
    except ValueError:
        return str(path)


def _resolve_registered_primary_wav(tools: "ParseChatTools", speaker: str) -> tuple[Path, str]:
    source_index = _read_json_file(tools.source_index_path, {})
    speakers_block = source_index.get("speakers") if isinstance(source_index, dict) else {}
    speaker_entry = speakers_block.get(speaker) if isinstance(speakers_block, dict) else None
    source_wavs = speaker_entry.get("source_wavs") if isinstance(speaker_entry, dict) else None
    sources = [entry for entry in (source_wavs or []) if isinstance(entry, dict) and _normalize_space(entry.get("path"))]
    if not sources:
        raise ChatToolValidationError(
            "Speaker {0!r} has no registered WAV; use onboard_speaker_import for first-time imports.".format(speaker)
        )
    selected = next((entry for entry in sources if bool(entry.get("is_primary"))), sources[0])
    raw_path = _normalize_space(selected.get("path"))
    wav_path = Path(raw_path).expanduser()
    if wav_path.is_absolute():
        resolved = wav_path.resolve()
    else:
        resolved = (tools.project_root / wav_path).resolve()
    try:
        wav_rel = resolved.relative_to(tools.project_root).as_posix()
    except ValueError as exc:
        raise ChatToolValidationError("Registered WAV for {0!r} is outside the project workspace: {1}".format(speaker, raw_path)) from exc
    if not resolved.exists() or not resolved.is_file():
        raise ChatToolValidationError("Registered WAV for {0!r} does not exist: {1}".format(speaker, wav_rel))
    return resolved, wav_rel


def _csv_reimport_annotation_exists(tools: "ParseChatTools", speaker: str) -> bool:
    return (tools.annotations_dir / (speaker + ".json")).exists() or (tools.annotations_dir / (speaker + ".parse.json")).exists()


def _csv_reimport_backup_entries(tools: "ParseChatTools", speaker: str) -> List[tuple[str, Path]]:
    return [
        (speaker + ".json", tools.annotations_dir / (speaker + ".json")),
        (speaker + ".parse.json", tools.annotations_dir / (speaker + ".parse.json")),
        ("parse-enrichments.json", tools.project_root / "parse-enrichments.json"),
        ("concepts.csv", tools.project_root / "concepts.csv"),
    ]


def _write_csv_reimport_manifest(
    backup_dir: Path,
    *,
    created_at: str,
    speaker: str,
    files: Sequence[str],
    input_payload: Dict[str, Any],
    result: Optional[Dict[str, Any]],
) -> None:
    manifest = {
        "version": 1,
        "createdAt": created_at,
        "speaker": speaker,
        "operation": "csv_only_reimport",
        "files": list(files),
        "input": input_payload,
        "result": result,
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _capture_csv_reimport_backup(
    tools: "ParseChatTools",
    speaker: str,
    backup_dir: Path,
    input_payload: Dict[str, Any],
) -> List[str]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    captured: List[str] = []
    for filename, source_path in _csv_reimport_backup_entries(tools, speaker):
        if not source_path.exists():
            print("[csv-reimport] backup skipped missing file: {0}".format(source_path), file=sys.stderr, flush=True)
            continue
        shutil.copy2(source_path, backup_dir / filename)
        captured.append(filename)
    _write_csv_reimport_manifest(
        backup_dir,
        created_at=_utc_now_iso(),
        speaker=speaker,
        files=captured,
        input_payload=input_payload,
        result=None,
    )
    return captured


def _ensure_project_local_csv_for_worker(tools: "ParseChatTools", path: Path, speaker: str, timestamp: str) -> Path:
    try:
        path.resolve().relative_to(tools.project_root)
        return path
    except ValueError:
        stage_dir = tools.project_root / "imports" / "csv-reimport" / speaker / timestamp
        stage_dir.mkdir(parents=True, exist_ok=True)
        staged = stage_dir / path.name
        shutil.copy2(path, staged)
        return staged


def _run_csv_reimport_worker(
    project_root: Path,
    speaker: str,
    wav_dest: Path,
    csv_dest: Path,
    comments_csv_dest: Optional[Path],
) -> Dict[str, Any]:
    import server  # Local import keeps normal tool listing lightweight.

    old_cwd = Path.cwd()
    os.chdir(project_root)
    try:
        server._install_route_bindings()
        job_id = server._create_job("onboard:speaker", {"speaker": speaker})
        server._run_onboard_speaker_job(job_id, speaker, wav_dest, csv_dest, comments_csv_dest)
        snapshot = server._get_job_snapshot(job_id)
    finally:
        os.chdir(old_cwd)
    if not isinstance(snapshot, dict):
        raise ChatToolExecutionError("CSV reimport worker did not return a job snapshot")
    if snapshot.get("status") == "error":
        raise ChatToolExecutionError("CSV reimport worker failed: {0}".format(snapshot.get("error") or "unknown error"))
    result = snapshot.get("result")
    if not isinstance(result, dict):
        raise ChatToolExecutionError("CSV reimport worker completed without a result payload")
    return result


def _csv_reimport_backup_dir(tools: "ParseChatTools", speaker: str, timestamp: str) -> Path:
    return tools.annotations_dir / "backups" / "{0}-{1}-csv-reimport".format(timestamp, speaker)


def tool_csv_only_reimport(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    speaker = tools._normalize_speaker(args.get("speaker"))
    source_csv_raw = str(args.get("sourceCsv") or "").strip()
    if not source_csv_raw:
        raise ChatToolValidationError("sourceCsv is required")
    source_csv = _resolve_onboard_source(tools, source_csv_raw, must_be_audio=False)
    comments_csv: Optional[Path] = None
    comments_csv_raw = str(args.get("commentsCsv") or "").strip()
    if comments_csv_raw:
        comments_csv = _resolve_onboard_source(tools, comments_csv_raw, must_be_audio=False)
    wav_path, wav_rel = _resolve_registered_primary_wav(tools, speaker)
    if not _csv_reimport_annotation_exists(tools, speaker):
        raise ChatToolValidationError(
            "Speaker {0!r} has no annotation record; use onboard_speaker_import for first-time imports.".format(speaker)
        )
    dry_run = bool(args.get("dryRun"))
    timestamp = _csv_reimport_timestamp()
    backup_dir = _csv_reimport_backup_dir(tools, speaker, timestamp)
    backup_rel = backup_dir.relative_to(tools.project_root).as_posix()
    input_payload = {
        "sourceCsv": _project_relative_or_display(tools, source_csv),
        "commentsCsv": _project_relative_or_display(tools, comments_csv),
        "wavPath": wav_rel,
    }
    empty_result = {
        "lexemesImported": None,
        "commentsImported": None,
        "conceptsAdded": None,
        "conceptTotal": None,
        "annotationPath": None,
        "wavPath": wav_rel,
        "csvPath": _project_relative_or_display(tools, source_csv),
        "commentsCsvPath": _project_relative_or_display(tools, comments_csv),
    }
    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "speaker": speaker,
            "backupDir": backup_rel,
            **empty_result,
            "message": "Preview only. Run again with dryRun=false to take the backup and re-import.",
        }

    captured = _capture_csv_reimport_backup(tools, speaker, backup_dir, input_payload)
    worker_source_csv = _ensure_project_local_csv_for_worker(tools, source_csv, speaker, timestamp)
    worker_comments_csv = (
        _ensure_project_local_csv_for_worker(tools, comments_csv, speaker, timestamp)
        if comments_csv is not None
        else None
    )
    try:
        result = _run_csv_reimport_worker(tools.project_root, speaker, wav_path, worker_source_csv, worker_comments_csv)
    except Exception as exc:
        _write_csv_reimport_manifest(
            backup_dir,
            created_at=_utc_now_iso(),
            speaker=speaker,
            files=captured,
            input_payload=input_payload,
            result={"error": str(exc)},
        )
        raise
    _write_csv_reimport_manifest(
        backup_dir,
        created_at=_utc_now_iso(),
        speaker=speaker,
        files=captured,
        input_payload=input_payload,
        result=result,
    )
    lexemes = result.get("lexemesImported")
    notes = result.get("commentsImported")
    return {
        "ok": True,
        "dryRun": False,
        "speaker": speaker,
        "backupDir": backup_rel,
        "lexemesImported": result.get("lexemesImported"),
        "commentsImported": result.get("commentsImported"),
        "conceptsAdded": result.get("conceptsAdded"),
        "conceptTotal": result.get("conceptTotal"),
        "annotationPath": result.get("annotationPath"),
        "wavPath": result.get("wavPath"),
        "csvPath": result.get("csvPath"),
        "commentsCsvPath": result.get("commentsCsvPath"),
        "message": "Re-imported {0!r}: {1} lexemes, {2} notes. Backup at {3}.".format(speaker, lexemes or 0, notes or 0, backup_rel),
    }


def _read_csv_reimport_manifest(backup_dir: Path, speaker: str) -> Dict[str, Any]:
    manifest_path = backup_dir / "manifest.json"
    manifest = _read_json_file(manifest_path, None)
    if not isinstance(manifest, dict):
        raise ChatToolValidationError("Backup manifest not found or invalid: {0}".format(manifest_path))
    manifest_speaker = _normalize_space(manifest.get("speaker"))
    if manifest_speaker != speaker:
        raise ChatToolValidationError(
            "Backup manifest speaker {0!r} does not match requested speaker {1!r}".format(manifest_speaker, speaker)
        )
    return manifest


def _resolve_csv_reimport_backup_dir(tools: "ParseChatTools", speaker: str, raw_backup_dir: str) -> Path:
    backups_root = (tools.annotations_dir / "backups").resolve()
    if raw_backup_dir.strip():
        raw_path = Path(raw_backup_dir.strip())
        if raw_path.is_absolute():
            raise ChatToolValidationError("backupDir must be relative under annotations/backups")
        if len(raw_path.parts) >= 2 and raw_path.parts[0] == "annotations" and raw_path.parts[1] == "backups":
            candidate = (tools.project_root / raw_path).resolve()
        else:
            candidate = (backups_root / raw_path).resolve()
        try:
            candidate.relative_to(backups_root)
        except ValueError as exc:
            raise ChatToolValidationError("backupDir must stay under annotations/backups") from exc
        if not candidate.is_dir():
            raise ChatToolValidationError("Backup directory not found: {0}".format(candidate))
        _read_csv_reimport_manifest(candidate, speaker)
        return candidate

    if not backups_root.exists():
        raise ChatToolValidationError("No csv-reimport backups found for {0!r}.".format(speaker))
    matches = sorted(
        (path for path in backups_root.glob("*-{0}-csv-reimport".format(speaker)) if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for candidate in matches:
        try:
            _read_csv_reimport_manifest(candidate, speaker)
        except ChatToolValidationError:
            continue
        return candidate
    raise ChatToolValidationError("No csv-reimport backups found for {0!r}.".format(speaker))


def _restore_target_for_manifest_file(tools: "ParseChatTools", speaker: str, filename: str) -> Path:
    safe_name = Path(filename).name
    if safe_name != filename:
        raise ChatToolValidationError("Backup manifest file entries must be plain filenames: {0}".format(filename))
    if safe_name in {speaker + ".json", speaker + ".parse.json"}:
        return tools.annotations_dir / safe_name
    if safe_name in {"parse-enrichments.json", "concepts.csv"}:
        return tools.project_root / safe_name
    raise ChatToolValidationError("Unsupported csv-reimport backup file: {0}".format(filename))


def tool_revert_csv_reimport(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    speaker = tools._normalize_speaker(args.get("speaker"))
    dry_run = bool(args.get("dryRun"))
    backup_dir = _resolve_csv_reimport_backup_dir(tools, speaker, str(args.get("backupDir") or ""))
    manifest = _read_csv_reimport_manifest(backup_dir, speaker)
    files_raw = manifest.get("files")
    if not isinstance(files_raw, list):
        raise ChatToolValidationError("Backup manifest files must be a list")
    restored: List[str] = []
    skipped: List[str] = []
    for raw_filename in files_raw:
        filename = str(raw_filename or "").strip()
        if not filename:
            continue
        source_path = backup_dir / filename
        target_path = _restore_target_for_manifest_file(tools, speaker, filename)
        if not source_path.exists() or not source_path.is_file():
            print("[csv-reimport] revert skipped missing backup file: {0}".format(source_path), file=sys.stderr, flush=True)
            skipped.append(filename)
            continue
        restored.append(filename)
        if not dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
    backup_rel = backup_dir.relative_to(tools.project_root).as_posix()
    action = "Would restore" if dry_run else "Restored"
    return {
        "ok": True,
        "dryRun": dry_run,
        "speaker": speaker,
        "backupDir": backup_rel,
        "restoredFiles": restored,
        "skippedFiles": skipped,
        "message": "{0} {1} file(s) for {2!r} from {3}.".format(action, len(restored), speaker, backup_rel),
    }


def tool_import_processed_speaker(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    import shutil

    speaker = tools._normalize_speaker(args.get("speaker"))
    working_wav_raw = str(args.get("workingWav") or "").strip()
    annotation_json_raw = str(args.get("annotationJson") or "").strip()
    if not working_wav_raw:
        raise ChatToolValidationError("workingWav is required")
    if not annotation_json_raw:
        raise ChatToolValidationError("annotationJson is required")

    working_wav = _resolve_onboard_source(tools, working_wav_raw, must_be_audio=True)
    annotation_json = _resolve_processed_json_source(tools, annotation_json_raw, "annotationJson")

    peaks_json: Optional[Path] = None
    peaks_json_raw = str(args.get("peaksJson") or "").strip()
    if peaks_json_raw:
        peaks_json = _resolve_processed_json_source(tools, peaks_json_raw, "peaksJson")

    transcript_csv: Optional[Path] = None
    transcript_csv_raw = str(args.get("transcriptCsv") or "").strip()
    if transcript_csv_raw:
        transcript_csv = _resolve_processed_csv_source(tools, transcript_csv_raw, "transcriptCsv")

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

    concepts = _extract_concepts_from_annotation(tools, annotation_payload)
    metadata = annotation_payload.get("metadata") if isinstance(annotation_payload.get("metadata"), dict) else {}
    language_code = _normalize_space(metadata.get("language_code")) or "und"
    project_id = _normalize_space(annotation_payload.get("project_id")) or "parse-project"
    duration_sec = _coerce_float(annotation_payload.get("source_audio_duration_sec"), 0.0)

    audio_dest = tools.audio_dir / "working" / speaker / working_wav.name
    annotation_dest = tools.annotations_dir / (speaker + ".json")
    parse_annotation_dest = tools.annotations_dir / (speaker + ".parse.json")
    peaks_dest = tools.peaks_dir / (speaker + ".json") if peaks_json else None
    transcript_dest = (
        tools.project_root / "imports" / "legacy" / speaker / transcript_csv.name
        if transcript_csv else None
    )

    plan: Dict[str, Any] = {
        "speaker": speaker,
        "workingWav": str(working_wav),
        "annotationJson": str(annotation_json),
        "peaksJson": str(peaks_json) if peaks_json else None,
        "transcriptCsv": str(transcript_csv) if transcript_csv else None,
        "audioDest": tools._display_readable_path(audio_dest),
        "annotationDest": tools._display_readable_path(annotation_dest),
        "peaksDest": tools._display_readable_path(peaks_dest) if peaks_dest else None,
        "transcriptDest": tools._display_readable_path(transcript_dest) if transcript_dest else None,
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

    _copy2_unless_samefile(working_wav, audio_dest)
    if peaks_json is not None and peaks_dest is not None:
        shutil.copy2(peaks_json, peaks_dest)
    if transcript_csv is not None and transcript_dest is not None:
        shutil.copy2(transcript_csv, transcript_dest)

    annotation_out = copy.deepcopy(annotation_payload)
    annotation_out["speaker"] = speaker
    annotation_out["source_audio"] = tools._display_readable_path(audio_dest)
    annotation_dest.write_text(json.dumps(annotation_out, indent=2, ensure_ascii=False), encoding="utf-8")
    existing_parse_payload = _read_json_file(parse_annotation_dest, None)
    parse_annotation_out = _merge_processed_annotation_for_parse_json(existing_parse_payload, annotation_out)
    parse_annotation_dest.write_text(json.dumps(parse_annotation_out, indent=2, ensure_ascii=False), encoding="utf-8")

    concept_total = _write_concepts_csv(tools, concepts)
    _write_project_json_for_processed_import(tools, speaker, project_id, language_code, concept_total)
    _write_source_index_for_processed_import(
        tools,
        speaker=speaker,
        audio_rel=tools._display_readable_path(audio_dest),
        duration_sec=duration_sec,
        file_size_bytes=audio_dest.stat().st_size,
        peaks_rel=tools._display_readable_path(peaks_dest) if peaks_dest else None,
        transcript_csv_rel=tools._display_readable_path(transcript_dest) if transcript_dest else None,
    )

    return {
        "ok": True,
        "dryRun": False,
        "plan": plan,
        "conceptCount": concept_total,
        "message": "Speaker {0!r} imported from processed artifacts.".format(speaker),
    }


def tool_onboard_speaker_import(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    speaker = tools._normalize_speaker(args.get("speaker"))

    source_wav_raw = str(args.get("sourceWav") or "").strip()
    if not source_wav_raw:
        raise ChatToolValidationError("sourceWav is required")

    wav_path = _resolve_onboard_source(tools, source_wav_raw, must_be_audio=True)

    csv_path: Optional[Path] = None
    source_csv_raw = str(args.get("sourceCsv") or "").strip()
    if source_csv_raw:
        csv_path = _resolve_onboard_source(tools, source_csv_raw, must_be_audio=False)

    dry_run = bool(args.get("dryRun"))
    is_primary_arg = args.get("isPrimary")

    source_index = _read_json_file(tools.source_index_path, {})
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

    target_dir = tools.audio_dir / "original" / speaker
    wav_dest = target_dir / wav_path.name
    csv_dest = (target_dir / csv_path.name) if csv_path else None

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
        "wavDest": tools._display_readable_path(wav_dest),
        "csvDest": tools._display_readable_path(csv_dest) if csv_dest else None,
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

    if tools._onboard_speaker is None:
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
        callback_result = tools._onboard_speaker(speaker, wav_path, csv_path, is_primary)
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


SPEAKER_IMPORT_TOOL_HANDLERS = {
    "onboard_speaker_import": tool_onboard_speaker_import,
    "import_processed_speaker": tool_import_processed_speaker,
    "csv_only_reimport": tool_csv_only_reimport,
    "revert_csv_reimport": tool_revert_csv_reimport,
}
