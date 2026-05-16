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


def _make_workspace(
    tmp_path: Path,
    *,
    concepts: list[dict[str, str]],
    speakers: dict[str, dict[str, object]],
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


if __name__ == "__main__":
    unittest.main()
