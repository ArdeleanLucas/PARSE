#!/usr/bin/env python3
"""Backfill concepts.csv source_item values from Audition cue CSVs.

Dry-run is the default.  Pass --apply to write concepts.csv.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
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


_PAREN_LETTER_SUFFIX = re.compile(r"^(.+?)\s*\(([A-Za-z]+)\)\s*$")
_LEADING_NUM = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")
_MALFORMED_KLQ = re.compile(r"^\s*\(\s*(\d+(?:\.\d+)*)\s*[-\u2013\u2014]")


def default_workspace_path() -> Path:
    return PYTHON_DIR / "test_fixtures" / "source_item_backfill_workspace"


def format_summary(summary: BackfillSummary) -> str:
    return "matched={0} added={1} skipped={2}".format(summary.matched, summary.added, summary.skipped)


def _iter_candidate_csvs(workspace: Path, source_roots: Sequence[Path] = ()) -> list[Path]:
    candidates: list[Path] = []
    for subdirectory in ("imports/staging", "imports/legacy"):
        directory = workspace / subdirectory
        if directory.exists():
            candidates.extend(path for path in directory.rglob("*.csv") if path.is_file())
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
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, str]], dict[str, tuple[str, str]]]:
    by_label: dict[str, str] = {}
    by_label_survey: dict[str, str] = {}
    by_label_by_survey: dict[str, dict[str, str]] = {}
    by_prefix: dict[str, tuple[str, str]] = {}
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
            if not source_item:
                continue
            survey = source_survey or ""
            by_prefix.setdefault(source_item, (source_item, survey))
            if not label:
                continue
            label_key = concept_label_key(label)
            by_label.setdefault(label_key, source_item)
            by_label_survey.setdefault(label_key, survey)
            by_label_by_survey.setdefault(label_key, {}).setdefault(survey, source_item)
    return by_label, by_label_survey, by_label_by_survey, by_prefix


def _audition_prefix_index(
    workspace: Path,
    by_prefix: dict[str, tuple[str, str]],
    summary: BackfillSummary,
) -> dict[str, tuple[str, str]]:
    """Return concept_id -> (source_item, survey) by joining annotation traces to the global prefix index."""
    out: dict[str, tuple[str, str]] = {}
    annotations = workspace / "annotations"
    if not annotations.exists():
        return out
    for path in sorted(annotations.glob("*.json")):
        if path.name.endswith(".parse.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            summary.decisions.append("skip {0}: annotation read failed {1}".format(path, exc))
            continue
        if not isinstance(data, dict):
            continue
        intervals = data.get("tiers", {}).get("concept", {}).get("intervals", [])
        if not isinstance(intervals, list):
            continue
        for interval in intervals:
            if not isinstance(interval, dict):
                continue
            cid = str(interval.get("concept_id") or "").strip()
            audition_prefix = str(interval.get("audition_prefix") or "").strip()
            if not cid or not audition_prefix or audition_prefix.startswith("row_"):
                continue
            hit = by_prefix.get(audition_prefix)
            if hit:
                out.setdefault(cid, hit)
    return out


def _bare_label_concepts(rows: Sequence[dict[str, str]]) -> set[str]:
    bare: set[str] = set()
    for row in rows:
        label = str(row.get("concept_en") or "").strip()
        if label and not _PAREN_LETTER_SUFFIX.match(label):
            bare.add(concept_label_key(label))
    return bare


def _jbil_lookup(by_label_by_survey: dict[str, dict[str, str]], label_key: str) -> str | None:
    return by_label_by_survey.get(label_key, {}).get("JBIL")


def _resolve_concept(
    cid: str,
    label: str,
    by_label: dict[str, str],
    by_label_survey: dict[str, str],
    by_label_by_survey: dict[str, dict[str, str]],
    audition_index: dict[str, tuple[str, str]],
    bare_label_concepts: set[str],
) -> tuple[str, str] | None:
    """Resolve source_item/source_survey using the fixed smart-match priority order.

    Priority: audition-prefix trace, exact label, paren-to-space normalization,
    JBIL alternate, leading-number JBIL, malformed-KLQ rescue.
    """
    if cid in audition_index:
        return audition_index[cid]

    label_key = concept_label_key(label)
    if label_key in by_label:
        return by_label[label_key], by_label_survey.get(label_key, "")

    suffix_match = _PAREN_LETTER_SUFFIX.match(label)
    if suffix_match:
        base = suffix_match.group(1).strip()
        normalized_key = concept_label_key("{0} {1}".format(base, suffix_match.group(2).strip()))
        if normalized_key in by_label:
            return by_label[normalized_key], by_label_survey.get(normalized_key, "")

        base_key = concept_label_key(base)
        if base_key in bare_label_concepts:
            jbil_source_item = _jbil_lookup(by_label_by_survey, base_key)
            if jbil_source_item:
                return jbil_source_item, "JBIL"

    leading_match = _LEADING_NUM.match(label)
    if leading_match:
        return leading_match.group(1), "JBIL"

    malformed_match = _MALFORMED_KLQ.match(label)
    if malformed_match:
        return malformed_match.group(1), "KLQ"

    return None


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
    by_label, by_label_survey, by_label_by_survey, by_prefix = _source_maps_from_csvs(csv_paths, summary)
    audition_index = _audition_prefix_index(workspace, by_prefix, summary)
    bare_label_concepts = _bare_label_concepts(rows)

    for row in rows:
        cid = str(row.get("id") or "").strip()
        label = str(row.get("concept_en") or "").strip()
        resolved = _resolve_concept(
            cid,
            label,
            by_label,
            by_label_survey,
            by_label_by_survey,
            audition_index,
            bare_label_concepts,
        )
        if not resolved:
            continue
        target, target_survey = resolved
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
