from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from concept_relink import apply_relink_by_gloss, build_relink_by_gloss_plan


_FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


def _seed_concepts(project_root: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with (project_root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in _FIELDNAMES})


def _read_concepts(project_root: pathlib.Path) -> list[dict[str, str]]:
    with (project_root / "concepts.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _seed_overlap(project_root: pathlib.Path, payload: dict) -> None:
    (project_root / "survey-overlap.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_annotation(project_root: pathlib.Path, speaker: str, payload: dict) -> pathlib.Path:
    annotations_dir = project_root / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    path = annotations_dir / f"{speaker}.parse.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_dry_run_groups_by_canonical_gloss_and_prefers_metadata_rich_keep_id(tmp_path: pathlib.Path) -> None:
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "(1.5)- Nose"},
            {"id": "2", "concept_en": "Nose A", "source_item": "34", "source_survey": "JBIL"},
            {"id": "3", "concept_en": "ear (inner)"},
            {"id": "4", "concept_en": "ear"},
            {"id": "5", "concept_en": "eye, face"},
            {"id": "6", "concept_en": "face"},
        ],
    )
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": False,
            "surveys": {},
            "concept_survey_links": {"1": {"KLQ": "1.5"}, "2": {"EXT": "5.1"}},
            "speaker_choices": {},
        },
    )

    plan = build_relink_by_gloss_plan(tmp_path)

    assert plan["ok"] is True
    assert plan["applied"] is False
    assert plan["algorithm"] == "canonical_survey_gloss:v1-strict"
    assert len(plan["groups"]) == 1
    group = plan["groups"][0]
    assert group["canonical_gloss"] == "nose"
    assert group["keep_concept_id"] == "2"
    assert group["merge_concept_ids"] == ["1"]
    assert group["keep_reason"] == "metadata_rich_over_lowest_empty"
    assert group["labels"] == {"1": "(1.5)- Nose", "2": "Nose A"}
    assert group["links_by_survey"] == {"ext": "5.1", "jbil": "34", "klq": "1.5"}
    assert group["source_rows"] == [
        {"concept_id": "1", "concept_en": "(1.5)- Nose", "source_survey": "", "source_item": ""},
        {"concept_id": "2", "concept_en": "Nose A", "source_survey": "JBIL", "source_item": "34"},
    ]
    assert {candidate["reason"] for candidate in plan["fuzzy_candidates"]} == {
        "parenthetical_stripped_match",
        "comma_token_match",
    }


def test_apply_migrates_links_choices_annotations_tags_enrichments_and_is_idempotent(tmp_path: pathlib.Path) -> None:
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "(1.5)- Nose", "source_item": "", "source_survey": "", "custom_order": "10"},
            {"id": "2", "concept_en": "Nose A", "source_item": "34", "source_survey": "JBIL", "custom_order": "20"},
            {"id": "3", "concept_en": "hand", "source_item": "40", "source_survey": "JBIL", "custom_order": "30"},
        ],
    )
    _seed_overlap(
        tmp_path,
        {
            "version": 1,
            "color_coding_enabled": True,
            "surveys": {},
            "concept_survey_links": {"1": {"KLQ": "1.5"}, "2": {"EXT": "5.1"}},
            "speaker_choices": {"Saha01": {"1": "KLQ"}, "Khan01": {"3": "JBIL"}},
        },
    )
    annotation_path = _seed_annotation(
        tmp_path,
        "Saha01",
        {
            "speaker": "Saha01",
            "tiers": {
                "concept": {
                    "name": "concept",
                    "display_order": 1,
                    "intervals": [
                        {"start": 1.0, "end": 1.5, "text": "nose", "concept_id": "1", "manuallyAdjusted": True},
                        {"start": 2.0, "end": 2.5, "text": "hand", "concept_id": "3"},
                    ],
                }
            },
            "confirmed_anchors": {"1": {"start": 1.0, "end": 1.5, "source": "manual"}},
            "concept_tags": {"1": ["core"], "3": ["review"]},
            "ipa_candidates": {"1::ipa::0": [{"raw_ipa": "n"}]},
        },
    )
    (tmp_path / "parse-tags.json").write_text(
        json.dumps([{"id": "tag_core", "label": "core", "color": "#3554B8", "concepts": ["1", "3"], "lexemeTargets": []}]),
        encoding="utf-8",
    )
    (tmp_path / "parse-enrichments.json").write_text(
        json.dumps({"cognate_sets": {"1": {"a": ["Saha01"]}, "3": {"b": ["Khan01"]}}}),
        encoding="utf-8",
    )
    accepted_group = {"keep_concept_id": "2", "merge_concept_ids": ["1"]}

    response = apply_relink_by_gloss(tmp_path, accepted_groups=[accepted_group])

    assert response["ok"] is True
    assert response["applied"] is True
    assert response["fuzzy_candidates"] == []
    assert response["groups"][0]["keep_concept_id"] == "2"
    assert response["annotation_rewrites"] == {"annotations/Saha01.parse.json": 4}
    assert any(path.endswith("/concepts.csv") for path in response["backup_paths"])
    assert any(path.endswith("/survey-overlap.json") for path in response["backup_paths"])
    assert any(path.endswith("/annotations/Saha01.parse.json") for path in response["backup_paths"])
    assert any(path.endswith("/parse-tags.json") for path in response["backup_paths"])
    assert any(path.endswith("/parse-enrichments.json") for path in response["backup_paths"])
    for rel_path in response["backup_paths"]:
        assert (tmp_path / rel_path).exists()

    assert [row["id"] for row in _read_concepts(tmp_path)] == ["2", "3"]
    kept = _read_concepts(tmp_path)[0]
    assert kept["source_item"] == "34"
    assert kept["source_survey"] == "JBIL"
    assert kept["custom_order"] == "20"

    overlap = _read_json(tmp_path / "survey-overlap.json")
    assert overlap["concept_survey_links"] == {"2": {"ext": "5.1", "jbil": "34", "klq": "1.5"}}
    assert overlap["speaker_choices"] == {"Saha01": {"2": "klq"}, "Khan01": {"3": "jbil"}}

    rewritten = _read_json(annotation_path)
    interval = rewritten["tiers"]["concept"]["intervals"][0]
    assert interval["concept_id"] == "2"
    assert interval["start"] == 1.0
    assert interval["end"] == 1.5
    assert interval["manuallyAdjusted"] is True
    assert rewritten["confirmed_anchors"] == {"2": {"start": 1.0, "end": 1.5, "source": "manual"}}
    assert rewritten["concept_tags"] == {"2": ["core"], "3": ["review"]}
    assert rewritten["ipa_candidates"] == {"2::ipa::0": [{"raw_ipa": "n"}]}

    tags = _read_json(tmp_path / "parse-tags.json")
    assert tags[0]["concepts"] == ["2", "3"]
    enrichments = _read_json(tmp_path / "parse-enrichments.json")
    assert enrichments["cognate_sets"] == {"2": {"a": ["Saha01"]}, "3": {"b": ["Khan01"]}}
    assert build_relink_by_gloss_plan(tmp_path)["groups"] == []


def test_apply_rejects_fuzzy_candidate_shape(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "ear (inner)"}, {"id": "2", "concept_en": "ear"}])

    response = apply_relink_by_gloss(
        tmp_path,
        accepted_groups=[{"incoming_label": "ear (inner)", "candidate_label": "ear", "reason": "parenthetical_stripped_match"}],
    )

    assert response == {"error": "fuzzy_candidates_require_manual_relabel"}
