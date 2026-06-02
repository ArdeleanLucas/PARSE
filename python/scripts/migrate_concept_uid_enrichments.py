#!/usr/bin/env python3
"""Dry-run/apply MC-458-E parse-enrichments uid-key migration.

Examples:
  PYTHONPATH=python python3 python/scripts/migrate_concept_uid_enrichments.py --workspace /path/to/workspace
  PYTHONPATH=python python3 python/scripts/migrate_concept_uid_enrichments.py --workspace /path/to/workspace --execute --report /tmp/report.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migration.concept_uid_enrichments import migrate_uid_enrichment_keys  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-key parse-enrichments.json decisions from row/bundle keys to concept_identity uid. Dry-run by default."
    )
    parser.add_argument("--workspace", required=True, help="Workspace containing concepts.csv and parse-enrichments.json")
    parser.add_argument("--execute", action="store_true", help="Write parse-enrichments.json after creating a backup")
    parser.add_argument("--report", help="Optional JSON report path; stdout is always written")
    args = parser.parse_args(argv)

    report = migrate_uid_enrichment_keys(pathlib.Path(args.workspace), execute=bool(args.execute))
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        report_path = pathlib.Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
