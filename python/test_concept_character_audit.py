from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import ai.chat_tools  # noqa: F401  # import first: export_tools <-> chat_tools have a load-order cycle
from ai.tools.export_tools import build_nexus_text
from concept_character_audit import (
    audit_canonical_characters,
    audit_workspace,
    export_style_current_nchar,
)

FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "canonical_character_audit"


def _concept_rows() -> list[dict[str, str]]:
    with (FIXTURE / "concepts.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _enrichments() -> dict:
    return json.loads((FIXTURE / "parse-enrichments.json").read_text(encoding="utf-8"))


def _group_by_key(report):
    return {group.canonical_key: group for group in report.groups}


class _NexusTools:
    project_root = FIXTURE
    project_json_path = FIXTURE / "project.json"
    enrichments_path = FIXTURE / "parse-enrichments.json"


def test_audit_classifies_canonical_groups_and_collapse_actions() -> None:
    report = audit_canonical_characters(_concept_rows(), _enrichments())
    groups = _group_by_key(report)

    assert set(groups) == {"hair", "leaf", "stone"}

    hair = groups["hair"]
    assert hair.class_label == "Class 1"
    assert hair.collapse_action == "safe_union"
    assert [member.concept_id for member in hair.members] == ["1", "2"]
    assert [member.current_character_count for member in hair.members] == [2, 2]

    leaf = groups["leaf"]
    assert leaf.class_label == "Class 2"
    assert leaf.collapse_action == "needs_recluster"
    assert [member.concept_id for member in leaf.members] == ["3", "4"]
    assert [member.current_character_count for member in leaf.members] == [2, 1]

    stone = groups["stone"]
    assert stone.class_label == "Class 3"
    assert stone.collapse_action == "needs_recluster"
    assert [member.concept_id for member in stone.members] == ["5", "6"]


def test_audit_quantifies_current_and_projected_nchar_inflation() -> None:
    report = audit_canonical_characters(_concept_rows(), _enrichments())

    assert report.totals.current_nchar == 9
    assert report.totals.projected_nchar_after_canonical_collapse == 3
    assert report.totals.nchar_inflation == 6
    assert report.totals.affected_canonical_concepts == 3
    assert report.totals.class_counts == {"Class 1": 1, "Class 2": 1, "Class 3": 1}
    assert report.totals.safe_union_groups == 1
    assert report.totals.needs_recluster_groups == 2
    assert report.byte_identical_column_pairs == [("1", "2")]


def test_current_nchar_matches_existing_nexus_character_counting() -> None:
    enrichments = _enrichments()
    report = audit_canonical_characters(_concept_rows(), enrichments)
    nexus_text = build_nexus_text(_NexusTools())
    match = re.search(r"DIMENSIONS NCHAR=(\d+);", nexus_text)

    assert match is not None
    assert export_style_current_nchar(enrichments) == int(match.group(1))
    assert report.totals.current_nchar == int(match.group(1))


def test_audit_workspace_loads_fixture_without_live_workspace() -> None:
    report = audit_workspace(FIXTURE)

    assert report.workspace == str(FIXTURE)
    assert report.totals.current_nchar == 9
    assert report.totals.projected_nchar_after_canonical_collapse == 3


def test_cli_prints_summary_and_machine_readable_json() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "concept_character_audit", str(FIXTURE)],
        check=True,
        cwd=Path(__file__).parents[1],
        env={"PYTHONPATH": str(Path(__file__).parents[1] / "python")},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "Canonical character audit" in completed.stdout
    assert "Current NCHAR: 9" in completed.stdout
    marker = "JSON_REPORT:\n"
    assert marker in completed.stdout
    payload = json.loads(completed.stdout.split(marker, 1)[1])
    assert payload["totals"]["nchar_inflation"] == 6
    assert payload["totals"]["needs_recluster_groups"] == 2
