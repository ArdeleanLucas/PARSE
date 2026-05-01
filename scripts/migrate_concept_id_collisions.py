#!/usr/bin/env python3
"""Deduplicate PARSE concept ids that differ only by label punctuation.

The script defaults to a dry run. Use ``--apply`` only after stopping any live
PARSE server writing the same workspace.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from concept_registry import concept_label_key  # noqa: E402


def _row_value(row: dict[str, Any], name: str) -> str:
    for key, value in row.items():
        if str(key or "").strip().lower() == name:
            return str(value or "").strip()
    return ""


def _normalize_integer_concept_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("#"):
        text = text[1:].strip()
    if ":" in text:
        text = text.split(":", 1)[0].strip()
    if not text:
        return ""
    try:
        int_id = int(text)
    except (TypeError, ValueError):
        return ""
    return text if str(int_id) == text else ""


def _read_concepts(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or ["id", "concept_en"])
        return fieldnames, [dict(row) for row in reader]


def _write_concepts(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _detect_aliases(rows: list[dict[str, str]]) -> tuple[dict[str, str], list[dict[str, str]]]:
    groups: dict[str, list[tuple[int, str, dict[str, str]]]] = {}
    for row in rows:
        cid = _normalize_integer_concept_id(_row_value(row, "id"))
        label = _row_value(row, "concept_en")
        key = concept_label_key(label)
        if not cid or not label or not key:
            continue
        groups.setdefault(key, []).append((int(cid), cid, row))

    alias_map: dict[str, str] = {}
    orphan_ids: set[str] = set()
    for entries in groups.values():
        distinct_ids = {cid for _int_id, cid, _row in entries}
        if len(distinct_ids) < 2:
            continue
        _canonical_int, canonical_id, _canonical_row = min(entries, key=lambda item: item[0])
        for orphan_int, orphan_id, _row in sorted(entries, key=lambda item: item[0]):
            if orphan_id == canonical_id:
                continue
            alias_map[orphan_id] = canonical_id
            orphan_ids.add(orphan_id)

    filtered_rows = [row for row in rows if _normalize_integer_concept_id(_row_value(row, "id")) not in orphan_ids]
    return dict(sorted(alias_map.items(), key=lambda item: int(item[0]))), filtered_rows


def _iter_annotation_files(workspace: Path) -> list[Path]:
    annotations_dir = workspace / "annotations"
    if not annotations_dir.exists():
        return []
    return sorted(path for path in annotations_dir.glob("*.json") if path.is_file())


def _rewrite_concept_ids(node: Any, alias_map: dict[str, str]) -> int:
    rewrites = 0
    if isinstance(node, dict):
        for field in ("concept_id", "conceptId"):
            current = _normalize_integer_concept_id(node.get(field))
            if current in alias_map:
                node[field] = alias_map[current]
                rewrites += 1
        for value in node.values():
            rewrites += _rewrite_concept_ids(value, alias_map)
    elif isinstance(node, list):
        for value in node:
            rewrites += _rewrite_concept_ids(value, alias_map)
    return rewrites


def _write_backup_once(path: Path) -> None:
    backup_path = path.with_name(f"{path.name}.bak")
    if not backup_path.exists():
        backup_path.write_bytes(path.read_bytes())


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _print_summary(summary: dict[str, Any], apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[concept-id-collision-migration] {mode}")
    alias_map: dict[str, str] = summary["alias_map"]
    if alias_map:
        print("Alias mappings (orphan -> canonical):")
        for orphan_id, canonical_id in alias_map.items():
            print(f"  {orphan_id} -> {canonical_id}")
    else:
        print("No concept-id collisions found.")
    print(f"concepts.csv rows: {summary['concepts_before']} -> {summary['concepts_after']}")
    annotation_rewrites: dict[str, int] = summary["annotation_rewrites"]
    if annotation_rewrites:
        print("Annotation rewrites:")
        for relative_path, count in annotation_rewrites.items():
            print(f"  {relative_path}: {count}")
    if apply:
        print(f"{summary['files_modified']} files modified")
    else:
        print(f"0 files modified (dry-run); {summary['files_would_modify']} files would be modified")


def migrate(workspace: str | Path, apply: bool = False) -> dict[str, Any]:
    workspace_path = Path(workspace)
    concepts_path = workspace_path / "concepts.csv"
    fieldnames, rows = _read_concepts(concepts_path)
    alias_map, filtered_rows = _detect_aliases(rows)

    annotation_rewrites: dict[str, int] = {}
    rewritten_payloads: dict[Path, Any] = {}
    for annotation_path in _iter_annotation_files(workspace_path):
        try:
            payload = json.loads(annotation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARNING: skipping {annotation_path}: {exc}", file=sys.stderr)
            continue
        rewrite_count = _rewrite_concept_ids(payload, alias_map)
        if rewrite_count:
            annotation_rewrites[str(annotation_path.relative_to(workspace_path))] = rewrite_count
            rewritten_payloads[annotation_path] = payload

    concepts_changed = filtered_rows != rows
    files_would_modify = (1 if concepts_changed else 0) + len(rewritten_payloads)
    files_modified = 0
    if apply:
        if concepts_changed:
            _write_backup_once(concepts_path)
            _write_concepts(concepts_path, fieldnames, filtered_rows)
            files_modified += 1
        for annotation_path, payload in rewritten_payloads.items():
            _write_backup_once(annotation_path)
            _write_json(annotation_path, payload)
            files_modified += 1

    summary = {
        "alias_map": alias_map,
        "annotation_rewrites": annotation_rewrites,
        "concepts_before": len(rows),
        "concepts_after": len(filtered_rows),
        "files_would_modify": files_would_modify,
        "files_modified": files_modified,
    }
    _print_summary(summary, apply=apply)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path, help="PARSE workspace root containing concepts.csv")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="apply", action="store_false", help="Report changes without writing files")
    mode.add_argument("--apply", dest="apply", action="store_true", help="Write backups and apply the migration")
    parser.set_defaults(apply=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    migrate(args.workspace, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
