from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from ..chat_tools import (
    ANNOTATION_FILENAME_SUFFIX,
    ChatToolError,
    ChatToolExecutionError,
    ChatToolSpec,
    _concept_sort_key,
    _project_loaded_condition,
    _read_json_file,
    _tool_condition,
    cognate_compute_module,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


EXPORT_TOOL_NAMES = (
    "export_annotations_csv",
    "export_lingpy_tsv",
    "export_nexus",
    "export_annotations_elan",
    "export_annotations_textgrid",
)


EXPORT_TOOL_SPECS: Dict[str, ChatToolSpec] = {
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
}


def export_annotations_csv(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
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
                rows = _collect_all_rows(tools.annotations_dir)
                _sort_rows_all(rows)
                csv_content = _rows_to_csv_string(rows)
            else:
                sp = tools._normalize_speaker(speaker_raw)
                ann_path = tools.annotations_dir / "{0}{1}".format(sp, ANNOTATION_FILENAME_SUFFIX)
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

        out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(csv_content, encoding="utf-8-sig")
        return {
            "success": True,
            "outputPath": str(out_path),
            "lines": len(csv_content.splitlines()),
        }


def export_lingpy_tsv(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
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
                        tools.enrichments_path, tools.annotations_dir, tmp_path
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

            out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            count = cognate_compute_module.export_wordlist_tsv(
                tools.enrichments_path, tools.annotations_dir, out_path
            )
            return {"success": True, "outputPath": str(out_path), "rowCount": count}
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("LingPy TSV export failed: {0}".format(exc)) from exc


def export_nexus(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Build NEXUS matrix via _build_nexus_text(). Preview = first 2000 chars; write requires outputPath."""
        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        try:
            nexus_text = build_nexus_text(tools)
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

        out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(nexus_text, encoding="utf-8")
        return {"success": True, "outputPath": str(out_path), "totalChars": len(nexus_text)}


def build_nexus_text(tools: "ParseChatTools") -> str:
        """Build NEXUS cognate-character matrix (mirrors server._api_get_export_nexus)."""
        enrichments = _read_json_file(tools.enrichments_path, {})
        overrides = enrichments.get("manual_overrides") or {}
        override_sets = overrides.get("cognate_sets") if isinstance(overrides, dict) else None
        auto_sets = enrichments.get("cognate_sets") if isinstance(enrichments, dict) else None
        override_sets = override_sets if isinstance(override_sets, dict) else {}
        auto_sets = auto_sets if isinstance(auto_sets, dict) else {}

        speakers_set: set = set()
        project_payload = _read_json_file(tools.project_json_path, {})
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


def export_annotations_elan(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Export annotation to ELAN .eaf XML. Preview = first 2000 chars; write requires outputPath."""
        try:
            from elan_export import annotations_to_elan_str, export_elan  # type: ignore[import]
        except Exception as exc:
            raise ChatToolExecutionError("elan_export is not importable: {0}".format(exc))

        speaker = tools._normalize_speaker(args.get("speaker"))
        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        ann_path = tools.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)
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
            out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            export_elan(data, out_path, speaker)
            return {"success": True, "outputPath": str(out_path)}
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("ELAN export failed: {0}".format(exc)) from exc


def export_annotations_textgrid(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Export annotation to Praat TextGrid. Preview = first 2000 chars; write requires outputPath."""
        try:
            from textgrid_io import annotations_to_textgrid_str, write_textgrid  # type: ignore[import]
        except Exception as exc:
            raise ChatToolExecutionError("textgrid_io is not importable: {0}".format(exc))

        speaker = tools._normalize_speaker(args.get("speaker"))
        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        ann_path = tools.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)
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
            out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            write_textgrid(data, out_path, speaker)
            return {"success": True, "outputPath": str(out_path)}
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("TextGrid export failed: {0}".format(exc)) from exc


EXPORT_TOOL_HANDLERS = {
    "export_annotations_csv": export_annotations_csv,
    "export_lingpy_tsv": export_lingpy_tsv,
    "export_nexus": export_nexus,
    "export_annotations_elan": export_annotations_elan,
    "export_annotations_textgrid": export_annotations_textgrid,
}


__all__ = [
    "EXPORT_TOOL_NAMES",
    "EXPORT_TOOL_SPECS",
    "EXPORT_TOOL_HANDLERS",
    "build_nexus_text",
    "export_annotations_csv",
    "export_lingpy_tsv",
    "export_nexus",
    "export_annotations_elan",
    "export_annotations_textgrid",
]
