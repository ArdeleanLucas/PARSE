from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from compare_bundles import build_compare_bundles, build_canonical_lexemes_report_tsv

FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


def _seed_concepts(root: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with (root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})


def _seed_annotation(root: pathlib.Path, speaker: str, intervals: list[dict], *, source_audio: str | None = None) -> None:
    annotations = root / "annotations"
    annotations.mkdir(exist_ok=True)
    payload = {
        "speaker": speaker,
        "audio": {"source_wav": f"{speaker}.wav"},
        "tiers": {
            "concept": {"intervals": intervals},
            "ipa": {"intervals": []},
            "ortho": {"intervals": []},
            "ortho_words": {"intervals": []},
        },
    }
    if source_audio is not None:
        payload["source_audio"] = source_audio
    (annotations / f"{speaker}.parse.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _big_rows() -> list[dict[str, str]]:
    return [
        {"id": "53", "concept_en": "big (A)", "source_item": "4.1", "source_survey": "KLQ", "custom_order": "53"},
        {"id": "619", "concept_en": "big (B)", "source_item": "4.1", "source_survey": "KLQ", "custom_order": "619"},
        {"id": "150", "concept_en": "big (A)", "source_item": "169", "source_survey": "JBIL", "custom_order": "150"},
    ]


def test_build_compare_bundles_groups_big_rows_into_bundle_buckets_and_variants(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, _big_rows())
    _seed_annotation(
        tmp_path,
        "Saha01",
        [
            {"text": "big", "concept_id": "53", "start": 4013.131, "end": 4013.999, "ipa": "ɣɛɫ", "ortho": "gel"},
            {"text": "big", "concept_id": "150", "start": 12.0, "end": 13.0, "ipa": "gawr", "ortho": "gawr"},
        ],
    )

    payload = build_compare_bundles(tmp_path, speakers=["Saha01"])

    assert [bundle["bundle_id"] for bundle in payload["bundles"]] == ["bundle:big"]
    bundle = payload["bundles"][0]
    assert bundle["label"] == "big"
    assert bundle["row_ids"] == ["53", "619", "150"]
    assert [(bucket["survey_id"], bucket["source_item"], [variant["csv_row_id"] for variant in bucket["variants"]]) for bucket in bundle["buckets"]] == [
        ("klq", "4.1", ["53", "619"]),
        ("jbil", "169", ["150"]),
    ]
    assert bundle["candidates"]["Saha01"]["53"] == {
        "ipa": "ɣɛɫ",
        "ortho": "gel",
        "start_sec": 4013.131,
        "end_sec": 4013.999,
        "source_wav": "audio/working/Saha01/Saha01.wav",
    }
    assert bundle["candidates"]["Saha01"]["619"] is None
    assert "Saha01" not in bundle["canonical"]
    assert any("2 candidates" in warning for warning in bundle["warnings"])


def test_candidate_ipa_is_none_when_concept_annotation_has_no_real_ipa(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, [{"id": "77", "concept_en": "hair (A)", "source_item": "2.2", "source_survey": "KLQ"}])
    _seed_annotation(
        tmp_path,
        "Saha01",
        [{"text": "hair (A)", "concept_id": "77", "start": 3.0, "end": 4.0, "ortho": "muser"}],
    )

    candidate = build_compare_bundles(tmp_path, speakers=["Saha01"])["bundles"][0]["candidates"]["Saha01"]["77"]

    assert candidate["ipa"] is None
    assert candidate["ortho"] == "muser"


def test_candidate_source_wav_uses_project_relative_source_audio(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "big", "source_item": "4.1", "source_survey": "KLQ"}])
    _seed_annotation(
        tmp_path,
        "Saha01",
        [{"text": "big", "concept_id": "53", "start": 1.0, "end": 2.0, "ipa": "ɣɛɫ", "ortho": "gel"}],
        source_audio="audio/working/Saha01/Saha01.wav",
    )

    candidate = build_compare_bundles(tmp_path, speakers=["Saha01"])["bundles"][0]["candidates"]["Saha01"]["53"]

    assert candidate["source_wav"] == "audio/working/Saha01/Saha01.wav"
    assert "/" in candidate["source_wav"]


def test_singleton_bundle_auto_picks_single_candidate_without_persisting(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, [{"id": "10", "concept_en": "nose", "source_item": "1.5", "source_survey": "KLQ"}])
    _seed_annotation(tmp_path, "Saha01", [{"text": "not nose", "concept_id": "10", "start": 1, "end": 2, "ipa": "lut", "ortho": "lut"}])

    bundle = build_compare_bundles(tmp_path, speakers=["Saha01"])["bundles"][0]

    assert bundle["bundle_id"] == "bundle:nose"
    assert bundle["canonical"]["Saha01"] == {
        "csv_row_id": "10",
        "survey_id": "klq",
        "source_item": "1.5",
        "bucket_key": "klq\u00001.5",
        "variant_label": "",
        "realization_index": 0,
        "source": "default:single-candidate",
    }
    assert not (tmp_path / "parse-enrichments.json").exists()


def test_bundle_id_collision_suffix_is_deterministic(tmp_path: pathlib.Path) -> None:
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "a/b", "source_item": "1", "source_survey": "KLQ"},
            {"id": "2", "concept_en": "a b", "source_item": "2", "source_survey": "KLQ"},
        ],
    )

    payload = build_compare_bundles(tmp_path, speakers=[])

    assert [bundle["bundle_id"] for bundle in payload["bundles"]] == ["bundle:a-b", "bundle:a-b-2"]


def test_no_concept_id_legacy_interval_falls_back_to_text_with_warning(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, [{"id": "7", "concept_en": "water", "source_item": "3", "source_survey": "KLQ"}])
    _seed_annotation(tmp_path, "Saha01", [{"text": "water", "start": 4, "end": 5, "ipa": "aw", "ortho": "aw"}])

    bundle = build_compare_bundles(tmp_path, speakers=["Saha01"])["bundles"][0]

    assert bundle["candidates"]["Saha01"]["7"] == {
        "ipa": None,
        "ortho": "",
        "start_sec": 4.0,
        "end_sec": 5.0,
        "source_wav": "audio/working/Saha01/Saha01.wav",
    }
    assert any("legacy text fallback" in warning for warning in bundle["warnings"])


def test_speaker_concept_survey_links_take_precedence_over_legacy_bucket(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, _big_rows())
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps({"speaker_choices": {"Saha01": {"53": "klq"}}, "concept_survey_links": {"53": {"klq": "4.1"}}, "speaker_concept_survey_links": {"Saha01": {"53": {"jbil": "169"}}}}),
        encoding="utf-8",
    )

    bundle = build_compare_bundles(tmp_path, speakers=["Saha01"])["bundles"][0]

    bucket_by_key = {bucket["bucket_key"]: bucket for bucket in bundle["buckets"]}
    assert "jbil\u0000169" in bucket_by_key
    assert any(variant["csv_row_id"] == "53" for variant in bucket_by_key["jbil\u0000169"]["variants"])


def test_bundle_emits_scoped_survey_overlap_snapshot(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, _big_rows())
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps(
            {
                "concept_survey_links": {"53": {"KLQ": "4.1"}, "999": {"KLQ": "9.9"}},
                "speaker_choices": {"Saha01": {"53": "KLQ", "999": "KLQ"}, "Khan02": {"150": "JBIL"}},
                "speaker_concept_survey_links": {
                    "Saha01": {"53": {"JBIL": "169"}, "999": {"KLQ": "9.9"}},
                    "Khan02": {"150": {"JBIL": "169"}},
                },
            }
        ),
        encoding="utf-8",
    )

    bundle = build_compare_bundles(tmp_path, speakers=["Saha01", "Khan02"])["bundles"][0]

    assert bundle["concept_survey_links"] == {"53": {"klq": "4.1"}}
    assert bundle["speaker_choices"] == {"Saha01": {"53": "klq"}, "Khan02": {"150": "jbil"}}
    assert bundle["speaker_concept_survey_links"] == {
        "Saha01": {"53": {"jbil": "169"}},
        "Khan02": {"150": {"jbil": "169"}},
    }


def test_bundle_emits_empty_survey_overlap_snapshot_when_unset(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, [{"id": "10", "concept_en": "nose", "source_item": "1.5", "source_survey": "KLQ"}])

    bundle = build_compare_bundles(tmp_path, speakers=[])["bundles"][0]

    assert bundle["concept_survey_links"] == {}
    assert bundle["speaker_choices"] == {}
    assert bundle["speaker_concept_survey_links"] == {}


def test_migration_from_canonical_realizations_maps_unambiguous_order_and_skips_ambiguous(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, _big_rows() + [{"id": "9", "concept_en": "hand", "source_item": "2", "source_survey": "KLQ"}])
    (tmp_path / "parse-enrichments.json").write_text(
        json.dumps({"manual_overrides": {"canonical_realizations": {"big": {"Saha01": 1}, "missing": {"Saha01": 0}}}}),
        encoding="utf-8",
    )

    bundles = build_compare_bundles(tmp_path, speakers=["Saha01"])["bundles"]
    big = next(bundle for bundle in bundles if bundle["bundle_id"] == "bundle:big")
    hand = next(bundle for bundle in bundles if bundle["bundle_id"] == "bundle:hand")

    assert big["canonical"]["Saha01"]["csv_row_id"] == "619"
    assert big["canonical"]["Saha01"]["source"] == "migration:canonical_realizations"
    assert "Saha01" not in hand["canonical"]


def test_canonical_report_uses_same_effective_rows_and_escapes_tsv_fields(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, [{"id": "10", "concept_en": "no\tse\nlabel", "source_item": "1.5", "source_survey": "KLQ"}])
    _seed_annotation(tmp_path, "Saha01", [{"text": "nose", "concept_id": "10", "start": 1, "end": 2, "ipa": "lu\tt", "ortho": "lu\nt"}])

    payload = build_compare_bundles(tmp_path, speakers=["Saha01"])
    report = build_canonical_lexemes_report_tsv(payload)

    assert report.splitlines()[0] == "speaker\tbundle_id\tbundle_label\tcsv_row_id\tsurvey_id\tsource_item\tvariant_label\tipa\tortho\tsource"
    assert "no se label" in report
    assert "lu t" in report
    assert "lu t" in report
    assert "default:single-candidate" in report
