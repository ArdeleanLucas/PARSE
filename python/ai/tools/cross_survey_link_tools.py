from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from ..chat_tools import ChatToolSpec

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


CROSS_SURVEY_LINK_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "populate_cross_survey_links": ChatToolSpec(
        name="populate_cross_survey_links",
        description=(
            "Populate survey-overlap.json concept_survey_links from a reference lexeme CSV "
            "with source,id,lexeme columns. The tool is dry-run first: dryRun=true previews "
            "matched links, conflicts, and skipped multi-word concepts; dryRun=false writes "
            "only the survey-overlap sidecar after explicit confirmation."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["referencePath", "dryRun"],
            "properties": {
                "referencePath": {"type": "string", "minLength": 1, "maxLength": 1024},
                "dryRun": {"type": "boolean"},
                "singleWordOnly": {"type": "boolean", "default": True},
            },
        },
        mutability="mutating",
        supports_dry_run=True,
        dry_run_parameter="dryRun",
    )
}


def _resolve_reference_path(tools: "ParseChatTools", raw_path: str) -> Path:
    if hasattr(tools, "_resolve_readable_path"):
        return tools._resolve_readable_path(raw_path)  # noqa: SLF001 - mirrors existing tool delegation pattern.
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = tools.project_root / candidate
    return candidate.resolve()


def tool_populate_cross_survey_links(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    from cross_survey_links import compute_cross_survey_link_patch, patch_from_cross_survey_link_summary
    from survey_overlap import load_survey_overlap_state, update_survey_overlap_state

    raw_reference = str(args.get("referencePath") or "").strip()
    if not raw_reference:
        return {"ok": False, "error": "referencePath is required"}
    reference_path = _resolve_reference_path(tools, raw_reference)
    if not reference_path.exists():
        return {"ok": False, "error": "Reference CSV not found: {0}".format(reference_path)}

    dry_run = bool(args.get("dryRun"))
    single_word_only = bool(args.get("singleWordOnly", True))
    summary = compute_cross_survey_link_patch(tools.project_root, reference_path, single_word_only=single_word_only)
    payload: Dict[str, Any] = {"dryRun": dry_run, **summary}
    if dry_run:
        return payload

    patch = patch_from_cross_survey_link_summary(summary)
    before_state = load_survey_overlap_state(tools.project_root)
    before_links = dict(before_state.get("concept_survey_links") or {})
    if patch:
        after_state = update_survey_overlap_state(tools.project_root, {"concept_survey_links": patch})
    else:
        after_state = before_state
    after_links = dict(after_state.get("concept_survey_links") or {})
    payload["sidecar_diff"] = {
        "before": {concept_id: before_links.get(concept_id, {}) for concept_id in sorted(patch)},
        "after": {concept_id: after_links.get(concept_id, {}) for concept_id in sorted(patch)},
        "added": patch,
    }
    return payload


CROSS_SURVEY_LINK_TOOL_HANDLERS = {
    "populate_cross_survey_links": tool_populate_cross_survey_links,
}
