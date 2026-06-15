from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

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
    "export_review_data",
    "export_beast2_xml",
    "export_concept_appendix_md",
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
                            "conceptTag": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "If set, restrict the matrix to this concept tag (e.g. custom-sk-concept-list, the thesis tag) and fold survey-overlap duplicate concept ids into one canonical character.",
                            },
                            "consolidate": {"type": "boolean", "description": "Fold survey-overlap duplicate concept ids into one canonical character (implied when conceptTag is set)."},
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
                            "conceptTag": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "If set, restrict the matrix to this concept tag (e.g. custom-sk-concept-list, the thesis tag) and fold survey-overlap duplicate concept ids into one canonical character.",
                            },
                            "consolidate": {"type": "boolean", "description": "Fold survey-overlap duplicate concept ids into one canonical character (implied when conceptTag is set)."},
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
    "export_beast2_xml": ChatToolSpec(
                    name="export_beast2_xml",
                    description=(
                        "Export a runnable BEAST2 (v2.7) XML analysis from the cognate-character matrix "
                        "for direct phylogenetic inference — no BEAUti step required. Uses a binary "
                        "substitution model, Yule tree prior, and strict clock. Supports conceptTag / "
                        "consolidate exactly like export_nexus. Without outputPath returns a preview "
                        "(first 2000 chars); with outputPath writes inside the project. Run the result "
                        "with BEAST2 (`beast <file>.xml`)."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "outputPath": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "description": "Project-relative or absolute path inside project root (e.g. exports/beast2/analysis.xml).",
                            },
                            "conceptTag": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "If set, restrict to this concept tag and fold survey-overlap duplicate concept ids into one canonical character.",
                            },
                            "consolidate": {"type": "boolean", "description": "Fold survey-overlap duplicate concept ids (implied when conceptTag is set)."},
                            "chainLength": {
                                "type": "integer",
                                "minimum": 1000,
                                "maximum": 1000000000,
                                "description": "MCMC chain length (default 10000000). Loggers sample ~200 times across the chain.",
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
                            "The project must contain enough cognate/enrichment data to build a character matrix.",
                            kind="project_state",
                        ),
                    ),
                    postconditions=(
                        _tool_condition(
                            "export_file_written",
                            "When dryRun=false and outputPath is provided, the BEAST2 XML is written inside the project.",
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
    "export_review_data": ChatToolSpec(
                    name="export_review_data",
                    description=(
                        "Export a PARSE workspace to the legacy review_tool v4.1 schema "
                        "(thesis-tag filtered, optional ffmpeg-clipped audio, analytical fields, "
                        "and contact-language reference forms). Mirrors python/export_review_data.py."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["workspace", "out"],
                        "properties": {
                            "workspace": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 1024,
                                "description": "Absolute path to the PARSE workspace root.",
                            },
                            "out": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 1024,
                                "description": "Output directory for review_data.json, timestamps, and optional audio clips.",
                            },
                            "tag_id": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "parse-tags.json tag id to filter concepts by (default: custom-sk-concept-list).",
                            },
                            "contact_config": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 1024,
                                "description": "Path to sil_contact_languages.json. Defaults to <repo>/config/sil_contact_languages.json.",
                            },
                            "speakers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional speaker subset; project.json order is preserved and unknown speakers return invalid_args.",
                            },
                            "skip_audio": {
                                "type": "boolean",
                                "description": "Skip ffmpeg audio clipping; emits review_data.json and timestamps only.",
                            },
                        },
                    },
                    mutability="mutating",
                    preconditions=(
                        _project_loaded_condition(),
                        _tool_condition(
                            "review_workspace_available",
                            "The requested workspace must contain project.json, concepts.csv, and annotations suitable for review_tool export.",
                            kind="project_state",
                        ),
                    ),
                    postconditions=(
                        _tool_condition(
                            "review_data_export_written",
                            "The tool writes review_data.json plus timestamp CSVs and optional audio clips to the requested output directory.",
                            kind="filesystem_write",
                        ),
                    ),
                ),
    "export_concept_appendix_md": ChatToolSpec(
                    name="export_concept_appendix_md",
                    description=(
                        "Export a per-concept markdown appendix (per-speaker IPA/ORTH forms per "
                        "survey concept), optionally annotated with the cognate-set decisions made "
                        "in compare mode (cognate-set letters, accepted/split/merge verdict, "
                        "borrowing markers, excluded speakers, and a speaker x concept cognate "
                        "matrix). Language/survey-neutral. Without outputPath returns the full "
                        "markdown; with outputPath writes a .md file inside the project."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "tagId": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "parse-tags.json tag id to filter concepts by (default: custom-sk-concept-list).",
                            },
                            "includeCognates": {
                                "type": "boolean",
                                "description": "Include cognate-set decisions (default true). When false, emits the plain forms-only appendix.",
                            },
                            "speakers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional speaker subset; project.json order is preserved and unknown speakers return invalid_args. Omit or pass an empty list for all speakers.",
                            },
                            "conceptIds": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional concept-id subset (concepts.csv ids), e.g. the caller's currently-filtered concept menu. When provided, the export covers exactly these concepts instead of the whole tag. Omit or pass an empty list to use tagId.",
                            },
                            "outputPath": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "description": "Project-relative or absolute path inside project root (e.g. exports/concept-appendix.md).",
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
                            "review_workspace_available",
                            "The project must contain concepts.csv and tag-filtered annotations to build the appendix.",
                            kind="project_state",
                        ),
                    ),
                    postconditions=(
                        _tool_condition(
                            "export_file_written",
                            "When dryRun=false and outputPath is provided, the requested markdown file is written inside the project.",
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


def lingpy_tsv_readiness(tsv_text: str) -> List[str]:
        """Return BEAST2-readiness warnings for a LingPy wordlist TSV.

        An empty list means no readiness problems were detected. The file
        write still succeeds; these warnings only flag that the artifact is
        not phylogenetically informative.
        """
        warnings: List[str] = []
        lines = [line for line in tsv_text.splitlines() if line.strip()]
        if len(lines) < 2:
            warnings.append("Wordlist has no data rows: no exportable forms were found.")
            return warnings

        header = lines[0].split("\t")
        try:
            cogid_idx = header.index("COGID")
        except ValueError:
            return warnings

        cogid_values = {
            row[cogid_idx].strip()
            for row in (line.split("\t") for line in lines[1:])
            if len(row) > cogid_idx
        }
        if cogid_values and cogid_values <= {"0", ""}:
            warnings.append(
                "All COGID values are 0: no cognate sets are assigned, so this "
                "wordlist is not phylogenetically informative for BEAST2."
            )
        return warnings


def nexus_readiness(nexus_text: str) -> List[str]:
        """Return BEAST2-readiness warnings for a NEXUS character matrix."""
        import re

        warnings: List[str] = []

        nchar_match = re.search(r"NCHAR\s*=\s*(\d+)", nexus_text, re.IGNORECASE)
        nchar = int(nchar_match.group(1)) if nchar_match else 0
        if nchar == 0:
            warnings.append(
                "NEXUS matrix has no characters (NCHAR=0): there are no cognate "
                "sets to analyze."
            )
            return warnings

        matrix_match = re.search(r"MATRIX\s*(.*?);", nexus_text, re.DOTALL | re.IGNORECASE)
        if not matrix_match:
            return warnings

        # NOTE: '?' is a valid NEXUS state (missing data), and comparative
        # wordlists are routinely sparse, so per-cell missingness is NOT flagged.
        # Only a *fully* missing taxon (no forms for any concept) is a real no-go.
        fully_missing: List[str] = []
        for raw_row in matrix_match.group(1).splitlines():
            parts = raw_row.split()
            if len(parts) < 2:
                continue
            taxon, seq = parts[0], parts[1]
            if seq and all(ch == "?" for ch in seq):
                fully_missing.append(taxon)

        if fully_missing:
            warnings.append(
                "{0} taxa have no character data (all '?'): {1}.".format(
                    len(fully_missing), ", ".join(fully_missing)
                )
            )
        return warnings


def _consolidated_sets(tools: "ParseChatTools", concept_tag: str) -> Tuple[Any, Dict[str, Any], Dict[str, str], List[str], Any]:
        """Build the consolidated (canonical-collapsed) cognate sets + speakers.

        Reuses ``compare.consolidated_matrix`` so survey-overlap duplicate
        concept ids fold into one canonical character. ``concept_tag`` (e.g. the
        thesis tag) restricts the matrix to that tag's concepts.

        Note: this reads concepts.csv + enrichments + tags + project.json on each
        call. ``export_complete_lingpy_dataset`` therefore reads them twice (once
        for the TSV stage, once for NEXUS). That is acceptable at current corpus
        sizes; revisit with a cached resolve if concepts.csv grows large.
        """
        import csv as _csv
        from compare.consolidated_matrix import (
            build_consolidated_cognate_sets,
            tag_concept_ids,
        )

        concepts_path = tools.project_root / "concepts.csv"
        concepts_rows: List[Dict[str, Any]] = []
        if concepts_path.exists():
            with concepts_path.open(encoding="utf-8", newline="") as handle:
                concepts_rows = list(_csv.DictReader(handle))

        enrichments = _read_json_file(tools.enrichments_path, {})
        allowed_ids = None
        if concept_tag:
            tags_payload = _read_json_file(tools.tags_path, [])
            allowed_ids = tag_concept_ids(tags_payload, concept_tag)

        cognate_sets, meta, id_to_key = build_consolidated_cognate_sets(
            concepts_rows, enrichments, allowed_ids
        )

        # Distinguish "tag matched nothing" from "tag has no cognate data": an
        # unknown / empty conceptTag otherwise looks like a silent empty export.
        if concept_tag and not allowed_ids:
            meta.setdefault("warnings", []).insert(
                0,
                "conceptTag '{0}' matched 0 concepts (unknown or empty tag); "
                "the export is empty.".format(concept_tag),
            )

        project_payload = _read_json_file(tools.project_json_path, {})
        sp_block = project_payload.get("speakers") if isinstance(project_payload, dict) else None
        if isinstance(sp_block, dict):
            speakers = [str(s) for s in sp_block.keys() if str(s).strip()]
        elif isinstance(sp_block, list):
            speakers = [str(s) for s in sp_block if str(s).strip()]
        else:
            speakers = []
        return cognate_sets, meta, id_to_key, speakers, allowed_ids


def _consolidation_summary(meta: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "concept_count": meta.get("concept_count"),
            "character_count": meta.get("character_count"),
            "collapsed_groups": len(meta.get("collapsed") or []),
            "needs_recluster_groups": len(meta.get("needs_recluster") or []),
        }


def export_lingpy_tsv(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Export LingPy wordlist TSV. Preview = first 20 lines via temp file; write requires outputPath."""
        if cognate_compute_module is None:
            raise ChatToolExecutionError("cognate_compute is not importable")

        concept_tag = str(args.get("conceptTag") or "").strip()
        consolidate = bool(args.get("consolidate")) or bool(concept_tag)

        import os as _os
        import tempfile

        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        if consolidate:
            try:
                from compare.consolidated_matrix import build_wordlist_rows, wordlist_rows_to_tsv
                cognate_sets, meta, id_to_key, _speakers, allowed_ids = _consolidated_sets(tools, concept_tag)
                canonical_lexemes = (_read_json_file(tools.enrichments_path, {}).get("manual_overrides") or {}).get("canonical_lexemes")
                rows = build_wordlist_rows(tools.annotations_dir, cognate_sets, id_to_key, allowed_ids, canonical_lexemes)
                content = wordlist_rows_to_tsv(rows)
            except ChatToolError:
                raise
            except Exception as exc:
                raise ChatToolExecutionError("Consolidated LingPy TSV export failed: {0}".format(exc)) from exc

            warnings = lingpy_tsv_readiness(content) + list(meta.get("warnings") or [])
            summary = _consolidation_summary(meta)
            if dry_run or not output_path_str:
                lines = content.splitlines()
                return {
                    "readOnly": True, "previewOnly": True,
                    "previewLines": "\n".join(lines[:20]), "totalLines": len(lines),
                    "truncated": len(lines) > 20, "rowCount": len(rows),
                    "consolidated": True, "conceptTag": concept_tag or None,
                    "consolidation": summary, "warnings": warnings, "beast2_ready": not warnings,
                }
            out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            return {
                "success": True, "outputPath": str(out_path), "rowCount": len(rows),
                "consolidated": True, "conceptTag": concept_tag or None,
                "consolidation": summary, "warnings": warnings, "beast2_ready": not warnings,
            }

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
                warnings = lingpy_tsv_readiness(content)
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "previewLines": "\n".join(lines[:20]),
                    "totalLines": len(lines),
                    "truncated": len(lines) > 20,
                    "rowCount": count,
                    "warnings": warnings,
                    "beast2_ready": not warnings,
                }

            out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            count = cognate_compute_module.export_wordlist_tsv(
                tools.enrichments_path, tools.annotations_dir, out_path
            )
            warnings = lingpy_tsv_readiness(out_path.read_text(encoding="utf-8"))
            return {
                "success": True,
                "outputPath": str(out_path),
                "rowCount": count,
                "warnings": warnings,
                "beast2_ready": not warnings,
            }
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("LingPy TSV export failed: {0}".format(exc)) from exc


def _nexus_text_and_meta(tools: "ParseChatTools", args: Dict[str, Any]) -> Tuple[str, bool, str, Optional[Dict[str, Any]], List[str]]:
        """Build the NEXUS matrix text honoring conceptTag/consolidate.

        Returns ``(nexus_text, consolidate, concept_tag, summary, extra_warnings)``.
        Shared by ``export_nexus`` and ``export_beast2_xml`` so they always agree
        on the underlying character matrix.
        """
        concept_tag = str(args.get("conceptTag") or "").strip()
        consolidate = bool(args.get("consolidate")) or bool(concept_tag)
        summary: Optional[Dict[str, Any]] = None
        extra_warnings: List[str] = []
        if consolidate:
            from compare.consolidated_matrix import build_nexus_from_sets
            cognate_sets, meta, _id_to_key, speakers, _allowed = _consolidated_sets(tools, concept_tag)
            nexus_text = build_nexus_from_sets(cognate_sets, speakers)
            summary = _consolidation_summary(meta)
            extra_warnings = list(meta.get("warnings") or [])
        else:
            nexus_text = build_nexus_text(tools)
        return nexus_text, consolidate, concept_tag, summary, extra_warnings


def export_nexus(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Build NEXUS matrix via _build_nexus_text(). Preview = first 2000 chars; write requires outputPath."""
        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))

        try:
            nexus_text, consolidate, concept_tag, summary, extra_warnings = _nexus_text_and_meta(tools, args)
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("NEXUS build failed: {0}".format(exc)) from exc

        warnings = nexus_readiness(nexus_text) + extra_warnings
        base: Dict[str, Any] = {
            "warnings": warnings,
            "beast2_ready": not warnings,
        }
        if consolidate:
            base.update({"consolidated": True, "conceptTag": concept_tag or None, "consolidation": summary})

        if dry_run or not output_path_str:
            base.update({
                "readOnly": True,
                "previewOnly": True,
                "preview": nexus_text[:2000],
                "truncated": len(nexus_text) > 2000,
                "totalChars": len(nexus_text),
            })
            return base

        out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(nexus_text, encoding="utf-8")
        base.update({"success": True, "outputPath": str(out_path), "totalChars": len(nexus_text)})
        return base


def export_beast2_xml(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Build a runnable BEAST 2.7 XML from the (optionally consolidated) cognate matrix.

        Wraps the same NEXUS character matrix as ``export_nexus`` into a
        self-contained BEAST2 analysis (binary model, Yule prior, strict clock),
        so the full PARSE -> BEAST2 chain needs no BEAUti step or external script.
        Preview = first 2000 chars; write requires outputPath.
        """
        from compare.beast2_xml import nexus_to_beast2_xml, DEFAULT_CHAIN_LENGTH

        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))
        raw_chain = args.get("chainLength")
        try:
            chain_length = DEFAULT_CHAIN_LENGTH if raw_chain in (None, "") else int(raw_chain)
        except (TypeError, ValueError):
            raise ChatToolExecutionError("chainLength must be an integer.")
        if chain_length < 1:
            raise ChatToolExecutionError("chainLength must be a positive integer.")

        try:
            nexus_text, consolidate, concept_tag, summary, extra_warnings = _nexus_text_and_meta(tools, args)
            xml_text = nexus_to_beast2_xml(nexus_text, chain_length=chain_length)
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("BEAST2 XML build failed: {0}".format(exc)) from exc

        # Readiness reflects the underlying matrix (an empty/uncoded matrix yields
        # a structurally-valid but uninformative analysis).
        warnings = nexus_readiness(nexus_text) + extra_warnings
        base: Dict[str, Any] = {
            "chainLength": chain_length,
            "warnings": warnings,
            "beast2_ready": not warnings,
            "note": "Run with BEAST2 (e.g. `beast <file>.xml`); outputs use the XML's basename.",
        }
        if consolidate:
            base.update({"consolidated": True, "conceptTag": concept_tag or None, "consolidation": summary})

        if dry_run or not output_path_str:
            base.update({
                "readOnly": True,
                "previewOnly": True,
                "preview": xml_text[:2000],
                "truncated": len(xml_text) > 2000,
                "totalChars": len(xml_text),
            })
            return base

        out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(xml_text, encoding="utf-8")
        base.update({"success": True, "outputPath": str(out_path), "totalChars": len(xml_text)})
        return base


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


def _review_export_invalid_args(message: str) -> Dict[str, Any]:
    return {"ok": False, "error": message, "error_kind": "invalid_args"}


def export_review_data(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Export a workspace to the legacy review_tool schema via the chat/MCP surface."""
    try:
        from export_review_data import (  # type: ignore[import]
            DEFAULT_TAG_ID,
            build_review_data,
            write_outputs,
        )
    except Exception as exc:
        raise ChatToolExecutionError("export_review_data is not importable: {0}".format(exc)) from exc

    workspace_raw = str(args.get("workspace") or "").strip()
    out_raw = str(args.get("out") or "").strip()
    if not workspace_raw:
        return _review_export_invalid_args("workspace is required")
    if not out_raw:
        return _review_export_invalid_args("out is required")

    workspace = Path(workspace_raw).expanduser().resolve()
    out_dir = Path(out_raw).expanduser().resolve()
    if not workspace.exists():
        return _review_export_invalid_args("workspace path does not exist: {0}".format(workspace_raw))

    tag_id = str(args.get("tag_id") or DEFAULT_TAG_ID).strip() or DEFAULT_TAG_ID
    contact_config_raw = str(args.get("contact_config") or "").strip()
    if contact_config_raw:
        contact_config = Path(contact_config_raw).expanduser().resolve()
    else:
        contact_config = None

    speakers_raw = args.get("speakers")
    speakers = None
    if isinstance(speakers_raw, list):
        speakers = [str(speaker).strip() for speaker in speakers_raw if str(speaker).strip()]

    try:
        review_data, clip_plan = build_review_data(
            workspace=workspace,
            tag_id=tag_id,
            contact_config=contact_config,
            speaker_filter=speakers,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _review_export_invalid_args(str(exc))
    except Exception as exc:
        raise ChatToolExecutionError("review_tool export failed: {0}".format(exc)) from exc

    try:
        summary = write_outputs(
            workspace=workspace,
            out_dir=out_dir,
            review_data=review_data,
            clip_plan=clip_plan,
            skip_audio=bool(args.get("skip_audio", False)),
        )
    except Exception as exc:
        raise ChatToolExecutionError("review_tool output write failed: {0}".format(exc)) from exc

    return {"ok": True, **summary}


def export_concept_appendix_md(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Build the per-concept markdown appendix (+ cognate decisions).

    Preview (no outputPath / dryRun) returns the full markdown; with outputPath writes a
    .md file inside the project. Workspace is always the active project root.
    """
    try:
        from concept_appendix import build_concept_appendix_markdown  # type: ignore[import]
    except Exception as exc:
        raise ChatToolExecutionError("concept_appendix is not importable: {0}".format(exc)) from exc

    tag_id_raw = str(args.get("tagId") or "").strip()
    include_cognates = bool(args.get("includeCognates", True))
    output_path_str = str(args.get("outputPath") or "").strip()
    dry_run = bool(args.get("dryRun", False))

    kwargs: Dict[str, Any] = {
        "workspace": tools.project_root,
        "include_cognates": include_cognates,
    }
    if tag_id_raw:
        kwargs["tag_id"] = tag_id_raw

    speakers_raw = args.get("speakers")
    if isinstance(speakers_raw, list):
        speakers = [str(s).strip() for s in speakers_raw if str(s).strip()]
        if speakers:
            kwargs["speaker_filter"] = speakers

    concept_ids_raw = args.get("conceptIds")
    if isinstance(concept_ids_raw, list):
        concept_ids = [str(c).strip() for c in concept_ids_raw if str(c).strip()]
        if concept_ids:
            kwargs["concept_ids"] = concept_ids

    try:
        result = build_concept_appendix_markdown(**kwargs)
    except (FileNotFoundError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "error_kind": "invalid_args"}
    except ChatToolError:
        raise
    except Exception as exc:
        raise ChatToolExecutionError("concept appendix export failed: {0}".format(exc)) from exc

    markdown = str(result.get("markdown") or "")
    if dry_run or not output_path_str:
        return {
            "readOnly": True,
            "previewOnly": True,
            "markdown": markdown,
            "concepts": result.get("concepts", 0),
            "speakers": result.get("speakers", 0),
            "includeCognates": include_cognates,
        }

    out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    return {
        "success": True,
        "outputPath": str(out_path),
        "concepts": result.get("concepts", 0),
        "speakers": result.get("speakers", 0),
        "bytes": len(markdown.encode("utf-8")),
    }


EXPORT_TOOL_HANDLERS = {
    "export_annotations_csv": export_annotations_csv,
    "export_lingpy_tsv": export_lingpy_tsv,
    "export_nexus": export_nexus,
    "export_beast2_xml": export_beast2_xml,
    "export_annotations_elan": export_annotations_elan,
    "export_annotations_textgrid": export_annotations_textgrid,
    "export_review_data": export_review_data,
    "export_concept_appendix_md": export_concept_appendix_md,
}


__all__ = [
    "EXPORT_TOOL_NAMES",
    "EXPORT_TOOL_SPECS",
    "EXPORT_TOOL_HANDLERS",
    "build_nexus_text",
    "lingpy_tsv_readiness",
    "nexus_readiness",
    "export_beast2_xml",
    "export_annotations_csv",
    "export_lingpy_tsv",
    "export_nexus",
    "export_annotations_elan",
    "export_annotations_textgrid",
    "export_review_data",
    "export_concept_appendix_md",
]
