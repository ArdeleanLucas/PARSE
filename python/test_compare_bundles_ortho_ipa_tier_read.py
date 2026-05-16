from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from compare_bundles import build_compare_bundles

FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


def _seed_concepts(root: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with (root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})


def _seed_annotation(
    root: pathlib.Path,
    speaker: str,
    *,
    concept_intervals: list[dict],
    ortho_intervals: list[dict] | None = None,
    ipa_intervals: list[dict] | None = None,
) -> None:
    annotations = root / "annotations"
    annotations.mkdir(exist_ok=True)
    tiers = {"concept": {"intervals": concept_intervals}}
    if ortho_intervals is not None:
        tiers["ortho"] = {"intervals": ortho_intervals}
    if ipa_intervals is not None:
        tiers["ipa"] = {"intervals": ipa_intervals}
    payload = {
        "speaker": speaker,
        "source_audio": f"audio/working/{speaker}/{speaker}.wav",
        "tiers": tiers,
    }
    (annotations / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")


def test_candidate_ortho_and_ipa_are_read_from_matching_tiers(tmp_path: pathlib.Path) -> None:
    _seed_concepts(
        tmp_path,
        [{"id": "53", "concept_en": "big (A)", "source_item": "4.1", "source_survey": "KLQ", "custom_order": "53"}],
    )
    _seed_annotation(
        tmp_path,
        "Saha01",
        concept_intervals=[{"start": 1.0, "end": 2.0, "text": "big (A)", "concept_id": "53"}],
        ortho_intervals=[{"start": 1.0, "end": 2.0, "text": "گەورە", "conceptId": "53"}],
        ipa_intervals=[{"start": 1.0, "end": 2.0, "text": "ɡeːrɔ", "conceptId": "53"}],
    )

    result = build_compare_bundles(tmp_path, speakers=["Saha01"], bundle_id="bundle:big")
    candidate = result["bundles"][0]["candidates"]["Saha01"]["53"]

    assert candidate["ortho"] == "گەورە"
    assert candidate["ipa"] == "ɡeːrɔ"
    assert candidate["ortho"] != "big (A)"


def test_candidate_missing_ortho_and_ipa_tiers_do_not_fall_back_to_concept_text(tmp_path: pathlib.Path) -> None:
    _seed_concepts(
        tmp_path,
        [{"id": "77", "concept_en": "hair (A)", "source_item": "2.2", "source_survey": "KLQ", "custom_order": "77"}],
    )
    _seed_annotation(
        tmp_path,
        "Saha01",
        concept_intervals=[{"start": 3.0, "end": 4.0, "text": "hair (A)", "concept_id": "77"}],
    )

    result = build_compare_bundles(tmp_path, speakers=["Saha01"], bundle_id="bundle:hair")
    candidate = result["bundles"][0]["candidates"]["Saha01"]["77"]

    assert candidate["ortho"] == ""
    assert candidate["ipa"] is None
