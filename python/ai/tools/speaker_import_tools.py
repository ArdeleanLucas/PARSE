from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from ..chat_tools import (
    ONBOARD_AUDIO_EXTENSIONS,
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
    import csv as _csv

    merged: Dict[str, str] = {
        item["id"]: item["label"]
        for item in tools._load_project_concepts()
        if item.get("id") and item.get("label")
    }
    for item in concepts:
        concept_id = _normalize_space(item.get("id"))
        label = _normalize_space(item.get("label"))
        if concept_id and label:
            merged[concept_id] = label

    ordered = sorted(merged.items(), key=lambda kv: _concept_sort_key(kv[0]))
    concepts_path = tools.project_root / "concepts.csv"
    concepts_path.parent.mkdir(parents=True, exist_ok=True)
    with open(concepts_path, "w", newline="", encoding="utf-8") as handle:
        writer = _csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        for concept_id, label in ordered:
            writer.writerow({"id": concept_id, "concept_en": label})
    return len(ordered)


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

    shutil.copy2(working_wav, audio_dest)
    if peaks_json is not None and peaks_dest is not None:
        shutil.copy2(peaks_json, peaks_dest)
    if transcript_csv is not None and transcript_dest is not None:
        shutil.copy2(transcript_csv, transcript_dest)

    annotation_out = copy.deepcopy(annotation_payload)
    annotation_out["speaker"] = speaker
    annotation_out["source_audio"] = tools._display_readable_path(audio_dest)
    annotation_dest.write_text(json.dumps(annotation_out, indent=2, ensure_ascii=False), encoding="utf-8")

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
}
