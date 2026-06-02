#!/usr/bin/env python3
"""Audit and optionally repair survey-overlap cross-survey link integrity.

Dry-run examples:
  PYTHONPATH=python python3 python/scripts/audit_survey_overlap_links.py --workspace /path/to/workspace
  PYTHONPATH=python python3 python/scripts/audit_survey_overlap_links.py --workspace /path/to/workspace --report /tmp/report.json

Curated repair examples:
  PYTHONPATH=python python3 python/scripts/audit_survey_overlap_links.py --workspace /path/to/workspace --apply-fixes fixes.json
  PYTHONPATH=python python3 python/scripts/audit_survey_overlap_links.py --workspace /path/to/workspace --apply-fixes fixes.json --execute
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from survey_overlap_integrity import apply_survey_overlap_link_fixes, audit_survey_overlap_links  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit survey-overlap.json concept_survey_links for gloss mismatch, dangling, and non-reciprocal links. Dry-run by default."
    )
    parser.add_argument("--workspace", required=True, help="Workspace containing concepts.csv and survey-overlap.json")
    parser.add_argument("--report", help="Optional JSON report path; stdout is always written")
    parser.add_argument("--apply-fixes", help="Optional curated JSON fixes map: {concept_id: {survey: item_or_null}}")
    parser.add_argument("--execute", action="store_true", help="Apply --apply-fixes after creating a timestamped backup")
    args = parser.parse_args(argv)

    workspace = pathlib.Path(args.workspace)
    if args.apply_fixes:
        report = {
            "audit_before": audit_survey_overlap_links(workspace),
            "fixes": apply_survey_overlap_link_fixes(workspace, pathlib.Path(args.apply_fixes), execute=bool(args.execute)),
        }
    else:
        report = audit_survey_overlap_links(workspace)

    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        report_path = pathlib.Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
