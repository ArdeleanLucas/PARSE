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
    build_review_data,
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
        annotation = {
            "version": 1,
            "speaker": speaker,
            "source_audio": f"audio/working/{speaker}/{speaker}.wav",
            "tiers": {
                "concept": {
                    "display_order": 3,
                    "type": "interval",
                    "intervals": list(intervals),
                }
            },
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


if __name__ == "__main__":
    unittest.main()
