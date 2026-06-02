from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import compare_bundles
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


def test_each_realization_keeps_its_own_sibling_transcription(tmp_path: pathlib.Path) -> None:
    # A speaker who records two realizations (A/B) of one concept must get each
    # realization's OWN IPA/ortho from the sibling tiers — not realization A's
    # transcription copied onto B. Regression: the sibling selector pinned every
    # realization to the first same-conceptId interval, so B duplicated A and the
    # distinct second variant never surfaced in Compare. The IPA/ortho siblings
    # are intentionally keyed by time overlap, so the file order below (B before
    # A) must not change which transcription each realization receives.
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "hair", "source_item": "1.1", "source_survey": "KLQ"}])
    annotations = tmp_path / "annotations"
    annotations.mkdir(exist_ok=True)
    payload = {
        "speaker": "Saha01",
        "audio": {"source_wav": "Saha01.wav"},
        "tiers": {
            "concept": {
                "intervals": [
                    {"text": "hair", "concept_id": "1", "start": 20.0, "end": 21.0},
                    {"text": "hair", "concept_id": "1", "start": 10.0, "end": 11.0},
                ]
            },
            "ipa": {
                "intervals": [
                    {"text": "ipa-late", "concept_id": "1", "start": 20.0, "end": 21.0},
                    {"text": "ipa-early", "concept_id": "1", "start": 10.0, "end": 11.0},
                ]
            },
            "ortho": {
                "intervals": [
                    {"text": "ortho-late", "concept_id": "1", "start": 20.0, "end": 21.0},
                    {"text": "ortho-early", "concept_id": "1", "start": 10.0, "end": 11.0},
                ]
            },
            "ortho_words": {"intervals": []},
        },
    }
    (annotations / "Saha01.parse.json").write_text(json.dumps(payload), encoding="utf-8")

    candidate = build_compare_bundles(tmp_path, speakers=["Saha01"])["bundles"][0]["candidates"]["Saha01"]["1"]
    realizations = candidate["realizations"]

    # Realizations are start-sorted (A = earliest), each carrying its own time-
    # aligned transcription rather than realization A's repeated twice.
    assert [r["realization_index"] for r in realizations] == [0, 1]
    assert [r["ipa"] for r in realizations] == ["ipa-early", "ipa-late"]
    assert [r["ortho"] for r in realizations] == ["ortho-early", "ortho-late"]
    # The primary candidate still mirrors realization A.
    assert candidate["ipa"] == "ipa-early"
    assert candidate["realization_index"] == 0


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


def test_cross_gloss_link_warns_but_still_merges(tmp_path: pathlib.Path) -> None:
    # A bad cross-survey link joins two genuinely different concepts (a "fog" row
    # and a "rain" row that share a survey item only because the link is wrong).
    # Grouping is unchanged — the rows still merge into one bundle — but the
    # bundle must surface a gloss-mismatch warning so the bad link is visible
    # instead of silently fabricating a phantom A/B variant.
    _seed_concepts(
        tmp_path,
        [
            {"id": "142", "concept_en": "rain", "source_item": "125", "source_survey": "JBIL"},
            {"id": "537", "concept_en": "fog", "source_item": "3.9", "source_survey": "KLQ"},
        ],
    )
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps({"concept_survey_links": {"537": {"jbil": "125"}}}),
        encoding="utf-8",
    )

    bundles = build_compare_bundles(tmp_path, speakers=[])["bundles"]
    merged = [bundle for bundle in bundles if set(bundle["row_ids"]) == {"142", "537"}]
    assert len(merged) == 1, "behavior preserved: the rows still merge into one bundle"
    warnings = merged[0]["warnings"]
    assert any("glosses differ" in w and "fog" in w and "rain" in w for w in warnings), warnings


def test_cross_gloss_link_warns_once_for_bidirectional_link(tmp_path: pathlib.Path) -> None:
    # Two mismatched-gloss rows that link to EACH OTHER's survey items share two
    # (survey, item) pairs, so the mismatch is encountered twice. It must warn
    # exactly once per row pair — not duplicate the message.
    _seed_concepts(
        tmp_path,
        [
            {"id": "142", "concept_en": "rain", "source_item": "125", "source_survey": "JBIL"},
            {"id": "537", "concept_en": "fog", "source_item": "3.9", "source_survey": "KLQ"},
        ],
    )
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps({"concept_survey_links": {"142": {"klq": "3.9"}, "537": {"jbil": "125"}}}),
        encoding="utf-8",
    )

    bundles = build_compare_bundles(tmp_path, speakers=[])["bundles"]
    merged = [bundle for bundle in bundles if set(bundle["row_ids"]) == {"142", "537"}]
    assert len(merged) == 1
    gloss_warnings = [w for w in merged[0]["warnings"] if "glosses differ" in w]
    assert len(gloss_warnings) == 1, gloss_warnings


def test_clarifier_variant_link_does_not_warn(tmp_path: pathlib.Path) -> None:
    # "salt" and "salt (eating)" are the same concept across two surveys — a
    # clarifier difference, not a different concept. They must merge WITHOUT a
    # gloss-mismatch warning (the heuristic ignores substring/clarifier glosses).
    _seed_concepts(
        tmp_path,
        [
            {"id": "52", "concept_en": "salt", "source_item": "3.14", "source_survey": "KLQ"},
            {"id": "352", "concept_en": "salt (eating)", "source_item": "139", "source_survey": "JBIL"},
        ],
    )
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps({"concept_survey_links": {"52": {"jbil": "139"}, "352": {"klq": "3.14"}}}),
        encoding="utf-8",
    )

    bundles = build_compare_bundles(tmp_path, speakers=[])["bundles"]
    merged = [bundle for bundle in bundles if set(bundle["row_ids"]) == {"52", "352"}]
    assert len(merged) == 1
    assert merged[0]["warnings"] == [], merged[0]["warnings"]


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


def test_multiple_realizations_are_all_emitted_start_sorted(tmp_path: pathlib.Path) -> None:
    """A speaker with 2+ intervals on one concept_id exposes every realization
    (A/B) under candidate["realizations"], start-sorted, not just the first."""
    _seed_concepts(
        tmp_path,
        [{"id": "122", "concept_en": "to fly", "source_item": "7.12", "source_survey": "KLQ", "custom_order": "122"}],
    )
    # B is authored first but starts LATER, so start-sorting must put A (earlier) at index 0.
    _seed_annotation(
        tmp_path,
        "Fail01",
        [
            {"text": "to fly", "concept_id": "122", "start": 8381.30, "end": 8382.10, "ipa": "balB", "ortho": "orthoB"},
            {"text": "to fly", "concept_id": "122", "start": 8381.25, "end": 8382.19, "ipa": "balA", "ortho": "orthoA"},
        ],
    )

    payload = build_compare_bundles(tmp_path, speakers=["Fail01"])
    candidate = payload["bundles"][0]["candidates"]["Fail01"]["122"]

    realizations = candidate["realizations"]
    assert len(realizations) == 2
    # Start-sorted: A (earlier start) is index 0, B is index 1.
    assert [r["ipa"] for r in realizations] == ["balA", "balB"]
    assert [r["realization_index"] for r in realizations] == [0, 1]
    # Primary top-level mirrors realization 0 (back-compat).
    assert candidate["ipa"] == "balA"
    assert candidate["start_sec"] == 8381.25


def test_single_realization_candidate_has_no_realizations_key(tmp_path: pathlib.Path) -> None:
    """Single-realization rows stay byte-identical: no realizations key added."""
    _seed_concepts(
        tmp_path,
        [{"id": "122", "concept_en": "to fly", "source_item": "7.12", "source_survey": "KLQ", "custom_order": "122"}],
    )
    _seed_annotation(
        tmp_path,
        "Fail01",
        [{"text": "to fly", "concept_id": "122", "start": 1.0, "end": 2.0, "ipa": "bal", "ortho": "o"}],
    )

    payload = build_compare_bundles(tmp_path, speakers=["Fail01"])
    candidate = payload["bundles"][0]["candidates"]["Fail01"]["122"]

    assert "realizations" not in candidate
    assert "realization_index" not in candidate


def _salt_rows() -> list[dict[str, str]]:
    # Two concept rows that the overlap sidecar declares the same concept, but
    # whose English stems differ ("salt" vs "salt (eating)").
    return [
        {"id": "52", "concept_en": "salt", "source_item": "3.14", "source_survey": "KLQ", "custom_order": "52"},
        {"id": "352", "concept_en": "salt (eating)", "source_item": "139", "source_survey": "JBIL", "custom_order": "352"},
    ]


def test_cross_survey_linked_rows_merge_into_one_bundle(tmp_path: pathlib.Path) -> None:
    # 52 (KLQ 3.14) <-> 352 (JBIL 139) cross-reference each other in the sidecar.
    _seed_concepts(tmp_path, _salt_rows())
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps({"concept_survey_links": {"52": {"jbil": "139"}, "352": {"klq": "3.14"}}}),
        encoding="utf-8",
    )
    # Saha01 recorded salt under the JBIL row (352); Badr01 under the KLQ row (52).
    _seed_annotation(tmp_path, "Saha01", [{"text": "salt", "concept_id": "352", "start": 1.0, "end": 2.0, "ipa": "xwa", "ortho": "خوە"}])
    _seed_annotation(tmp_path, "Badr01", [{"text": "salt", "concept_id": "52", "start": 1.0, "end": 2.0, "ipa": "xwā", "ortho": "xwā"}])

    payload = build_compare_bundles(tmp_path, speakers=["Saha01", "Badr01"])

    # One merged bundle (not two), labelled with the clean gloss.
    assert len(payload["bundles"]) == 1
    bundle = payload["bundles"][0]
    assert bundle["bundle_id"] == "bundle:salt"
    assert bundle["label"] == "salt"
    assert set(bundle["row_ids"]) == {"52", "352"}
    # Both speakers' candidates live in the SAME bundle, each under the concept id
    # they actually recorded — the speaker who used row 52 is no longer dropped.
    assert bundle["candidates"]["Badr01"]["52"]["ipa"] == "xwā"
    assert bundle["candidates"]["Badr01"].get("352") is None
    assert bundle["candidates"]["Saha01"]["352"]["ipa"] == "xwa"
    assert bundle["candidates"]["Saha01"].get("52") is None


def test_unlinked_distinct_stems_stay_separate_bundles(tmp_path: pathlib.Path) -> None:
    # Without a cross-survey link, distinct stems must NOT merge (no false union).
    _seed_concepts(tmp_path, _salt_rows())  # no survey-overlap.json
    _seed_annotation(tmp_path, "Saha01", [{"text": "salt", "concept_id": "352", "start": 1.0, "end": 2.0, "ipa": "xwa", "ortho": "خوە"}])

    payload = build_compare_bundles(tmp_path, speakers=["Saha01"])

    assert sorted(b["bundle_id"] for b in payload["bundles"]) == ["bundle:salt", "bundle:salt-eating"]


def test_annotation_is_read_once_per_speaker_not_once_per_bundle(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    # Perf regression guard: each speaker's annotation must be loaded exactly
    # once for the whole build, regardless of how many bundles exist. The old
    # code loaded it inside the per-bundle loop -> O(bundles x speakers) reparses
    # of the same file, which made Compare slow to load. Seed many distinct
    # concepts (=> many bundles) and assert the read count equals the speaker
    # count, not bundle_count x speaker_count.
    rows = [
        {"id": str(i), "concept_en": word, "source_item": str(i), "source_survey": "KLQ"}
        for i, word in enumerate(
            ["big", "small", "hair", "salt", "water", "fire", "tree", "stone"], start=1
        )
    ]
    _seed_concepts(tmp_path, rows)
    for speaker in ("Saha01", "Badr01"):
        _seed_annotation(
            tmp_path,
            speaker,
            [{"text": "big", "concept_id": "1", "start": 1.0, "end": 2.0, "ipa": "x", "ortho": "x"}],
        )

    calls: list[str] = []
    real = compare_bundles._intervals_for_speaker

    def _counting(project_root, speaker):
        calls.append(speaker)
        return real(project_root, speaker)

    monkeypatch.setattr(compare_bundles, "_intervals_for_speaker", _counting)

    payload = build_compare_bundles(tmp_path, speakers=["Saha01", "Badr01"])

    # 8 distinct concepts -> 8 bundles. The old loop would have read each of the
    # 2 speakers' files 8 times (16 reads); hoisted, it is exactly 2.
    assert len(payload["bundles"]) == 8
    assert len(calls) == 2
    assert sorted(calls) == ["Badr01", "Saha01"]
