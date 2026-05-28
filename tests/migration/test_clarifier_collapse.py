from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_ROOT = _REPO_ROOT / "python"
for _path in (str(_REPO_ROOT), str(_PYTHON_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from python.migration.concept_suffix_pollution import collapse_clarifier_rows, run_migration

_COMPARE_NOTES_FILE = "parseui-compare-notes-v1.json"


def _write_concepts(workspace: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["id", "concept_en", "source_item", "source_survey", "custom_order"]
    with (workspace / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _read_concepts(workspace: Path) -> list[dict[str, str]]:
    with (workspace / "concepts.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_annotation(workspace: Path) -> None:
    annotations = workspace / "annotations"
    annotations.mkdir()
    (annotations / "Fail01.parse.json").write_text(
        json.dumps(
            {
                "tiers": {
                    "concept": {
                        "intervals": [
                            {"start": 1.0, "end": 2.0, "text": "hair (men)", "concept_id": "249"},
                            {"start": 3.0, "end": 4.0, "text": "hair (women)", "concept_id": "250"},
                            {"start": 5.0, "end": 6.0, "text": "hair (collective)", "conceptId": "599"},
                        ]
                    }
                },
                "concept_tags": {"250": ["gendered"], "599": ["collective"]},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_hair_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_concepts(
        workspace,
        [
            {"id": "249", "concept_en": "hair (men)", "source_survey": "JBIL", "source_item": "32", "custom_order": "249"},
            {"id": "250", "concept_en": "hair (women)", "source_survey": "JBIL", "source_item": "32", "custom_order": "250"},
            {"id": "599", "concept_en": "hair (collective)", "source_survey": "JBIL", "source_item": "32", "custom_order": "599"},
            {"id": "601", "concept_en": "hair (women)", "source_survey": "KLQ", "source_item": "1.1", "custom_order": "601"},
        ],
    )
    _write_annotation(workspace)
    (workspace / "parse-tags.json").write_text(
        json.dumps(
            [
                {"id": "tag-hair", "concepts": ["249", "250", "599"]},
                {"id": "tag-klq", "concepts": ["601"]},
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (workspace / _COMPARE_NOTES_FILE).write_text(json.dumps({"249": "existing note"}) + "\n", encoding="utf-8")
    return workspace


def test_collapse_clarifier_rows_collapses_hair_triple_and_prepends_delta_notes(tmp_path: Path) -> None:
    workspace = _write_hair_workspace(tmp_path)

    result = collapse_clarifier_rows(workspace, dry_run=False)

    assert result.merge_map == {"250": "249", "599": "249"}
    assert result.groups_collapsed == 1
    assert result.notes_updated == 1
    rows = _read_concepts(workspace)
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {"249", "601"}
    assert by_id["249"]["concept_en"] == "hair"
    assert by_id["601"]["concept_en"] == "hair (women)"

    annotation = json.loads((workspace / "annotations" / "Fail01.parse.json").read_text(encoding="utf-8"))
    intervals = annotation["tiers"]["concept"]["intervals"]
    assert [interval.get("concept_id") or interval.get("conceptId") for interval in intervals] == ["249", "249", "249"]
    assert annotation["concept_tags"] == {"249": ["gendered", "collective"]}

    tags = json.loads((workspace / "parse-tags.json").read_text(encoding="utf-8"))
    assert tags[0]["concepts"] == ["249"]
    assert tags[1]["concepts"] == ["601"]

    notes = json.loads((workspace / _COMPARE_NOTES_FILE).read_text(encoding="utf-8"))["249"]
    assert notes.startswith("Merged from clarifier rows on ")
    assert "- hair (men) — was concept_id 249" in notes
    assert "- hair (women) — was concept_id 250" in notes
    assert "- hair (collective) — was concept_id 599" in notes
    assert notes.endswith("existing note")
    assert list(workspace.glob("concepts.csv.bak-*-pre-clarifier-collapse"))
    assert list(workspace.glob("parse-tags.json.bak-*-pre-clarifier-collapse"))
    assert list(workspace.glob(f"{_COMPARE_NOTES_FILE}.bak-*-pre-clarifier-collapse"))


def test_clarifier_collapse_dry_run_writes_nothing(tmp_path: Path) -> None:
    workspace = _write_hair_workspace(tmp_path)
    before = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}

    result = collapse_clarifier_rows(workspace, dry_run=True)

    after = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert result.merge_map == {"250": "249", "599": "249"}
    assert before == after
    assert result.backups_created == []


def test_run_migration_clarifier_pass_is_idempotent(tmp_path: Path) -> None:
    workspace = _write_hair_workspace(tmp_path)

    first = run_migration(workspace)
    notes_after_first = (workspace / _COMPARE_NOTES_FILE).read_text(encoding="utf-8")
    second = run_migration(workspace)
    notes_after_second = (workspace / _COMPARE_NOTES_FILE).read_text(encoding="utf-8")

    assert first.success
    assert first.clarifier_merge_map == {"250": "249", "599": "249"}
    assert second.success
    assert second.clarifier_merge_map == {}
    assert notes_after_second == notes_after_first
    assert notes_after_second.count("Merged from clarifier rows on") == 1


def test_singleton_clarifier_row_is_not_collapsed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_concepts(
        workspace,
        [
            {"id": "250", "concept_en": "hair (women)", "source_survey": "JBIL", "source_item": "32", "custom_order": "250"},
        ],
    )

    result = run_migration(workspace)

    assert result.success
    assert result.clarifier_merge_map == {}
    assert _read_concepts(workspace)[0]["concept_en"] == "hair (women)"
    assert not (workspace / _COMPARE_NOTES_FILE).exists()
