"""Tests for ``python/export_review_data.py``.

The exporter is the reverse of ``python/import_review_data.py``: a workspace
plus a tag id should yield a ``review_data.json`` whose schema matches the one
the archived review_tool HTML consumes. Tests stub the workspace shape rather
than depending on a live one.
"""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from export_review_data import (
    DEFAULT_TAG_ID,
    LEGACY_SCHEMA_VERSION,
    _crosstier_text,
    _stem_label,
    _variant_letter,
    build_review_data,
    build_review_data_anchored,
    write_outputs,
)


def _write_contact_config(tmp_path: Path, payload: dict[str, dict[str, object]]) -> Path:
    """Write a tmp ``sil_contact_languages.json`` and return its path."""
    path = tmp_path / "sil_contact_languages.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _make_workspace(
    tmp_path: Path,
    *,
    concepts: list[dict[str, str]],
    speakers: dict[str, dict[str, object]],
    enrichments: dict[str, object] | None = None,
) -> Path:
    """Materialise a minimal PARSE workspace under ``tmp_path``.

    ``speakers`` maps a speaker name to a dict carrying ``concept_intervals``
    (list of dicts with at minimum ``concept_id``, ``start``, ``end``, ``ipa``,
    ``ortho``) and ``tagged_ids`` (concept ids to mark as thesis-tagged).
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "project.json").write_text(
        json.dumps(
            {
                "project_id": "test-export",
                "speakers": {name: {} for name in speakers},
                "concepts": {
                    "source": "concepts.csv",
                    "id_column": "id",
                    "label_column": "concept_en",
                    "total": len(concepts),
                },
            }
        ),
        encoding="utf-8",
    )

    with (workspace / "concepts.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["id", "concept_en", "source_item", "source_survey", "custom_order"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in concepts:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    annotations = workspace / "annotations"
    annotations.mkdir()
    for speaker, payload in speakers.items():
        intervals = payload.get("concept_intervals") or []
        tagged = payload.get("tagged_ids") or []
        ipa_intervals = payload.get("ipa_intervals") or []
        ortho_intervals = payload.get("ortho_intervals") or []
        tiers: dict[str, object] = {
            "concept": {
                "display_order": 3,
                "type": "interval",
                "intervals": list(intervals),
            }
        }
        if ipa_intervals:
            tiers["ipa"] = {"display_order": 1, "type": "interval", "intervals": list(ipa_intervals)}
        if ortho_intervals:
            tiers["ortho"] = {"display_order": 2, "type": "interval", "intervals": list(ortho_intervals)}
        annotation = {
            "version": 1,
            "speaker": speaker,
            "source_audio": f"audio/working/{speaker}/{speaker}.wav",
            "tiers": tiers,
            "concept_tags": {cid: [DEFAULT_TAG_ID] for cid in tagged},
        }
        (annotations / f"{speaker}.parse.json").write_text(
            json.dumps(annotation), encoding="utf-8"
        )

    if enrichments is not None:
        (workspace / "parse-enrichments.json").write_text(
            json.dumps(enrichments, ensure_ascii=False), encoding="utf-8"
        )

    return workspace


class BuildReviewDataTests(unittest.TestCase):
    def test_only_tagged_concepts_emitted_in_concepts_csv_order(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "1", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
                    {"id": "2", "concept_en": "bark", "source_item": "1.2", "source_survey": "KLQ"},
                    {"id": "3", "concept_en": "dog (A)", "source_item": "79", "source_survey": "JBIL"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "1", "start": 0.0, "end": 0.5, "ipa": "aʂ", "ortho": "aş"},
                            {"concept_id": "3", "start": 1.0, "end": 1.4, "ipa": "səg", "ortho": "seg"},
                        ],
                        "tagged_ids": ["1", "3"],
                    },
                    "Kalh01": {
                        "concept_intervals": [
                            {"concept_id": "3", "start": 2.0, "end": 2.6, "ipa": "kuʧik", "ortho": "kuçik"},
                        ],
                        "tagged_ids": ["3"],
                    },
                },
            )
            review_data, clip_plan = build_review_data(workspace=workspace)

        concept_ids_emitted = [c["concept_id"] for c in review_data["concepts"]]
        # source_item is used as concept_id in the legacy payload; 1.1 for ash, 79 for dog.
        self.assertEqual(concept_ids_emitted, ["1.1", "79"])
        gloss_emitted = [c["concept_en"] for c in review_data["concepts"]]
        self.assertEqual(gloss_emitted, ["ash", "dog"])
        # Three clip specs: Fail01 ash, Fail01 dog, Kalh01 dog.
        self.assertEqual(len(clip_plan), 3)

    def test_form_fields_match_legacy_schema(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "1", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "1", "start": 0.5, "end": 1.25, "ipa": "aʂ", "ortho": "aş"}
                        ],
                        "tagged_ids": ["1"],
                    },
                    "Khan01": {
                        # Untagged speaker — should still appear as an empty form, not omitted.
                        "concept_intervals": [],
                        "tagged_ids": [],
                    },
                },
            )
            review_data, _clip_plan = build_review_data(workspace=workspace)

        forms = review_data["concepts"][0]["forms"]
        speakers = {f["speaker"]: f for f in forms}
        self.assertEqual(sorted(speakers), ["Fail01", "Khan01"])

        produced = speakers["Fail01"]
        self.assertEqual(produced["ipa"], "aʂ")
        self.assertEqual(produced["ortho"], "aş")
        self.assertAlmostEqual(produced["start_sec"], 0.5)
        self.assertAlmostEqual(produced["duration_sec"], 0.75)
        self.assertEqual(produced["source"], "KLQ")
        self.assertEqual(produced["audio_path"], "audio/Fail01/KLQ_1.1_A_ash_Fail01.wav")
        # Analytical fields unscored in PARSE today — match legacy null shape.
        self.assertEqual(produced["cognate_class"], "?")
        self.assertEqual(produced["arabic_similarity"], 0.0)
        self.assertEqual(produced["persian_similarity"], 0.0)
        self.assertIsNone(produced["borrowing_flag"])
        self.assertIsNone(produced["spectrogram_path"])

        empty = speakers["Khan01"]
        self.assertEqual(empty["ipa"], "?")
        self.assertEqual(empty["ortho"], "")
        self.assertIsNone(empty["audio_path"])

    def test_variant_letter_extracted_from_concept_label(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "1", "concept_en": "dog (A)", "source_item": "79", "source_survey": "JBIL"},
                    {"id": "2", "concept_en": "dog (B)", "source_item": "79", "source_survey": "JBIL"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "1", "start": 0.0, "end": 0.3, "ipa": "səg", "ortho": "seg"},
                            {"concept_id": "2", "start": 0.5, "end": 0.8, "ipa": "kʷəɾ", "ortho": "kur"},
                        ],
                        "tagged_ids": ["1", "2"],
                    },
                },
            )
            review_data, _ = build_review_data(workspace=workspace)

        paths = [c["forms"][0]["audio_path"] for c in review_data["concepts"]]
        self.assertEqual(
            paths,
            [
                "audio/Fail01/JBIL_79_A_dog_Fail01.wav",
                "audio/Fail01/JBIL_79_B_dog_Fail01.wav",
            ],
        )

    def test_metadata_block_matches_legacy_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "1", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "1", "start": 0.0, "end": 0.2, "ipa": "aʂ", "ortho": "aş"}
                        ],
                        "tagged_ids": ["1"],
                    },
                },
            )
            review_data, _ = build_review_data(workspace=workspace)

        meta = review_data["metadata"]
        for key in (
            "generated",
            "speakers",
            "total_concepts",
            "method",
            "audio_linked",
            "spectrograms",
            "version",
            "phonetic_flags",
        ):
            self.assertIn(key, meta)
        self.assertEqual(meta["version"], LEGACY_SCHEMA_VERSION)
        self.assertEqual(meta["speakers"], ["Fail01"])
        self.assertEqual(meta["total_concepts"], 1)
        self.assertEqual(meta["source"]["tag_id"], DEFAULT_TAG_ID)

    def test_custom_tag_id_filters_correctly(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "1", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "1", "start": 0.0, "end": 0.2, "ipa": "aʂ", "ortho": "aş"}
                        ],
                        # Tagged with a different id — default thesis tag should miss it.
                        "tagged_ids": [],
                    },
                },
            )
            review_data, clip_plan = build_review_data(workspace=workspace)

        self.assertEqual(review_data["concepts"], [])
        self.assertEqual(clip_plan, [])


class WriteOutputsTests(unittest.TestCase):
    def test_skip_audio_emits_json_and_timestamps_only(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "1", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "1", "start": 0.0, "end": 0.4, "ipa": "aʂ", "ortho": "aş"}
                        ],
                        "tagged_ids": ["1"],
                    },
                },
            )
            review_data, clip_plan = build_review_data(workspace=workspace)
            out_dir = Path(tmp) / "out"

            summary = write_outputs(
                workspace=workspace,
                out_dir=out_dir,
                review_data=review_data,
                clip_plan=clip_plan,
                skip_audio=True,
            )

            self.assertTrue((out_dir / "review_data.json").exists())
            self.assertTrue((out_dir / "timestamps" / "Fail01_timestamps.csv").exists())
            self.assertFalse((out_dir / "audio" / "Fail01").exists())
            self.assertEqual(summary["clip_plan_count"], 1)
            self.assertEqual(summary["audio_clipped"], 0)
            self.assertTrue(summary["skipped_audio"])

            # Re-read the written JSON to ensure it round-trips.
            payload = json.loads((out_dir / "review_data.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["concepts"][0]["concept_en"], "ash")

            # Timestamps CSV carries the per-form rows.
            with (out_dir / "timestamps" / "Fail01_timestamps.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["concept_en"], "ash")
            self.assertEqual(rows[0]["ipa"], "aʂ")


class AnalyticalFieldsTests(unittest.TestCase):
    """Cover Lane B — analytical fields from parse-enrichments + contact config."""

    def _two_speaker_ash_workspace(
        self,
        tmp: str,
        *,
        enrichments: dict[str, object] | None = None,
    ) -> Path:
        return _make_workspace(
            Path(tmp),
            concepts=[
                {"id": "1", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
            ],
            speakers={
                "Fail01": {
                    "concept_intervals": [
                        {"concept_id": "1", "start": 0.0, "end": 0.3, "ipa": "aʂ", "ortho": "aş"}
                    ],
                    "tagged_ids": ["1"],
                },
                "Khan01": {
                    "concept_intervals": [],
                    "tagged_ids": [],
                },
            },
            enrichments=enrichments,
        )

    def test_analytical_fields_populated_from_enrichments(self) -> None:
        # Both shapes the legacy and modern schemas key by concept LABEL
        # (with variant suffix). Here the label is just "ash" (no variant).
        enrichments = {
            "cognate_sets": {"ash": {"A": ["Fail01"], "B": ["Khan01"]}},
            "similarity": {
                "ash": {
                    "Fail01": {
                        "ar": {"score": 0.91, "has_reference_data": True},
                        "fa": {"score": 0.42, "has_reference_data": True},
                    },
                    "Khan01": {
                        "ar": {"score": 0.0, "has_reference_data": False},
                        "fa": {"score": 0.10, "has_reference_data": True},
                    },
                }
            },
            "borrowing_flags": {"ash": {"Fail01": "ar"}},
            "lexeme_notes": {},
        }
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp, enrichments=enrichments)
            review_data, _clip_plan = build_review_data(workspace=workspace)

        forms = {f["speaker"]: f for f in review_data["concepts"][0]["forms"]}
        self.assertEqual(forms["Fail01"]["cognate_class"], "A")
        self.assertAlmostEqual(forms["Fail01"]["arabic_similarity"], 0.91)
        self.assertAlmostEqual(forms["Fail01"]["persian_similarity"], 0.42)
        self.assertEqual(forms["Fail01"]["borrowing_flag"], "ar")
        # Khan01 is in group B even though it has no interval (empty form).
        self.assertEqual(forms["Khan01"]["cognate_class"], "B")
        self.assertAlmostEqual(forms["Khan01"]["arabic_similarity"], 0.0)
        self.assertAlmostEqual(forms["Khan01"]["persian_similarity"], 0.10)
        self.assertIsNone(forms["Khan01"]["borrowing_flag"])

    def test_missing_enrichments_falls_back_to_null_defaults(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp)  # no enrichments
            # Confirm the file actually isn't there — regression guard.
            self.assertFalse((workspace / "parse-enrichments.json").exists())
            review_data, _clip_plan = build_review_data(workspace=workspace)

        forms = {f["speaker"]: f for f in review_data["concepts"][0]["forms"]}
        for speaker in ("Fail01", "Khan01"):
            self.assertEqual(forms[speaker]["cognate_class"], "?")
            self.assertEqual(forms[speaker]["arabic_similarity"], 0.0)
            self.assertEqual(forms[speaker]["persian_similarity"], 0.0)
            self.assertIsNone(forms[speaker]["borrowing_flag"])

    def test_contact_language_forms_populated_from_config(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp)
            contact_config = _write_contact_config(
                Path(tmp),
                {
                    "ar": {
                        "name": "Arabic",
                        "concepts": {"ash": [{"form": "رماد", "sources": ["test"]}]},
                    },
                    "fa": {
                        "name": "Persian",
                        # Legacy bare-list shape — exporter must handle it too.
                        "concepts": {"ash": ["خاکستر"]},
                    },
                    "_meta": {"primary_contact_languages": ["ar", "fa"]},
                },
            )
            review_data, _ = build_review_data(
                workspace=workspace,
                contact_config=contact_config,
            )

        concept = review_data["concepts"][0]
        self.assertEqual(concept["arabic"]["form"], "رماد")
        self.assertEqual(concept["arabic"]["ipa"], "")
        self.assertEqual(concept["persian"]["form"], "خاکستر")
        self.assertEqual(concept["persian"]["ipa"], "")

    def test_missing_contact_config_yields_empty_reference_forms(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp)
            review_data, _ = build_review_data(workspace=workspace, contact_config=None)

        concept = review_data["concepts"][0]
        self.assertEqual(concept["arabic"], {"form": "", "ipa": ""})
        self.assertEqual(concept["persian"], {"form": "", "ipa": ""})

    def test_id_keyed_enrichments_resolved(self) -> None:
        # Matches the current python/compare/cognate_compute.py output, which
        # writes ``cognate_sets[concept_id]`` / ``similarity[concept_id]``.
        # Regression guard against PR #497 review finding (id vs label).
        enrichments = {
            "cognate_sets": {"1": {"A": ["Fail01"], "B": ["Khan01"]}},
            "similarity": {
                "1": {
                    "Fail01": {
                        "ar": {"score": 0.81, "has_reference_data": True},
                        "fa": {"score": 0.40, "has_reference_data": True},
                    }
                }
            },
            "borrowing_flags": {"1": {"Fail01": True}},
        }
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp, enrichments=enrichments)
            review_data, _ = build_review_data(workspace=workspace)

        forms = {f["speaker"]: f for f in review_data["concepts"][0]["forms"]}
        self.assertEqual(forms["Fail01"]["cognate_class"], "A")
        self.assertAlmostEqual(forms["Fail01"]["arabic_similarity"], 0.81)
        self.assertAlmostEqual(forms["Fail01"]["persian_similarity"], 0.40)
        self.assertIs(forms["Fail01"]["borrowing_flag"], True)
        self.assertEqual(forms["Khan01"]["cognate_class"], "B")

    def test_variant_suffixed_label_resolved_in_either_key(self) -> None:
        # Concept_en = "ear (A)" — exercise both keying conventions independently.
        ear_concepts = [
            {"id": "7", "concept_en": "ear (A)", "source_item": "31", "source_survey": "JBIL"},
        ]
        ear_speakers = {
            "Fail01": {
                "concept_intervals": [
                    {"concept_id": "7", "start": 0.0, "end": 0.3, "ipa": "gəɫ", "ortho": "gel"}
                ],
                "tagged_ids": ["7"],
            },
        }
        # First: enrichments keyed by concept_id (matches cognate_compute today).
        with TemporaryDirectory() as tmp:
            ws = _make_workspace(
                Path(tmp),
                concepts=ear_concepts,
                speakers=ear_speakers,
                enrichments={"cognate_sets": {"7": {"A": ["Fail01"]}}},
            )
            data_id, _ = build_review_data(workspace=ws)
        self.assertEqual(data_id["concepts"][0]["forms"][0]["cognate_class"], "A")

        # Second: enrichments keyed by label (matches the 2026-04-30 backup format).
        with TemporaryDirectory() as tmp:
            ws = _make_workspace(
                Path(tmp),
                concepts=ear_concepts,
                speakers=ear_speakers,
                enrichments={"cognate_sets": {"ear (A)": {"A": ["Fail01"]}}},
            )
            data_lbl, _ = build_review_data(workspace=ws)
        self.assertEqual(data_lbl["concepts"][0]["forms"][0]["cognate_class"], "A")

    def test_malformed_enrichments_falls_back_safely(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp)
            # Overwrite the file with non-JSON garbage.
            (workspace / "parse-enrichments.json").write_text("{not-json", encoding="utf-8")
            review_data, _ = build_review_data(workspace=workspace)

        forms = {f["speaker"]: f for f in review_data["concepts"][0]["forms"]}
        for speaker in ("Fail01", "Khan01"):
            self.assertEqual(forms[speaker]["cognate_class"], "?")
            self.assertEqual(forms[speaker]["arabic_similarity"], 0.0)
            self.assertIsNone(forms[speaker]["borrowing_flag"])

    def test_non_mapping_enrichments_falls_back_safely(self) -> None:
        # Valid JSON but the top-level is a list / string / number — covers the
        # ``isinstance(data, Mapping)`` guard in ``_load_enrichments``.
        for payload in ("[]", '"oops"', "42"):
            with self.subTest(payload=payload), TemporaryDirectory() as tmp:
                workspace = self._two_speaker_ash_workspace(tmp)
                (workspace / "parse-enrichments.json").write_text(payload, encoding="utf-8")
                review_data, _ = build_review_data(workspace=workspace)
                forms = {f["speaker"]: f for f in review_data["concepts"][0]["forms"]}
                for speaker in ("Fail01", "Khan01"):
                    self.assertEqual(forms[speaker]["cognate_class"], "?")
                    self.assertEqual(forms[speaker]["arabic_similarity"], 0.0)
                    self.assertIsNone(forms[speaker]["borrowing_flag"])

    def test_contact_config_meta_keys_skipped(self) -> None:
        # ``_meta`` and other underscore-prefixed top-level keys are metadata,
        # not language codes — mirrors contact_lexeme_fetcher's own filter.
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp)
            contact_config = _write_contact_config(
                Path(tmp),
                {
                    "_meta": {"primary_contact_languages": ["ar"]},
                    "ar": {"name": "Arabic", "concepts": {"ash": [{"form": "رماد", "sources": []}]}},
                },
            )
            review_data, _ = build_review_data(
                workspace=workspace,
                contact_config=contact_config,
            )

        concept = review_data["concepts"][0]
        self.assertEqual(concept["arabic"]["form"], "رماد")
        # ``_meta`` must not surface as a fake language — assert persian stays empty.
        self.assertEqual(concept["persian"], {"form": "", "ipa": ""})

    def test_similarity_score_none_treated_as_zero(self) -> None:
        # cognate_compute.SimilarityScore["score"] is Optional[float]; PARSE
        # writes ``None`` when refs are missing. Our exporter must treat that
        # as 0.0, not crash, not emit ``None``.
        enrichments = {
            "similarity": {
                "1": {
                    "Fail01": {
                        "ar": {"score": None, "has_reference_data": False},
                        "fa": {"score": 0.5, "has_reference_data": True},
                    }
                }
            },
        }
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp, enrichments=enrichments)
            review_data, _ = build_review_data(workspace=workspace)

        form = next(f for f in review_data["concepts"][0]["forms"] if f["speaker"] == "Fail01")
        self.assertEqual(form["arabic_similarity"], 0.0)
        self.assertAlmostEqual(form["persian_similarity"], 0.5)

    def test_summary_carries_analytical_coverage_counts(self) -> None:
        enrichments = {
            "cognate_sets": {"ash": {"A": ["Fail01"]}},
            "similarity": {
                "ash": {
                    "Fail01": {
                        "ar": {"score": 0.5, "has_reference_data": True},
                        # no fa entry — persian_similarity stays 0.0
                    }
                }
            },
            "borrowing_flags": {},
        }
        with TemporaryDirectory() as tmp:
            workspace = self._two_speaker_ash_workspace(tmp, enrichments=enrichments)
            contact_config = _write_contact_config(
                Path(tmp),
                {"ar": {"concepts": {"ash": [{"form": "رماد", "sources": []}]}}},
            )
            review_data, clip_plan = build_review_data(
                workspace=workspace,
                contact_config=contact_config,
            )
            summary = write_outputs(
                workspace=workspace,
                out_dir=Path(tmp) / "out",
                review_data=review_data,
                clip_plan=clip_plan,
                skip_audio=True,
            )

        coverage = summary["analytical_coverage"]
        self.assertEqual(coverage["forms_with_cognate_class"], 1)        # Fail01 has class A
        self.assertEqual(coverage["forms_with_arabic_similarity"], 1)    # Fail01 ar=0.5
        self.assertEqual(coverage["forms_with_persian_similarity"], 0)
        self.assertEqual(coverage["forms_with_borrowing_flag"], 0)
        self.assertEqual(coverage["concepts_with_arabic_ref"], 1)
        self.assertEqual(coverage["concepts_with_persian_ref"], 0)


class SpeakerFilterTests(unittest.TestCase):
    """Lane F: --speakers / speaker_filter restricts which speakers ship."""

    @staticmethod
    def _three_speaker_workspace(tmp: str) -> Path:
        return _make_workspace(
            Path(tmp),
            concepts=[
                {"id": "1", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
            ],
            speakers={
                "Fail01": {
                    "concept_intervals": [
                        {"concept_id": "1", "start": 0.0, "end": 0.3, "ipa": "aʂ", "ortho": "aş"}
                    ],
                    "tagged_ids": ["1"],
                },
                "Fail02": {
                    "concept_intervals": [
                        {"concept_id": "1", "start": 1.0, "end": 1.4, "ipa": "aʃ", "ortho": "as"}
                    ],
                    "tagged_ids": ["1"],
                },
                "Khan01": {
                    "concept_intervals": [
                        {"concept_id": "1", "start": 2.0, "end": 2.5, "ipa": "ax", "ortho": "akh"}
                    ],
                    "tagged_ids": ["1"],
                },
            },
        )

    def test_speaker_filter_restricts_output(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = self._three_speaker_workspace(tmp)
            review_data, clip_plan = build_review_data(
                workspace=workspace,
                speaker_filter=["Fail01", "Khan01"],
            )

        self.assertEqual(review_data["metadata"]["speakers"], ["Fail01", "Khan01"])
        forms = review_data["concepts"][0]["forms"]
        self.assertEqual([f["speaker"] for f in forms], ["Fail01", "Khan01"])
        self.assertEqual(len(clip_plan), 2)
        # Fail02 must not surface in either the schema or the clip plan.
        all_clip_speakers = {spec["speaker"] for _, spec in clip_plan}
        self.assertNotIn("Fail02", all_clip_speakers)

    def test_speaker_filter_preserves_project_json_order(self) -> None:
        # project.json insertion order is Fail01, Fail02, Khan01; filter input
        # order Khan01, Fail01 should NOT reorder the output.
        with TemporaryDirectory() as tmp:
            workspace = self._three_speaker_workspace(tmp)
            review_data, _ = build_review_data(
                workspace=workspace,
                speaker_filter=["Khan01", "Fail01"],
            )

        self.assertEqual(review_data["metadata"]["speakers"], ["Fail01", "Khan01"])

    def test_unknown_speaker_raises_value_error(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = self._three_speaker_workspace(tmp)
            with self.assertRaises(ValueError) as ctx:
                build_review_data(
                    workspace=workspace,
                    speaker_filter=["Fail01", "Notreal99"],
                )
            self.assertIn("Notreal99", str(ctx.exception))

    def test_empty_or_none_filter_keeps_all_speakers(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = self._three_speaker_workspace(tmp)
            data_none, _ = build_review_data(workspace=workspace, speaker_filter=None)
            data_empty, _ = build_review_data(workspace=workspace, speaker_filter=[])

        self.assertEqual(data_none["metadata"]["speakers"], ["Fail01", "Fail02", "Khan01"])
        self.assertEqual(data_empty["metadata"]["speakers"], ["Fail01", "Fail02", "Khan01"])


def _write_legacy_anchor(tmp_path: Path, concepts: list[dict[str, object]]) -> Path:
    """Write a minimal legacy review_data.json and return its path."""
    path = tmp_path / "legacy_review_data.json"
    payload = {
        "metadata": {"version": LEGACY_SCHEMA_VERSION, "speakers": []},
        "concepts": concepts,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class CrosstierTextTests(unittest.TestCase):
    """The cross-tier IPA/ortho join is the load-bearing primitive of anchored mode."""

    def _payload(self, ipa_intervals: list[dict[str, object]]) -> dict[str, object]:
        return {"tiers": {"ipa": {"intervals": ipa_intervals}}}

    def test_returns_text_when_conceptid_matches(self) -> None:
        payload = self._payload([
            {"start": 1.0, "end": 1.5, "text": "ɡap", "conceptId": "634"},
        ])
        self.assertEqual(_crosstier_text(payload, "ipa", {"634"}, 1.0, 1.5), "ɡap")

    def test_falls_back_to_time_overlap_when_conceptid_absent(self) -> None:
        # Manually-adjusted IPA intervals drop the conceptId link — they must
        # still resolve via time-range overlap with the concept-tier interval.
        payload = self._payload([
            {"start": 3492.305, "end": 3493.186, "text": "ɡap", "manuallyAdjusted": True},
        ])
        self.assertEqual(_crosstier_text(payload, "ipa", {"634"}, 3492.305, 3493.186), "ɡap")

    def test_prefers_conceptid_match_over_time_overlap(self) -> None:
        # If both kinds of candidate exist, the conceptId match wins.
        payload = self._payload([
            {"start": 5.0, "end": 6.0, "text": "wrong"},
            {"start": 5.0, "end": 6.0, "text": "right", "conceptId": "634"},
        ])
        self.assertEqual(_crosstier_text(payload, "ipa", {"634"}, 5.0, 6.0), "right")

    def test_returns_none_when_no_match(self) -> None:
        payload = self._payload([
            {"start": 100.0, "end": 101.0, "text": "elsewhere"},
        ])
        self.assertIsNone(_crosstier_text(payload, "ipa", {"634"}, 5.0, 6.0))

    def test_missing_tier_returns_none(self) -> None:
        self.assertIsNone(_crosstier_text({"tiers": {}}, "ipa", {"634"}, 1.0, 2.0))
        self.assertIsNone(_crosstier_text({}, "ipa", {"634"}, 1.0, 2.0))

    def test_largest_overlap_wins_for_time_fallback(self) -> None:
        # Two overlapping intervals — pick the one with the most overlap.
        payload = self._payload([
            {"start": 0.9, "end": 1.1, "text": "edge"},      # 0.1s overlap with [1.0, 2.0]
            {"start": 1.0, "end": 2.0, "text": "center"},    # 1.0s overlap
            {"start": 1.5, "end": 5.0, "text": "trailing"},  # 0.5s overlap
        ])
        self.assertEqual(_crosstier_text(payload, "ipa", set(), 1.0, 2.0), "center")


class LegacyAnchoredTests(unittest.TestCase):
    """End-to-end tests for build_review_data_anchored."""

    def _ash_workspace_and_anchor(self, tmp: str) -> tuple[Path, Path]:
        """Two PARSE rows for 'ash' (variant pollution); one speaker has data.

        Legacy carries the canonical concept_id=132 for ash, with Arabic and
        Persian reference forms. The exporter should collapse both PARSE rows
        into one entry preserving the legacy concept_id and references.
        """
        workspace = _make_workspace(
            Path(tmp),
            concepts=[
                # PARSE pollution: two rows for the same gloss, different concept_ids.
                {"id": "1", "concept_en": "ash (A)", "source_item": "1.1", "source_survey": "KLQ"},
                {"id": "2", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
            ],
            speakers={
                "Fail01": {
                    "concept_intervals": [
                        # Speaker only tagged concept_id="2" — but legacy looks for "ash" globally.
                        {"concept_id": "2", "start": 0.5, "end": 1.25}
                    ],
                    "tagged_ids": ["2"],
                    "ipa_intervals": [
                        {"start": 0.5, "end": 1.25, "text": "aʂ", "conceptId": "2"}
                    ],
                    "ortho_intervals": [
                        {"start": 0.5, "end": 1.25, "text": "aş", "conceptId": "2"}
                    ],
                },
                "Kalh01": {
                    "concept_intervals": [],
                    "tagged_ids": [],
                },
            },
        )
        anchor = _write_legacy_anchor(
            Path(tmp),
            concepts=[
                {
                    "concept_id": "132",
                    "concept_en": "ash",
                    "arabic": {"form": "رماد", "ipa": "ramaːd"},
                    "persian": {"form": "خاکستر", "ipa": "xɑːkestær"},
                    "forms": [
                        {"speaker": "Fail01", "source": "JBIL"},
                        {"speaker": "Kalh01", "source": "JBIL"},
                    ],
                }
            ],
        )
        return workspace, anchor

    def test_anchored_collapses_polluted_concepts_csv_to_one_entry(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace, anchor = self._ash_workspace_and_anchor(tmp)
            review_data, clip_plan = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        # ONE concept entry per legacy entry, not two for "ash" + "ash (A)".
        self.assertEqual(len(review_data["concepts"]), 1)
        concept = review_data["concepts"][0]
        # Legacy concept identity preserved.
        self.assertEqual(concept["concept_id"], "132")
        self.assertEqual(concept["concept_en"], "ash")
        self.assertEqual(concept["arabic"], {"form": "رماد", "ipa": "ramaːd"})
        self.assertEqual(concept["persian"], {"form": "خاکستر", "ipa": "xɑːkestær"})

    def test_anchored_recovers_per_speaker_ipa_and_ortho_via_crosstier_join(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace, anchor = self._ash_workspace_and_anchor(tmp)
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        forms = {f["speaker"]: f for f in review_data["concepts"][0]["forms"]}
        # Fail01 had a single interval — cross-tier join finds the matching IPA/ortho.
        self.assertEqual(forms["Fail01"]["ipa"], "aʂ")
        self.assertEqual(forms["Fail01"]["ortho"], "aş")
        self.assertEqual(forms["Fail01"]["source"], "JBIL")
        self.assertEqual(
            forms["Fail01"]["audio_path"],
            "audio/Fail01/JBIL_132_A_ash_Fail01.wav",
        )
        # Kalh01 has no interval → legacy null defaults.
        self.assertEqual(forms["Kalh01"]["ipa"], "?")
        self.assertEqual(forms["Kalh01"]["ortho"], "")
        self.assertIsNone(forms["Kalh01"]["audio_path"])

    def test_anchored_picks_longest_interval_when_speaker_has_multiple(self) -> None:
        # Polluted concepts.csv → speaker has intervals for both concept_ids
        # (e.g. they tagged 'big' and 'big (A)' separately). Anchored mode
        # picks the longest one as the representative realization.
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "53", "concept_en": "big (A)", "source_item": "4.1", "source_survey": "KLQ"},
                    {"id": "634", "concept_en": "big", "source_item": "4.1", "source_survey": "KLQ"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "53", "start": 1000.0, "end": 1000.2},   # 0.2s
                            {"concept_id": "634", "start": 3492.305, "end": 3493.186},  # 0.881s — longer
                        ],
                        "tagged_ids": ["53", "634"],
                        "ipa_intervals": [
                            {"start": 1000.0, "end": 1000.2, "text": "short", "conceptId": "53"},
                            {"start": 3492.305, "end": 3493.186, "text": "ɡap", "manuallyAdjusted": True},
                        ],
                        "ortho_intervals": [
                            {"start": 3492.305, "end": 3493.186, "text": "گەپ", "manuallyAdjusted": True},
                        ],
                    },
                },
            )
            anchor = _write_legacy_anchor(
                Path(tmp),
                concepts=[
                    {
                        "concept_id": "169",
                        "concept_en": "big",
                        "arabic": {"form": "كبير", "ipa": "kabiːr"},
                        "persian": {"form": "بزرگ", "ipa": "bozorɡ"},
                        "forms": [{"speaker": "Fail01", "source": "JBIL"}],
                    }
                ],
            )
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        form = review_data["concepts"][0]["forms"][0]
        # Longest interval wins → IPA via time-overlap fallback ('ɡap') not 'short'.
        self.assertEqual(form["ipa"], "ɡap")
        self.assertEqual(form["ortho"], "گەپ")
        self.assertAlmostEqual(form["start_sec"], 3492.305)
        self.assertAlmostEqual(form["duration_sec"], 0.881, places=2)
        self.assertEqual(
            form["audio_path"],
            "audio/Fail01/JBIL_169_A_big_Fail01.wav",
        )

    def test_anchored_unmatched_legacy_concept_emits_empty_forms(self) -> None:
        # A legacy concept with no matching PARSE row (e.g. legacy 'egg' but
        # PARSE has no 'egg' row) must still emit an entry — committee sees the
        # concept's reference forms even when no speaker has annotated it.
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "1", "concept_en": "ash", "source_item": "1.1", "source_survey": "KLQ"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [],
                        "tagged_ids": [],
                    },
                },
            )
            anchor = _write_legacy_anchor(
                Path(tmp),
                concepts=[
                    {
                        "concept_id": "141",
                        "concept_en": "egg (e.g., chicken)",
                        "arabic": {"form": "بيضة", "ipa": "bajdˤah"},
                        "persian": {"form": "تخم‌مرغ", "ipa": ""},
                        "forms": [{"speaker": "Fail01", "source": "JBIL"}],
                    }
                ],
            )
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        # Concept retained even though no PARSE row matched.
        self.assertEqual(len(review_data["concepts"]), 1)
        concept = review_data["concepts"][0]
        self.assertEqual(concept["concept_id"], "141")
        self.assertEqual(concept["arabic"]["form"], "بيضة")
        # Speaker's form is empty.
        self.assertEqual(concept["forms"][0]["ipa"], "?")
        self.assertIsNone(concept["forms"][0]["audio_path"])
        # Metadata names the unmatched concept so callers can audit.
        self.assertIn("egg (e.g., chicken)", review_data["metadata"]["source"]["unmatched_legacy_concepts"])

    def test_anchored_metadata_carries_legacy_anchor_path_and_speaker_filter(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace, anchor = self._ash_workspace_and_anchor(tmp)
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
                speaker_filter=["Fail01"],
            )

        meta = review_data["metadata"]
        self.assertEqual(meta["method"], "parse_workspace_export_legacy_anchored")
        self.assertEqual(meta["speakers"], ["Fail01"])
        self.assertEqual(meta["source"]["legacy_anchor"], str(anchor))
        # Speaker filter applied: Kalh01 excluded.
        forms = review_data["concepts"][0]["forms"]
        self.assertEqual([f["speaker"] for f in forms], ["Fail01"])


class StemLabelParenStrippingTests(unittest.TestCase):
    """MC-415-B: _stem_label must strip arbitrary parenthetical qualifiers, not
    only single-token variant suffixes, so anchored matching reaches legacy
    glosses like 'egg' / 'fly' / 'you' that PARSE carries as 'egg (e.g., chicken)' etc."""

    def test_strips_meaning_qualifier_with_punctuation(self) -> None:
        self.assertEqual(_stem_label("egg (e.g., chicken)"), "egg")
        self.assertEqual(_stem_label("fly (n.)"), "fly")
        self.assertEqual(_stem_label("you (sg.)"), "you")
        self.assertEqual(_stem_label("you (pl.)"), "you")
        self.assertEqual(_stem_label("to knock (at the door)"), "to knock")
        self.assertEqual(
            _stem_label("hard (like a stone, opposite of soft 'nerm')"),
            "hard",
        )

    def test_strips_chained_qualifier_then_variant(self) -> None:
        # PARSE issue #529 produces chained suffixes like 'egg (e.g., chicken) (A)'.
        # Both layers must fold away so the gloss matches legacy 'egg'.
        self.assertEqual(_stem_label("egg (e.g., chicken) (A)"), "egg")
        self.assertEqual(_stem_label("long (thing) (B)"), "long")

    def test_preserves_simple_alphanumeric_variant_behaviour(self) -> None:
        # MC-415-A behaviour stays intact for plain variant suffixes.
        self.assertEqual(_stem_label("dog (A)"), "dog")
        self.assertEqual(_stem_label("big (F)"), "big")
        self.assertEqual(_stem_label("dog"), "dog")
        self.assertEqual(_stem_label(""), "")

    def test_variant_letter_unchanged_by_broadening(self) -> None:
        # _variant_letter uses the narrow regex on purpose so meaning
        # qualifiers don't surface as bogus variant codes.
        self.assertEqual(_variant_letter("egg (e.g., chicken) (A)"), "A")
        self.assertEqual(_variant_letter("egg (e.g., chicken)"), "")
        self.assertEqual(_variant_letter("dog (A)"), "A")
        self.assertEqual(_variant_letter("big (F)"), "F")
        self.assertEqual(_variant_letter("dog"), "")

    def test_anchored_recovers_legacy_egg_via_paren_qualifier_strip(self) -> None:
        """Regression guard for the 2026-05-19 deploy: 'egg' was unmatched
        because PARSE carried 'egg (e.g., chicken)' and the old narrow regex
        couldn't fold the qualifier away."""
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "1", "concept_en": "egg (e.g., chicken)", "source_item": "141", "source_survey": "JBIL"},
                    {"id": "2", "concept_en": "egg (e.g., chicken) (A)", "source_item": "141", "source_survey": "JBIL"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "1", "start": 100.0, "end": 100.6}
                        ],
                        "tagged_ids": ["1"],
                        "ipa_intervals": [
                            {"start": 100.0, "end": 100.6, "text": "hek", "conceptId": "1"}
                        ],
                        "ortho_intervals": [
                            {"start": 100.0, "end": 100.6, "text": "هێک", "conceptId": "1"}
                        ],
                    }
                },
            )
            anchor = _write_legacy_anchor(
                Path(tmp),
                concepts=[
                    {
                        "concept_id": "141",
                        "concept_en": "egg",
                        "arabic": {"form": "بيض", "ipa": "bajd"},
                        "persian": {"form": "تخم مرغ", "ipa": ""},
                        "forms": [{"speaker": "Fail01", "source": "JBIL"}],
                    }
                ],
            )
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        self.assertEqual(review_data["concepts"][0]["concept_en"], "egg")
        # 'egg' is no longer in unmatched_legacy.
        self.assertNotIn("egg", review_data["metadata"]["source"]["unmatched_legacy_concepts"])
        # Speaker's form is populated, not the legacy-null empty form.
        form = review_data["concepts"][0]["forms"][0]
        self.assertEqual(form["ipa"], "hek")
        self.assertEqual(form["ortho"], "هێک")
        self.assertEqual(form["audio_path"], "audio/Fail01/JBIL_141_A_egg_Fail01.wav")


class StemLabelLeadingNumberPrefixTests(unittest.TestCase):
    """MC-415-C: _stem_label must also strip a leading '<number> ' prefix.

    PARSE's concepts.csv carries 2 rows where the Audition cue number escaped
    parse_cue_name normalization and got glued onto concept_en: id=611
    ``'56 skin'`` and id=610 ``'48 stomach (organ)'``. The exporter defends
    against this so anchored matching reaches the canonical legacy gloss.
    """

    def test_strips_simple_numeric_prefix(self) -> None:
        self.assertEqual(_stem_label("56 skin"), "skin")
        self.assertEqual(_stem_label("1 ash"), "ash")
        self.assertEqual(_stem_label("141 egg"), "egg")

    def test_strips_dotted_numeric_prefix(self) -> None:
        # Survey item ids can carry a dotted form (e.g. KLQ '1.1', '4.19').
        self.assertEqual(_stem_label("1.1 ash"), "ash")
        self.assertEqual(_stem_label("4.19 good"), "good")

    def test_combines_prefix_and_trailing_paren_strip(self) -> None:
        # Real-world id=610: "48 stomach (organ)" should fold to "stomach".
        self.assertEqual(_stem_label("48 stomach (organ)"), "stomach")
        self.assertEqual(_stem_label("169 big (A)"), "big")
        self.assertEqual(_stem_label("32 hair (men)"), "hair")

    def test_does_not_strip_alphabetic_prefix(self) -> None:
        # Only leading runs of digits (with optional dots) qualify as a prefix.
        # Don't accidentally swallow words that happen to start a label.
        self.assertEqual(_stem_label("to bathe"), "to bathe")
        self.assertEqual(_stem_label("the boy cut"), "the boy cut")
        self.assertEqual(_stem_label("3rd person"), "3rd person")

    def test_anchored_recovers_legacy_skin_via_leading_number_strip(self) -> None:
        """Regression guard for the 2026-05-19 Khan02 'skin' miss: PARSE row
        id=611 carries concept_en '56 skin' and the speaker's interval
        references id=611. Anchored matching against legacy gloss 'skin'
        only succeeds when the prefix is stripped."""
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "277", "concept_en": "skin", "source_item": "56", "source_survey": "JBIL"},
                    {"id": "611", "concept_en": "56 skin", "source_item": "56", "source_survey": "JBIL"},
                ],
                speakers={
                    "Khan02": {
                        "concept_intervals": [
                            {"concept_id": "611", "start": 5330.0, "end": 5331.247, "text": "skin"}
                        ],
                        # Note: Khan02 did NOT tag concept 611 — only has the
                        # interval. Anchored mode doesn't gate on the thesis tag.
                        "tagged_ids": [],
                        "ipa_intervals": [
                            {"start": 5330.0, "end": 5331.247, "text": "puːse"}
                        ],
                        "ortho_intervals": [
                            {"start": 5330.0, "end": 5331.247, "text": "پۊسە"}
                        ],
                    }
                },
            )
            anchor = _write_legacy_anchor(
                Path(tmp),
                concepts=[
                    {
                        "concept_id": "56",
                        "concept_en": "skin",
                        "arabic": {"form": "جلد", "ipa": "ʒild"},
                        "persian": {"form": "پوست", "ipa": "puːst"},
                        "forms": [{"speaker": "Khan02", "source": "JBIL"}],
                    }
                ],
            )
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        self.assertEqual(review_data["concepts"][0]["concept_en"], "skin")
        # 'skin' is not in unmatched_legacy_concepts.
        self.assertNotIn("skin", review_data["metadata"]["source"]["unmatched_legacy_concepts"])
        # Khan02's form is populated despite tagging neither concept_id.
        form = review_data["concepts"][0]["forms"][0]
        self.assertEqual(form["ipa"], "puːse")
        self.assertEqual(form["ortho"], "پۊسە")
        self.assertEqual(form["audio_path"], "audio/Khan02/JBIL_56_A_skin_Khan02.wav")


class AnchoredAuditionPrefixSelectionTests(unittest.TestCase):
    """MC-415-D: when a speaker has multiple concept-tier intervals at the
    same concept_id (PARSE collapses cross-survey readings together), the
    anchored exporter must prefer the interval whose ``audition_prefix``
    matches the legacy concept_id rather than blindly picking the longest.

    Regression case: Fail01 'sister' had two intervals at concept_id=16, one
    with audition_prefix='75' (JBIL 75 — the legacy source) and one with
    audition_prefix='2.5' (KLQ 2.5). The longest was the KLQ one, whose
    cross-tier IPA was 'xoʃokdubaːre' / ortho 'دو' — clearly wrong for
    'sister'. The JBIL one carries the canonical 'xoʃkaɡam' / 'خوشکەگەم'.
    """

    @staticmethod
    def _ws_with_two_sister_intervals(tmp: str) -> Path:
        return _make_workspace(
            Path(tmp),
            concepts=[
                {"id": "16", "concept_en": "sister", "source_item": "2.5", "source_survey": "KLQ"},
            ],
            speakers={
                "Fail01": {
                    "concept_intervals": [
                        {"concept_id": "16", "start": 1503.554, "end": 1504.315,
                         "text": "sister", "audition_prefix": "75"},
                        {"concept_id": "16", "start": 6631.295, "end": 6632.249,
                         "text": "sister", "audition_prefix": "2.5"},
                    ],
                    "tagged_ids": ["16"],
                    "ipa_intervals": [
                        {"start": 1503.554, "end": 1504.315, "text": "xoʃkaɡam", "conceptId": "16"},
                        {"start": 6631.295, "end": 6632.249, "text": "xoʃokdubaːre", "conceptId": "16"},
                    ],
                    "ortho_intervals": [
                        {"start": 1503.554, "end": 1504.315, "text": "خوشکەگەم", "conceptId": "16"},
                        {"start": 6631.295, "end": 6632.249, "text": "دو", "conceptId": "16"},
                    ],
                },
            },
        )

    def test_audition_prefix_matching_legacy_id_wins_over_longest(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = self._ws_with_two_sister_intervals(tmp)
            anchor = _write_legacy_anchor(
                Path(tmp),
                concepts=[
                    {
                        "concept_id": "75",
                        "concept_en": "sister",
                        "arabic": {"form": "أخت", "ipa": "ʔuxt;uxut"},
                        "persian": {"form": "خاهر", "ipa": "xaːhær"},
                        "forms": [{"speaker": "Fail01", "source": "JBIL"}],
                    }
                ],
            )
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        form = review_data["concepts"][0]["forms"][0]
        self.assertEqual(form["ipa"], "xoʃkaɡam")
        self.assertEqual(form["ortho"], "خوشکەگەم")
        self.assertAlmostEqual(form["start_sec"], 1503.554)
        self.assertAlmostEqual(form["duration_sec"], 0.761, places=2)
        self.assertEqual(form["audio_path"], "audio/Fail01/JBIL_75_A_sister_Fail01.wav")

    def test_falls_back_to_longest_when_no_audition_prefix_matches(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "16", "concept_en": "sister", "source_item": "2.5", "source_survey": "KLQ"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "16", "start": 10.0, "end": 10.5,
                             "text": "sister", "audition_prefix": "2.5"},
                            {"concept_id": "16", "start": 20.0, "end": 21.2,
                             "text": "sister", "audition_prefix": "2.17"},
                        ],
                        "tagged_ids": ["16"],
                        "ipa_intervals": [
                            {"start": 10.0, "end": 10.5, "text": "short_realization", "conceptId": "16"},
                            {"start": 20.0, "end": 21.2, "text": "long_realization", "conceptId": "16"},
                        ],
                    },
                },
            )
            anchor = _write_legacy_anchor(
                Path(tmp),
                concepts=[
                    {
                        "concept_id": "75",
                        "concept_en": "sister",
                        "arabic": {"form": "", "ipa": ""},
                        "persian": {"form": "", "ipa": ""},
                        "forms": [{"speaker": "Fail01", "source": "JBIL"}],
                    }
                ],
            )
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        form = review_data["concepts"][0]["forms"][0]
        self.assertEqual(form["ipa"], "long_realization")
        self.assertAlmostEqual(form["duration_sec"], 1.2, places=2)

    def test_audition_prefix_filter_picks_longest_within_matches(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = _make_workspace(
                Path(tmp),
                concepts=[
                    {"id": "16", "concept_en": "sister", "source_item": "2.5", "source_survey": "KLQ"},
                ],
                speakers={
                    "Fail01": {
                        "concept_intervals": [
                            {"concept_id": "16", "start": 10.0, "end": 10.5,
                             "text": "sister", "audition_prefix": "75"},
                            {"concept_id": "16", "start": 20.0, "end": 21.4,
                             "text": "sister", "audition_prefix": "75"},
                            {"concept_id": "16", "start": 30.0, "end": 32.0,
                             "text": "sister", "audition_prefix": "2.5"},
                        ],
                        "tagged_ids": ["16"],
                        "ipa_intervals": [
                            {"start": 10.0, "end": 10.5, "text": "first_jbil", "conceptId": "16"},
                            {"start": 20.0, "end": 21.4, "text": "second_jbil_longer", "conceptId": "16"},
                            {"start": 30.0, "end": 32.0, "text": "klq_longest_but_wrong_survey", "conceptId": "16"},
                        ],
                    },
                },
            )
            anchor = _write_legacy_anchor(
                Path(tmp),
                concepts=[
                    {
                        "concept_id": "75",
                        "concept_en": "sister",
                        "arabic": {"form": "", "ipa": ""},
                        "persian": {"form": "", "ipa": ""},
                        "forms": [{"speaker": "Fail01", "source": "JBIL"}],
                    }
                ],
            )
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        form = review_data["concepts"][0]["forms"][0]
        self.assertEqual(form["ipa"], "second_jbil_longer")
        self.assertAlmostEqual(form["start_sec"], 20.0)

    def test_legacy_id_unset_keeps_longest_fallback(self) -> None:
        # Defensive: when legacy concept_id is empty, no filtering happens.
        with TemporaryDirectory() as tmp:
            workspace = self._ws_with_two_sister_intervals(tmp)
            anchor = _write_legacy_anchor(
                Path(tmp),
                concepts=[
                    {
                        "concept_id": "",
                        "concept_en": "sister",
                        "arabic": {"form": "", "ipa": ""},
                        "persian": {"form": "", "ipa": ""},
                        "forms": [{"speaker": "Fail01", "source": "JBIL"}],
                    }
                ],
            )
            review_data, _ = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=anchor,
            )

        form = review_data["concepts"][0]["forms"][0]
        # No filtering → longest wins → the KLQ interval (the bug case).
        self.assertEqual(form["ipa"], "xoʃokdubaːre")


if __name__ == "__main__":
    unittest.main()
