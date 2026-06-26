#!/usr/bin/env python3
"""Collapse legacy row-id enrichment keys into their concept uid (data repair).

After the MC-458 uid migration, a ``parse-enrichments.json`` can carry the same
concept under BOTH a legacy row-id key (``"517"``) and its concept uid
(``"c-517"``). When the two diverge — e.g. a speaker assigned after the uid
migration lands only under ``"c-517"`` — read paths that promote legacy->uid (the
app, and post-MC-469 the exporters) resolve it correctly, but the stale legacy
block lingers on disk and any non-promoting reader sees out-of-date membership.

This script collapses those dual keys permanently: every legacy/bundle key is
merged into its uid (uid value wins) so the file holds a single, canonical key
namespace. It is a thin, reviewable wrapper over the tested, idempotent
``migration.concept_uid_enrichments.migrate_uid_enrichment_keys`` helper, which
writes a timestamped backup before touching the file.

Dry-run is the default. Pass --apply to write. Stop the PARSE server first — the
helper aborts if the file changes underneath it.

    python3 scripts/collapse_legacy_cognate_keys.py --workspace /home/lucas/parse-workspace
    python3 scripts/collapse_legacy_cognate_keys.py --workspace /home/lucas/parse-workspace --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from migration.concept_uid_enrichments import migrate_uid_enrichment_keys  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--workspace",
        required=True,
        type=Path,
        help="PARSE workspace root containing parse-enrichments.json",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the collapsed file (default: dry-run, no changes).",
    )
    args = parser.parse_args(argv)

    report = migrate_uid_enrichment_keys(args.workspace, execute=args.apply)

    migrated = report.get("decision_keys_migrated", [])
    print(json.dumps({
        "workspace": report.get("workspace"),
        "mode": report.get("mode"),
        "uid_keys_total": report.get("uid_keys_total"),
        "legacy_keys_migrated_total": report.get("legacy_keys_migrated_total"),
        "decision_keys_unmappable_left_in_place": report.get("decision_keys_unmappable_left_in_place"),
        "backup_written": report.get("backup_written"),
    }, indent=2, ensure_ascii=False))

    if migrated:
        print("\nLegacy -> uid key remaps ({0}):".format(len(migrated)), file=sys.stderr)
        for entry in migrated[:200]:
            print("  [{block}] {old_key} -> {new_key}".format(**entry), file=sys.stderr)
        if len(migrated) > 200:
            print("  … {0} more".format(len(migrated) - 200), file=sys.stderr)

    if not args.apply and report.get("legacy_keys_migrated_total"):
        print("\nDry-run only. Re-run with --apply to write (a backup is created first).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
