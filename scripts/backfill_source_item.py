#!/usr/bin/env python3
"""Backfill concepts.csv source_item values from Audition cue CSVs.

Dry-run is the default.  Pass --apply to write concepts.csv.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from concept_registry import concept_label_key  # noqa: E402
from concept_source_item import (  # noqa: E402
    parse_cue_name,
    read_concepts_csv_rows,
    row_value,
    write_concepts_csv_rows,
)


@dataclass
class BackfillSummary:
    matched: int = 0
    added: int = 0
    skipped: int = 0
    decisions: list[str] = field(default_factory=list)


def default_workspace_path() -> Path:
    return PYTHON_DIR / "test_fixtures" / "source_item_backfill_workspace"


def format_summary(summary: BackfillSummary) -> str:
    return "matched={0} added={1} skipped={2}".format(summary.matched, summary.added, summary.skipped)


def _iter_candidate_csvs(workspace: Path, source_roots: Sequence[Path] = ()) -> list[Path]:
    candidates: list[Path] = []
    staging = workspace / "imports" / "staging"
    if staging.exists():
        candidates.extend(path for path in staging.rglob("*.csv") if path.is_file())
    for root in source_roots:
        if root.exists():
            candidates.extend(path for path in root.rglob("*.csv") if path.is_file())
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in sorted(candidates):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _dict_reader_for_text(text: str) -> csv.DictReader:
    dialect = None
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters="\t,;")
    except csv.Error:
        pass
    if dialect is not None:
        return csv.DictReader(io.StringIO(text), dialect=dialect)
    return csv.DictReader(io.StringIO(text), delimiter="\t")


def _source_maps_from_csvs(
    paths: Iterable[Path],
    summary: BackfillSummary,
) -> tuple[dict[str, str], dict[str, str]]:
    by_label: dict[str, str] = {}
    by_label_survey: dict[str, str] = {}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            summary.decisions.append("skip {0}: read failed {1}".format(path, exc))
            continue
        reader = _dict_reader_for_text(text)
        fieldnames = {str(name or "").strip().lower() for name in reader.fieldnames or []}
        if "name" not in fieldnames:
            summary.decisions.append("skip {0}: no Name column".format(path))
            continue
        for record in reader:
            cue_name = row_value(record, "Name")
            source_item, source_survey, label = parse_cue_name(cue_name)
            if not source_item or not label:
                continue
            label_key = concept_label_key(label)
            by_label.setdefault(label_key, source_item)
            survey = source_survey or ""
            by_label_survey.setdefault(label_key, survey)
    return by_label, by_label_survey


def backfill_source_items(
    workspace_path: Path | str | None = None,
    *,
    source_roots: Sequence[Path | str] = (),
    dry_run: bool = True,
    verbose: bool = False,
) -> BackfillSummary:
    workspace = Path(workspace_path).expanduser().resolve() if workspace_path else default_workspace_path().resolve()
    source_root_paths = [Path(root).expanduser().resolve() for root in source_roots]
    summary = BackfillSummary()
    concepts_path = workspace / "concepts.csv"
    rows = read_concepts_csv_rows(concepts_path)
    if not rows:
        summary.decisions.append("skip {0}: no readable concepts.csv rows".format(concepts_path))
        return summary

    csv_paths = _iter_candidate_csvs(workspace, source_root_paths)
    by_label, by_label_survey = _source_maps_from_csvs(csv_paths, summary)
    if not by_label:
        return summary

    for row in rows:
        cid = str(row.get("id") or "").strip()
        label = str(row.get("concept_en") or "").strip()
        label_key = concept_label_key(label)
        target = by_label.get(label_key)
        if not target:
            continue
        target_survey = by_label_survey.get(label_key) or ""
        summary.matched += 1
        current = str(row.get("source_item") or "").strip()
        current_survey = str(row.get("source_survey") or "").strip()
        if current and current != target:
            summary.skipped += 1
            summary.decisions.append("skip {0} {1}: existing {2} != {3}".format(cid, label, current, target))
            continue
        if current_survey and current_survey != target_survey:
            summary.skipped += 1
            summary.decisions.append(
                "skip {0} {1}: existing source_survey {2} != {3}".format(cid, label, current_survey, target_survey)
            )
            continue
        if current == target and current_survey == target_survey:
            summary.skipped += 1
            summary.decisions.append("skip {0} {1}: already {2}".format(cid, label, target))
            continue
        summary.added += 1
        summary.decisions.append("add {0} {1}: {2} {3}".format(cid, label, target, target_survey).rstrip())
        if not dry_run:
            row["source_item"] = target
            row["source_survey"] = target_survey

    if not dry_run and summary.added:
        write_concepts_csv_rows(concepts_path, rows, atomic=True)
    elif verbose and not dry_run:
        summary.decisions.append("no write: no additions")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "workspace",
        nargs="?",
        default=str(default_workspace_path()),
        help="Workspace root containing concepts.csv; defaults to a safe test fixture workspace.",
    )
    parser.add_argument(
        "--source-root",
        action="append",
        default=[],
        help="Optional external root containing original Audition CSVs. May be provided multiple times.",
    )
    parser.add_argument("--apply", action="store_true", help="Write concepts.csv. Without this flag, dry-run only.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode (default).")
    parser.add_argument("--verbose", action="store_true", help="Print per-row decisions before the summary.")
    args = parser.parse_args(argv)

    summary = backfill_source_items(
        args.workspace,
        source_roots=args.source_root,
        dry_run=not args.apply,
        verbose=args.verbose,
    )
    if args.verbose:
        for decision in summary.decisions:
            print(decision)
    print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
