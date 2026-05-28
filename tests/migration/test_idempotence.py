from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from python.migration.concept_suffix_pollution import is_already_canonical, run_migration


def _write_canonical_workspace(workspace: Path) -> None:
    (workspace / "annotations").mkdir(parents=True)
    (workspace / "concepts.csv").write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "53,big,F01,Fail01,1\n"
        "54,white,F02,Fail01,2\n",
        encoding="utf-8",
    )
    (workspace / "annotations" / "Fail01.parse.json").write_text(
        json.dumps({
            "tiers": {"concept": {"intervals": [
                {"start": 0, "end": 1, "text": "big", "concept_id": "53"},
                {"start": 1, "end": 2, "text": "white", "concept_id": "54"},
            ]}},
            "concept_tags": {"53": ["custom-sk-concept-list"]},
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (workspace / "parse-tags.json").write_text(
        json.dumps([{"id": "custom-sk-concept-list", "concepts": ["53", "54"]}], indent=2) + "\n",
        encoding="utf-8",
    )


def test_already_canonical_workspace_is_no_op_without_backups_or_writes(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_canonical_workspace(workspace)
    before = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}

    assert is_already_canonical(workspace) is True
    result = run_migration(workspace)

    after = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert result.success
    assert result.already_canonical is True
    assert result.merge_map == {}
    assert result.backups_created == []
    assert before == after
    assert not list(workspace.rglob("*.bak-*"))


def test_second_migration_run_on_fail01_fixture_is_already_canonical(tmp_path: Path) -> None:
    source = Path(__file__).parent / "fixtures" / "issue_529_full"
    workspace = tmp_path / "ws"
    shutil.copytree(source, workspace)

    first = run_migration(workspace)
    second = run_migration(workspace)

    assert first.success
    assert first.already_canonical is False
    assert second.success
    assert second.already_canonical is True
    assert second.merge_map == {}
    assert second.backups_created == []
