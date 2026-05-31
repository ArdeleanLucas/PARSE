"""Audit duplicate concepts that inflate NEXUS/BEAST2 character counts.

This module is intentionally analysis-only. It mirrors the current NEXUS export's
character counting semantics but does not change export or cognate computation.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

from concept_linking import build_canonical_gloss_index


@dataclass(frozen=True)
class ConceptCharacterMember:
    concept_id: str
    label: str
    source_survey: str
    source_item: str
    current_character_count: int
    columns: dict[str, list[str]]


@dataclass(frozen=True)
class CanonicalCharacterGroup:
    canonical_key: str
    members: list[ConceptCharacterMember]
    current_character_count: int
    projected_character_count: int
    class_label: str
    collapse_action: str
    byte_identical_pairs: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class AuditTotals:
    current_nchar: int
    projected_nchar_after_canonical_collapse: int
    nchar_inflation: int
    affected_canonical_concepts: int
    class_counts: dict[str, int]
    safe_union_groups: int
    needs_recluster_groups: int


@dataclass(frozen=True)
class AuditReport:
    groups: list[CanonicalCharacterGroup]
    totals: AuditTotals
    byte_identical_column_pairs: list[tuple[str, str]]
    workspace: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ColumnMap = dict[str, list[str]]


def _clean_members(raw_members: Any) -> list[str]:
    if not isinstance(raw_members, list):
        return []
    return [str(member) for member in raw_members if str(member).strip()]


def _export_style_cognate_columns(enrichments: Mapping[str, Any]) -> dict[str, ColumnMap]:
    """Return concept -> cognate columns using current NEXUS export precedence.

    Mirrors ``build_nexus_text`` in ``python/ai/tools/export_tools.py``: union the
    manual-override keys followed by auto keys, use a manual block when present,
    ignore non-dict concept blocks and non-list/empty groups, and count one
    character per retained ``(concept_id, group)`` pair.
    """

    overrides = enrichments.get("manual_overrides") if isinstance(enrichments, Mapping) else None
    override_sets = overrides.get("cognate_sets") if isinstance(overrides, Mapping) else None
    auto_sets = enrichments.get("cognate_sets") if isinstance(enrichments, Mapping) else None
    override_sets = override_sets if isinstance(override_sets, Mapping) else {}
    auto_sets = auto_sets if isinstance(auto_sets, Mapping) else {}

    union_keys: list[str] = []
    seen_keys: set[str] = set()
    for key in list(override_sets.keys()) + list(auto_sets.keys()):
        key_str = str(key)
        if key_str not in seen_keys:
            seen_keys.add(key_str)
            union_keys.append(key_str)

    columns_by_concept: dict[str, ColumnMap] = {}
    for key in union_keys:
        override_block = override_sets.get(key)
        auto_block = auto_sets.get(key)
        block = override_block if isinstance(override_block, Mapping) else auto_block
        if not isinstance(block, Mapping):
            continue
        groups: ColumnMap = {}
        for group, members in block.items():
            cleaned = _clean_members(members)
            if cleaned:
                groups[str(group)] = cleaned
        if groups:
            columns_by_concept[key] = groups
    return columns_by_concept


def export_style_current_nchar(enrichments: Mapping[str, Any]) -> int:
    """Count current NEXUS characters using the existing export semantics."""

    return sum(len(groups) for groups in _export_style_cognate_columns(enrichments).values())


def _column_signature(columns: Mapping[str, Sequence[str]]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (str(group), tuple(sorted(str(member) for member in members if str(member).strip())))
        for group, members in sorted(columns.items(), key=lambda item: str(item[0]))
    )


def _row_value(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    return str(value if value is not None else "").strip()


def _classify_group(members: Sequence[ConceptCharacterMember]) -> str:
    if len(members) < 2:
        return "Singleton"

    source_pairs = {(member.source_survey, member.source_item) for member in members}
    if len(source_pairs) > 1:
        return "Class 3"

    signatures = {_column_signature(member.columns) for member in members}
    if len(signatures) == 1:
        return "Class 1"
    return "Class 2"


def _byte_identical_pairs(members: Sequence[ConceptCharacterMember]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for left, right in combinations(members, 2):
        if _column_signature(left.columns) == _column_signature(right.columns):
            pairs.append((left.concept_id, right.concept_id))
    return pairs


def audit_canonical_characters(
    concepts_rows: Sequence[Mapping[str, Any]], enrichments: Mapping[str, Any]
) -> AuditReport:
    """Quantify current vs canonical-collapse character counts.

    Canonical identity is delegated to ``build_canonical_gloss_index`` so this
    report uses the same cross-survey gloss normalization as the rest of PARSE.
    """

    rows_by_id = {_row_value(row, "id"): row for row in concepts_rows if _row_value(row, "id")}
    canonical_index = build_canonical_gloss_index(concepts_rows)
    columns_by_concept = _export_style_cognate_columns(enrichments)

    groups: list[CanonicalCharacterGroup] = []
    all_identical_pairs: list[tuple[str, str]] = []
    for canonical_key in sorted(canonical_index):
        concept_ids = [concept_id for concept_id in canonical_index[canonical_key] if concept_id in rows_by_id]
        if not concept_ids:
            continue
        members: list[ConceptCharacterMember] = []
        for concept_id in concept_ids:
            row = rows_by_id[concept_id]
            columns = columns_by_concept.get(concept_id, {})
            members.append(
                ConceptCharacterMember(
                    concept_id=concept_id,
                    label=_row_value(row, "concept_en"),
                    source_survey=_row_value(row, "source_survey"),
                    source_item=_row_value(row, "source_item"),
                    current_character_count=len(columns),
                    columns={group: list(values) for group, values in columns.items()},
                )
            )

        current_count = sum(member.current_character_count for member in members)
        projected_count = 1 if current_count else 0
        identical_pairs = _byte_identical_pairs(members)
        all_identical_pairs.extend(identical_pairs)
        signatures = {_column_signature(member.columns) for member in members}
        collapse_action = "safe_union" if len(signatures) == 1 else "needs_recluster"
        groups.append(
            CanonicalCharacterGroup(
                canonical_key=canonical_key,
                members=members,
                current_character_count=current_count,
                projected_character_count=projected_count,
                class_label=_classify_group(members),
                collapse_action=collapse_action,
                byte_identical_pairs=identical_pairs,
            )
        )

    current_nchar = export_style_current_nchar(enrichments)
    projected_nchar = sum(group.projected_character_count for group in groups)
    affected_groups = [
        group
        for group in groups
        if len(group.members) > 1 and group.current_character_count > group.projected_character_count
    ]
    class_counts = {"Class 1": 0, "Class 2": 0, "Class 3": 0}
    for group in affected_groups:
        if group.class_label in class_counts:
            class_counts[group.class_label] += 1

    totals = AuditTotals(
        current_nchar=current_nchar,
        projected_nchar_after_canonical_collapse=projected_nchar,
        nchar_inflation=current_nchar - projected_nchar,
        affected_canonical_concepts=len(affected_groups),
        class_counts=class_counts,
        safe_union_groups=sum(1 for group in affected_groups if group.collapse_action == "safe_union"),
        needs_recluster_groups=sum(1 for group in affected_groups if group.collapse_action == "needs_recluster"),
    )
    return AuditReport(groups=groups, totals=totals, byte_identical_column_pairs=all_identical_pairs)


def _read_concepts_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def audit_workspace(workspace_dir: str | Path) -> AuditReport:
    workspace = Path(workspace_dir).expanduser().resolve()
    concepts_path = workspace / "concepts.csv"
    enrichments_path = workspace / "parse-enrichments.json"
    if not concepts_path.exists():
        raise FileNotFoundError(f"concepts.csv not found in workspace: {workspace}")
    report = audit_canonical_characters(_read_concepts_csv(concepts_path), _read_json(enrichments_path, {}))
    return AuditReport(
        groups=report.groups,
        totals=report.totals,
        byte_identical_column_pairs=report.byte_identical_column_pairs,
        workspace=str(workspace),
    )


def _format_summary(report: AuditReport) -> str:
    totals = report.totals
    lines = [
        "Canonical character audit",
        f"Workspace: {report.workspace or '(in-memory)'}",
        f"Current NCHAR: {totals.current_nchar}",
        f"Projected NCHAR after canonical collapse: {totals.projected_nchar_after_canonical_collapse}",
        f"NCHAR inflation: {totals.nchar_inflation}",
        f"Affected canonical concepts: {totals.affected_canonical_concepts}",
        "Classes: "
        + ", ".join(f"{label}={count}" for label, count in sorted(totals.class_counts.items())),
        f"safe_union groups: {totals.safe_union_groups}",
        f"needs_recluster groups: {totals.needs_recluster_groups}",
    ]
    for group in report.groups:
        if len(group.members) <= 1:
            continue
        ids = ", ".join(member.concept_id for member in group.members)
        lines.append(
            f"- {group.canonical_key}: ids [{ids}], current={group.current_character_count}, "
            f"projected={group.projected_character_count}, {group.class_label}, {group.collapse_action}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit canonical concept character inflation.")
    parser.add_argument("workspace_dir", help="Workspace containing concepts.csv and parse-enrichments.json")
    parser.add_argument("--json-only", action="store_true", help="Print only the machine-readable JSON report")
    args = parser.parse_args(argv)

    report = audit_workspace(args.workspace_dir)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    if args.json_only:
        print(payload)
    else:
        print(_format_summary(report))
        print("JSON_REPORT:")
        print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CLI test
    raise SystemExit(main())
