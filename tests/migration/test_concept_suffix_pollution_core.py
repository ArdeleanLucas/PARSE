from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_ROOT = _REPO_ROOT / "python"
for _path in (str(_REPO_ROOT), str(_PYTHON_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from python.migration.concept_suffix_pollution import build_merge_map, run_migration, rewrite_annotation_file

FIXTURE = Path(__file__).parent / "fixtures" / "fail01_pattern"


def _copy_fixture(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE, workspace)
    return workspace


def _read_concepts(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_build_merge_map_fail01_pattern() -> None:
    rows = [
        {"id": "53", "concept_en": "big (A)", "source_survey": "KLQ", "source_item": "4.1"},
        {"id": "619", "concept_en": "big (B)", "source_survey": "KLQ", "source_item": "4.1"},
        {"id": "620", "concept_en": "big (C)", "source_survey": "KLQ", "source_item": "4.1"},
        {"id": "621", "concept_en": "big (D)", "source_survey": "KLQ", "source_item": "4.1"},
        {"id": "631", "concept_en": "big (E)", "source_survey": "KLQ", "source_item": "4.1"},
        {"id": "634", "concept_en": "big", "source_survey": "KLQ", "source_item": "4.1"},
        {"id": "10", "concept_en": "hair (women)", "source_survey": "JBIL", "source_item": "32"},
        {"id": "11", "concept_en": "hair (men)", "source_survey": "JBIL", "source_item": "32"},
    ]

    merge_map = build_merge_map(rows)

    assert merge_map == {"619": "53", "620": "53", "621": "53", "631": "53", "634": "53"}


def test_build_merge_map_strips_leaked_audition_cue_prefixes() -> None:
    rows = [
        {"id": "48", "concept_en": "stomach (organ)", "source_survey": "KLQ", "source_item": "48"},
        {"id": "610", "concept_en": "48 stomach (organ)", "source_survey": "KLQ", "source_item": "48"},
        {"id": "56", "concept_en": "skin", "source_survey": "KLQ", "source_item": "56"},
        {"id": "611", "concept_en": "56 skin", "source_survey": "KLQ", "source_item": "56"},
    ]

    merge_map = build_merge_map(rows)

    assert merge_map == {"610": "48", "611": "56"}


def test_run_migration_dry_run_does_not_write(tmp_path: Path) -> None:
    workspace = _copy_fixture(tmp_path)
    before = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}

    result = run_migration(workspace, dry_run=True)
    after = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}

    assert result.success
    assert result.dry_run is True
    assert result.merge_map == {"619": "53", "620": "53", "621": "53", "631": "53", "634": "53"}
    assert before == after
    assert result.backups_created == []


def test_run_migration_canonical_concept_en_and_clarifier_preservation(tmp_path: Path) -> None:
    workspace = _copy_fixture(tmp_path)

    result = run_migration(workspace)

    assert result.success
    rows = _read_concepts(workspace / "concepts.csv")
    by_id = {row["id"]: row for row in rows}
    assert list(by_id) == ["53", "10", "11"]
    assert by_id["53"]["concept_en"] == "big"
    assert by_id["53"]["source_survey"] == "KLQ"
    assert by_id["53"]["source_item"] == "4.1"
    assert by_id["53"]["custom_order"] == "53"
    assert by_id["10"]["concept_en"] == "hair (women)"
    assert by_id["11"]["concept_en"] == "hair (men)"


def test_rewrite_annotation_file_rekeys_strips_exact_variant_text_and_merges_concept_tags(tmp_path: Path) -> None:
    workspace = _copy_fixture(tmp_path)
    annotation_path = workspace / "annotations" / "Fail01.parse.json"
    merge_map = {"619": "53", "620": "53", "621": "53", "631": "53", "634": "53"}
    concept_canonical_by_id = {"53": "big", "10": "hair (women)", "11": "hair (men)"}

    stats = rewrite_annotation_file(annotation_path, merge_map, concept_canonical_by_id, dry_run=False)

    assert stats["rekeyed"] == 2
    assert stats["stripped"] == 1
    assert stats["tags_rekeyed"] == 1
    record = json.loads(annotation_path.read_text(encoding="utf-8"))
    intervals = record["tiers"]["concept"]["intervals"]
    assert [interval["concept_id"] for interval in intervals] == ["53", "53", "53", "10"]
    assert intervals[0]["text"] == "big"
    assert intervals[1]["text"] == "big"
    assert intervals[2]["text"] == "big (something else)"
    assert record["concept_tags"] == {"53": ["custom-sk", "confirmed"], "10": ["clarifier"]}
    assert list(workspace.glob("annotations/Fail01.parse.json.bak-*-pre-suffix-canonicalization"))


def test_run_migration_rekeys_parse_tags_and_creates_timestamped_backups(tmp_path: Path) -> None:
    workspace = _copy_fixture(tmp_path)

    result = run_migration(workspace)

    assert result.success
    tags = json.loads((workspace / "parse-tags.json").read_text(encoding="utf-8"))
    assert tags[0]["concepts"] == ["53"]
    assert [str(concept_id) for concept_id in tags[1]["concepts"]] == ["10", "11"]
    assert result.parse_tags_rekeyed == 1
    backup_names = sorted(Path(path).name for path in result.backups_created)
    assert len(backup_names) == 3
    assert any(name.startswith("concepts.csv.bak-") and name.endswith("-pre-suffix-canonicalization") for name in backup_names)
    assert any(name.startswith("Fail01.parse.json.bak-") and name.endswith("-pre-suffix-canonicalization") for name in backup_names)
    assert any(name.startswith("parse-tags.json.bak-") and name.endswith("-pre-suffix-canonicalization") for name in backup_names)
    assert list(workspace.glob("concepts.csv.bak-*-pre-suffix-canonicalization"))
    assert list(workspace.glob("parse-tags.json.bak-*-pre-suffix-canonicalization"))


def _write_minimal_annotation(workspace: Path, intervals: list[dict[str, object]] | None = None) -> None:
    annotations = workspace / "annotations"
    annotations.mkdir()
    (annotations / "Synthetic.parse.json").write_text(
        json.dumps(
            {
                "tiers": {"concept": {"intervals": intervals or []}},
                "concept_tags": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_migration_canonicalizes_standalone_variant_suffix_rows(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "concepts.csv").write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "100,solo (A),99,JBIL,100\n"
        "200,paired (A),50,KLQ,200\n"
        "201,paired (B),50,KLQ,201\n"
        "300,clean,77,JBIL,300\n",
        encoding="utf-8",
    )
    _write_minimal_annotation(
        workspace,
        [
            {"start": 0, "end": 1, "text": "solo (A)", "concept_id": "100"},
            {"start": 1, "end": 2, "text": "paired (A)", "concept_id": "200"},
            {"start": 2, "end": 3, "text": "paired (B)", "concept_id": "201"},
            {"start": 3, "end": 4, "text": "clean", "concept_id": "300"},
        ],
    )

    result = run_migration(workspace)

    assert result.success
    rows = _read_concepts(workspace / "concepts.csv")
    by_id = {row["id"]: row for row in rows}
    assert by_id["100"]["concept_en"] == "solo"
    assert "201" not in by_id
    assert by_id["200"]["concept_en"] == "paired"
    assert by_id["300"]["concept_en"] == "clean"
    assert result.post_migration_violations == []


def test_run_migration_rekeys_survey_overlap_links_and_dedupes_collisions(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "concepts.csv").write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "53,big (A),4.1,KLQ,53\n"
        "619,big (B),4.1,KLQ,619\n"
        "620,big (C),4.1,KLQ,620\n"
        "900,small,5.1,JBIL,900\n"
        "901,big,4.1,jbil,901\n"
        "902,big,x.y,klq2,902\n"
        "903,small,5.1,klq,903\n",
        encoding="utf-8",
    )
    (workspace / "survey-overlap.json").write_text(
        json.dumps(
            {
                "concept_survey_links": {
                    "53": {"jbil": "4.1"},
                    "619": {"jbil": "4.1"},
                    "620": {"klq2": "x.y"},
                    "900": {"klq": "5.1"},
                },
                "speaker_concept_survey_links": {
                    "Fail01": {
                        "53": {"jbil": "4.1"},
                        "619": {"jbil": "4.1"},
                    },
                    "Saha01": {
                        "620": {"klq2": "x.y"},
                        "900": {"klq": "5.1"},
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_minimal_annotation(workspace)

    result = run_migration(workspace)

    assert result.success
    assert result.survey_overlap_rekeyed == 4
    payload = json.loads((workspace / "survey-overlap.json").read_text(encoding="utf-8"))
    assert payload["concept_survey_links"] == {
        "53": {"jbil": "4.1", "klq2": "x.y"},
        "900": {"klq": "5.1"},
    }
    assert payload["speaker_concept_survey_links"] == {
        "Fail01": {"53": {"jbil": "4.1"}},
        "Saha01": {"53": {"klq2": "x.y"}, "900": {"klq": "5.1"}},
    }
    backup_names = [path.name for path in workspace.glob("survey-overlap.json.bak-*-pre-suffix-canonicalization")]
    assert backup_names
    assert any(Path(path).name in backup_names for path in result.backups_created)
    assert "survey-overlap.json entries re-keyed: 4" in result.summary()


def test_run_migration_missing_survey_overlap_file_is_not_an_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "concepts.csv").write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "53,big (A),4.1,KLQ,53\n"
        "619,big (B),4.1,KLQ,619\n",
        encoding="utf-8",
    )
    _write_minimal_annotation(workspace)

    result = run_migration(workspace)

    assert result.success
    assert result.survey_overlap_rekeyed == 0
    assert not (workspace / "survey-overlap.json").exists()
