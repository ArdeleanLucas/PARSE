"""Regression tests for concept-id collision migration helper."""
from __future__ import annotations

import csv
import importlib.util
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate_concept_id_collisions.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("migrate_concept_id_collisions", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_concepts_csv(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerows(rows)


def _read_concepts_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_collision_workspace(workspace: pathlib.Path) -> None:
    _write_concepts_csv(
        workspace / "concepts.csv",
        [
            {"id": "237", "concept_en": "twenty one"},
            {"id": "526", "concept_en": "twenty-one"},
            {"id": "51", "concept_en": "hill"},
            {"id": "600", "concept_en": "hill ?"},
        ],
    )
    _write_json(
        workspace / "annotations" / "Saha01.json",
        {
            "tiers": {
                "concept": {
                    "intervals": [
                        {"concept_id": "526", "label": "twenty-one"},
                        {"conceptId": 600, "label": "hill ?"},
                    ],
                },
                "ipa": {"intervals": [{"conceptId": "526", "text": "bist u yek"}]},
            },
        },
    )
    _write_json(
        workspace / "annotations" / "Kalh01.parse.json",
        {
            "tiers": [
                {
                    "name": "ortho",
                    "intervals": [
                        {"concept_id": 526, "text": "twenty-one"},
                        {"conceptId": "51", "text": "already canonical"},
                    ],
                }
            ],
        },
    )


def test_migrate_dry_run_reports_aliases_without_writing(tmp_path: pathlib.Path, capsys) -> None:
    module = _load_script_module()
    _build_collision_workspace(tmp_path)
    before_concepts = (tmp_path / "concepts.csv").read_text(encoding="utf-8")
    before_annotation = (tmp_path / "annotations" / "Saha01.json").read_text(encoding="utf-8")

    summary = module.migrate(tmp_path, apply=False)

    assert summary["alias_map"] == {"526": "237", "600": "51"}
    assert summary["files_modified"] == 0
    assert (tmp_path / "concepts.csv").read_text(encoding="utf-8") == before_concepts
    assert (tmp_path / "annotations" / "Saha01.json").read_text(encoding="utf-8") == before_annotation
    assert not (tmp_path / "concepts.csv.bak").exists()
    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.out
    assert "526 -> 237" in captured.out
    assert "600 -> 51" in captured.out
    assert "0 files modified" in captured.out


def test_migrate_apply_rewrites_annotations_and_is_idempotent(tmp_path: pathlib.Path) -> None:
    module = _load_script_module()
    _build_collision_workspace(tmp_path)

    summary = module.migrate(tmp_path, apply=True)

    assert summary["alias_map"] == {"526": "237", "600": "51"}
    assert summary["files_modified"] == 3
    assert _read_concepts_csv(tmp_path / "concepts.csv") == [
        {"id": "237", "concept_en": "twenty one"},
        {"id": "51", "concept_en": "hill"},
    ]
    saha = _read_json(tmp_path / "annotations" / "Saha01.json")
    assert saha["tiers"]["concept"]["intervals"][0]["concept_id"] == "237"
    assert saha["tiers"]["concept"]["intervals"][1]["conceptId"] == "51"
    assert saha["tiers"]["ipa"]["intervals"][0]["conceptId"] == "237"
    kalh = _read_json(tmp_path / "annotations" / "Kalh01.parse.json")
    assert kalh["tiers"][0]["intervals"][0]["concept_id"] == "237"
    assert kalh["tiers"][0]["intervals"][1]["conceptId"] == "51"
    assert (tmp_path / "concepts.csv.bak").exists()
    assert (tmp_path / "annotations" / "Saha01.json.bak").exists()
    assert (tmp_path / "annotations" / "Kalh01.parse.json.bak").exists()

    second_summary = module.migrate(tmp_path, apply=True)

    assert second_summary["alias_map"] == {}
    assert second_summary["files_modified"] == 0
