#!/usr/bin/env python3
"""Migrate or verify PARSE workspace concept suffix pollution.

Usage:
    python3 python/scripts/migrate_concept_suffix_pollution.py --workspace /path/to/workspace [--dry-run]
    python3 python/scripts/migrate_concept_suffix_pollution.py --workspace /path/to/workspace --verify-only

This script does not run automatically. Stop PARSE before applying it to a real
workspace so concepts.csv, annotation JSON, and parse-tags.json cannot be
written concurrently by the server.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Support direct execution as ``python3 python/scripts/<script>.py`` from a
# checkout root as requested by the handoff, in addition to ``PYTHONPATH=python
# python3 -m scripts.migrate_concept_suffix_pollution``.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_ROOT = _REPO_ROOT / "python"
for _path in (str(_REPO_ROOT), str(_PYTHON_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from python.migration.concept_suffix_pollution import (  # noqa: E402
    audit_text_vs_concept_en,
    run_migration,
    validate_cross_survey_links,
    verify_post_migration,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path, help="PARSE workspace root containing concepts.csv.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned changes without writing files or backups.")
    parser.add_argument("--verify-only", action="store_true", help="Run verification/audit checks without migration writes.")
    return parser.parse_args(argv)


def _print_list(title: str, values: list[str]) -> None:
    print(f"{title}: {len(values)}")
    for value in values:
        print(f"  - {value}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.verify_only:
        post_violations = verify_post_migration(args.workspace)
        link_violations = validate_cross_survey_links(args.workspace)
        text_inconsistencies = audit_text_vs_concept_en(args.workspace)
        _print_list("post_migration_violations", post_violations)
        _print_list("cross_survey_link_violations", link_violations)
        _print_list("text_vs_concept_en_inconsistencies", text_inconsistencies)
        return 0 if not (post_violations or link_violations or text_inconsistencies) else 1

    result = run_migration(args.workspace, dry_run=args.dry_run)
    print(result.summary())
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
