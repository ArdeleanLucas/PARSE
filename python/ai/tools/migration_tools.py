from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict
import importlib

from ..chat_tools import ChatToolSpec, _project_loaded_condition, _tool_condition

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools

MIGRATION_TOOL_NAMES = ("migrate_concept_suffix_pollution",)

MIGRATION_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "migrate_concept_suffix_pollution": ChatToolSpec(
        name="migrate_concept_suffix_pollution",
        description=(
            "Migrate or verify PARSE concept identity suffix pollution per MC-418/#529. "
            "Builds a merge map, rewrites concepts.csv, annotations, and parse-tags.json with backups, "
            "and is idempotent: already-canonical workspaces return a no-op summary."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["workspace"],
            "properties": {
                "workspace": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2048,
                    "description": "Absolute or project-relative PARSE workspace root containing concepts.csv.",
                },
                "dryRun": {"type": "boolean", "description": "Preview migration only; no writes or backups."},
                "verifyOnly": {"type": "boolean", "description": "Run verification/audit checks without migration writes."},
            },
        },
        mutability="mutating",
        supports_dry_run=True,
        dry_run_parameter="dryRun",
        preconditions=(
            _project_loaded_condition(),
            _tool_condition(
                "workspace_contains_concepts_csv",
                "The workspace path must exist and contain the PARSE concepts.csv file.",
                kind="file_presence",
            ),
        ),
        postconditions=(
            _tool_condition(
                "concept_suffix_pollution_migration_verified",
                "The call returns migration counters plus post-migration verification/audit lists.",
                kind="project_state",
            ),
        ),
    ),
}


def tool_migrate_concept_suffix_pollution(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        migration_module = importlib.import_module("python.migration.concept_suffix_pollution")
    except ModuleNotFoundError:  # pragma: no cover - alternate script/PYTHONPATH shape
        migration_module = importlib.import_module("migration.concept_suffix_pollution")
    audit_text_vs_concept_en = migration_module.audit_text_vs_concept_en
    run_migration = migration_module.run_migration
    validate_cross_survey_links = migration_module.validate_cross_survey_links
    verify_post_migration = migration_module.verify_post_migration

    workspace_raw = str(args.get("workspace") or "").strip()
    if not workspace_raw:
        return _invalid_args("workspace is required")
    workspace = Path(workspace_raw).expanduser()
    if not workspace.is_absolute():
        workspace = tools.project_root / workspace
    workspace = workspace.resolve()
    if not workspace.exists():
        return _invalid_args(f"workspace path does not exist: {workspace_raw}")
    if not (workspace / "concepts.csv").exists():
        return _invalid_args(f"workspace concepts.csv does not exist: {workspace / 'concepts.csv'}")

    verify_only = bool(args.get("verifyOnly", False))
    if verify_only:
        post_violations = verify_post_migration(workspace)
        link_violations = validate_cross_survey_links(workspace)
        text_inconsistencies = audit_text_vs_concept_en(workspace)
        ok = not (post_violations or link_violations or text_inconsistencies)
        return {
            "ok": ok,
            "verifyOnly": True,
            "workspace": str(workspace),
            "postMigrationViolations": post_violations,
            "crossSurveyLinkViolations": link_violations,
            "textVsConceptEnInconsistencies": text_inconsistencies,
            "post_migration_violations": post_violations,
            "cross_survey_link_violations": link_violations,
            "text_vs_concept_en_inconsistencies": text_inconsistencies,
        }

    dry_run = bool(args.get("dryRun", False))
    result = run_migration(workspace, dry_run=dry_run)
    return {
        "ok": result.success,
        "workspace": str(workspace),
        "dryRun": dry_run,
        "dry_run": dry_run,
        "alreadyCanonical": result.already_canonical,
        "already_canonical": result.already_canonical,
        "mergeMap": result.merge_map,
        "merge_map": result.merge_map,
        "mergeMapCount": len(result.merge_map),
        "merge_map_count": len(result.merge_map),
        "rowsBefore": result.rows_before,
        "rows_before": result.rows_before,
        "rowsAfter": result.rows_after,
        "rows_after": result.rows_after,
        "annotationsRewritten": result.annotations_rewritten,
        "annotations_rewritten": result.annotations_rewritten,
        "intervalsRekeyed": result.intervals_rekeyed,
        "intervals_rekeyed": result.intervals_rekeyed,
        "textFieldsStripped": result.text_fields_stripped,
        "text_fields_stripped": result.text_fields_stripped,
        "conceptTagsRekeyed": result.concept_tags_rekeyed,
        "concept_tags_rekeyed": result.concept_tags_rekeyed,
        "parseTagsRekeyed": result.parse_tags_rekeyed,
        "parse_tags_rekeyed": result.parse_tags_rekeyed,
        "backups": result.backups_created,
        "errors": result.errors,
        "postMigrationViolations": result.post_migration_violations,
        "crossSurveyLinkViolations": result.cross_survey_link_violations,
        "textVsConceptEnInconsistencies": result.text_vs_concept_en_inconsistencies,
        "post_migration_violations": result.post_migration_violations,
        "cross_survey_link_violations": result.cross_survey_link_violations,
        "text_vs_concept_en_inconsistencies": result.text_vs_concept_en_inconsistencies,
    }


def _invalid_args(message: str) -> Dict[str, Any]:
    return {"ok": False, "error": message, "errorKind": "invalid_args", "error_kind": "invalid_args"}


MIGRATION_TOOL_HANDLERS = {
    "migrate_concept_suffix_pollution": tool_migrate_concept_suffix_pollution,
}

__all__ = [
    "MIGRATION_TOOL_NAMES",
    "MIGRATION_TOOL_SPECS",
    "MIGRATION_TOOL_HANDLERS",
    "tool_migrate_concept_suffix_pollution",
]
