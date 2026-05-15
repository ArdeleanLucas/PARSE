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
    apply_cross_survey_link_patch,
    compute_cross_survey_link_patch,
)


def _default_workspace() -> Path:
    return Path("~/parse-workspace").expanduser()



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
        "--replace",
        action="store_true",
        help="Reset concept_survey_links before applying. Default merges instead.",
    )
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
        payload["sidecar_diff"] = apply_cross_survey_link_patch(workspace, summary, replace=bool(args.replace))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
