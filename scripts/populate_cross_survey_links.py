#!/usr/bin/env python3
"""Populate survey-overlap.json concept_survey_links from a reference lexeme CSV.

Dry-run is the default. Pass --apply to write only the survey-overlap sidecar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from cross_survey_links import (  # noqa: E402
    compute_cross_survey_link_patch,
    patch_from_cross_survey_link_summary,
)
from survey_overlap import load_survey_overlap_state, update_survey_overlap_state  # noqa: E402


def _default_workspace() -> Path:
    return Path("~/parse-workspace").expanduser()


def _sidecar_diff(before: dict[str, Any], after: dict[str, Any], patch: dict[str, dict[str, str]]) -> dict[str, Any]:
    concept_ids = sorted(patch)
    return {
        "before": {concept_id: before.get(concept_id, {}) for concept_id in concept_ids},
        "after": {concept_id: after.get(concept_id, {}) for concept_id in concept_ids},
        "added": patch,
    }


def apply_cross_survey_link_patch(
    workspace: Path,
    summary: dict[str, list[dict[str, object]]],
) -> dict[str, Any]:
    patch = patch_from_cross_survey_link_summary(summary)
    before_state = load_survey_overlap_state(workspace)
    before_links = dict(before_state.get("concept_survey_links") or {})
    if patch:
        after_state = update_survey_overlap_state(workspace, {"concept_survey_links": patch})
    else:
        after_state = before_state
    after_links = dict(after_state.get("concept_survey_links") or {})
    return _sidecar_diff(before_links, after_links, patch)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="Reference lexeme CSV path with source,id,lexeme columns.")
    parser.add_argument(
        "--workspace",
        default=str(_default_workspace()),
        help="Workspace root containing concepts.csv; defaults to ~/parse-workspace.",
    )
    parser.add_argument("--apply", action="store_true", help="Write survey-overlap.json. Without this flag, dry-run only.")
    parser.add_argument(
        "--single-word-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Restrict matching to concepts with no spaces, commas, or parentheses (default: true).",
    )
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    reference = Path(args.reference).expanduser().resolve()
    summary = compute_cross_survey_link_patch(workspace, reference, single_word_only=bool(args.single_word_only))
    payload: dict[str, Any] = dict(summary)
    if args.apply:
        payload["sidecar_diff"] = apply_cross_survey_link_patch(workspace, summary)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
