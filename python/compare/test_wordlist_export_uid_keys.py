"""export_wordlist_tsv must resolve cognate membership across legacy/uid keys.

Regression for MC-469: a concept keyed both legacy (``"1"``) and uid (``"c-1"``),
where the uid block carries a speaker assigned after the uid migration, must code
that speaker with the group's COGID — not COGID 0 (ungrouped) read from the stale
legacy block. The same path must keep working once the file is collapsed to
uid-only keys (the data migration), because annotation forms are csv-id keyed.
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compare.cognate_compute import export_wordlist_tsv


def _seed(tmp_path: pathlib.Path, cognate_sets: dict) -> pathlib.Path:
    with (tmp_path / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "I", "source_item": "319", "source_survey": "JBIL", "custom_order": "1"})
    annotations = tmp_path / "annotations"
    annotations.mkdir()
    for speaker in ("Fail01", "Saha01", "Khan02"):
        # IPA is read from a separate time-aligned "ipa" tier overlapping the
        # concept window — not from a field on the concept interval.
        (annotations / f"{speaker}.parse.json").write_text(
            json.dumps({
                "version": 1,
                "speaker": speaker,
                "tiers": {
                    "concept": {"type": "interval", "intervals": [
                        {"concept_id": "1", "start": 1.0, "end": 2.0, "text": "I"},
                    ]},
                    "ipa": {"type": "interval", "intervals": [
                        {"start": 1.0, "end": 2.0, "text": "mɛn"},
                    ]},
                    "ortho": {"type": "interval", "intervals": [
                        {"start": 1.0, "end": 2.0, "text": "من"},
                    ]},
                },
            }),
            encoding="utf-8",
        )
    (tmp_path / "parse-enrichments.json").write_text(
        json.dumps({"manual_overrides": {"cognate_sets": cognate_sets}}),
        encoding="utf-8",
    )
    return tmp_path / "parse-enrichments.json"


def _cogids_by_speaker(tsv_path: pathlib.Path) -> dict:
    rows = list(csv.DictReader(tsv_path.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
    return {row["DOCULECT"]: row["COGID"] for row in rows}


def test_wordlist_groups_late_speaker_under_divergent_dual_keys(tmp_path: pathlib.Path) -> None:
    enrichments_path = _seed(tmp_path, {
        "1": {"A": ["Fail01", "Saha01"]},              # legacy — stale
        "c-1": {"A": ["Fail01", "Saha01", "Khan02"]},  # uid — current
    })
    out = tmp_path / "wordlist.tsv"
    export_wordlist_tsv(enrichments_path, tmp_path / "annotations", out)

    cogids = _cogids_by_speaker(out)
    # All three share one cognate set -> same non-zero COGID. Khan02 must not be 0.
    assert cogids["Khan02"] != "0", cogids
    assert cogids["Khan02"] == cogids["Fail01"] == cogids["Saha01"], cogids


def test_wordlist_groups_speaker_under_uid_only_keys(tmp_path: pathlib.Path) -> None:
    # Post-migration state: only the uid key remains; forms are still csv-id keyed.
    enrichments_path = _seed(tmp_path, {"c-1": {"A": ["Fail01", "Saha01", "Khan02"]}})
    out = tmp_path / "wordlist.tsv"
    export_wordlist_tsv(enrichments_path, tmp_path / "annotations", out)

    cogids = _cogids_by_speaker(out)
    assert cogids["Khan02"] != "0", cogids
    assert cogids["Khan02"] == cogids["Fail01"] == cogids["Saha01"], cogids
