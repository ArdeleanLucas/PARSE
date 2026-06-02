#!/usr/bin/env python3
"""Migrate PARSE concept-decision keys off survey-local ``source_item``.

Usage:
    python3 python/scripts/migrate_concept_key_namespace.py --workspace /path [--execute] [--report out.json]

Dry-run by default (reports planned changes, writes nothing). Pass ``--execute``
to apply. Stop the PARSE server before ``--execute`` so parse-enrichments.json
cannot be written concurrently by the server.

See docs/data-persistence-model.md for the overall persistence/keying model and
docs/reports/2026-06-02-concept-key-namespace-collision.md for the rationale.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_ROOT = _REPO_ROOT / "python"
for _path in (str(_REPO_ROOT), str(_PYTHON_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from python.migration.concept_key_namespace import migrate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--execute", action="store_true", help="apply changes (default: dry-run)")
    parser.add_argument("--report", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)

    report = migrate(args.workspace, execute=args.execute)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["verification_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
