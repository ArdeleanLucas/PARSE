"""Regression tests for the PARSE -> BEAST2 export path.

Covers the stable concept-id keying fix (so id-keyed cognate sets attach to
exported forms) and the export-readiness diagnostics that flag wordlists /
NEXUS matrices which are not phylogenetically informative.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import compare.cognate_compute as cognate_compute
import ai.chat_tools  # noqa: F401  # import first: export_tools <-> chat_tools have a load-order cycle
from ai.tools.export_tools import lingpy_tsv_readiness, nexus_readiness


def _seed_annotation(root: pathlib.Path, speaker: str, concept_intervals, ipa_intervals) -> None:
    annotations = root / "annotations"
    annotations.mkdir(exist_ok=True)
    payload = {
        "speaker": speaker,
        "tiers": {
            "concept": {"intervals": concept_intervals},
            "ipa": {"intervals": ipa_intervals},
            "ortho": {"intervals": []},
        },
    }
    (annotations / f"{speaker}.parse.json").write_text(json.dumps(payload), encoding="utf-8")


def _read_tsv(path: pathlib.Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    return header, [dict(zip(header, line.split("\t"))) for line in lines[1:] if line]


def test_export_keys_forms_by_stable_concept_id(tmp_path: pathlib.Path) -> None:
    # Two speakers annotate concept 53 ("big") with the stable id carried on
    # the interval, distinct from the human label text.
    _seed_annotation(
        tmp_path,
        "Spk1",
        [{"text": "big", "concept_id": "53", "start": 0.0, "end": 1.0}],
        [{"text": "gewra", "start": 0.0, "end": 1.0}],
    )
    _seed_annotation(
        tmp_path,
        "Spk2",
        [{"text": "big", "concept_id": "53", "start": 0.0, "end": 1.0}],
        [{"text": "kalan", "start": 0.0, "end": 1.0}],
    )

    forms, _speakers = cognate_compute.load_annotations(tmp_path / "annotations")
    # Forms must be keyed by the stable id, not the label text.
    assert set(forms.keys()) == {"53"}
    assert all(record.concept_label == "big" for record in forms["53"])

    enrichments = tmp_path / "parse-enrichments.json"
    enrichments.write_text(
        json.dumps({"manual_overrides": {"cognate_sets": {"53": {"A": ["Spk1"], "B": ["Spk2"]}}}}),
        encoding="utf-8",
    )

    out = tmp_path / "wordlist.tsv"
    count = cognate_compute.export_wordlist_tsv(enrichments, tmp_path / "annotations", out)
    assert count == 2

    header, rows = _read_tsv(out)
    assert "COGID" in header
    by_speaker = {row["DOCULECT"]: row for row in rows}
    # Id-keyed cognate set now attaches: distinct, non-zero COGIDs.
    assert by_speaker["Spk1"]["COGID"] != "0"
    assert by_speaker["Spk2"]["COGID"] != "0"
    assert by_speaker["Spk1"]["COGID"] != by_speaker["Spk2"]["COGID"]
    # Human label is preserved in the CONCEPT column.
    assert by_speaker["Spk1"]["CONCEPT"] == "big"


def test_legacy_interval_without_concept_id_falls_back_to_text(tmp_path: pathlib.Path) -> None:
    _seed_annotation(
        tmp_path,
        "Spk1",
        [{"text": "water", "start": 0.0, "end": 1.0}],
        [{"text": "aw", "start": 0.0, "end": 1.0}],
    )
    forms, _speakers = cognate_compute.load_annotations(tmp_path / "annotations")
    assert set(forms.keys()) == {"water"}


def test_lingpy_tsv_readiness_flags_all_zero_cogid() -> None:
    tsv = "ID\tCONCEPT\tDOCULECT\tIPA\tCOGID\tTOKENS\tBORROWING\n" \
          "1\tbig\tSpk1\tgewra\t0\tg e\t0\n" \
          "2\tbig\tSpk2\tkalan\t0\tk a\t0\n"
    warnings = lingpy_tsv_readiness(tsv)
    assert any("COGID" in w for w in warnings)


def test_lingpy_tsv_readiness_clean_when_cogids_assigned() -> None:
    tsv = "ID\tCONCEPT\tDOCULECT\tIPA\tCOGID\tTOKENS\tBORROWING\n" \
          "1\tbig\tSpk1\tgewra\t1\tg e\t0\n" \
          "2\tbig\tSpk2\tkalan\t2\tk a\t0\n"
    assert lingpy_tsv_readiness(tsv) == []


def test_lingpy_tsv_readiness_flags_empty_wordlist() -> None:
    tsv = "ID\tCONCEPT\tDOCULECT\tIPA\tCOGID\tTOKENS\tBORROWING\n"
    warnings = lingpy_tsv_readiness(tsv)
    assert any("no data rows" in w for w in warnings)


def test_nexus_readiness_flags_fully_missing_and_high_missingness() -> None:
    nexus = (
        "#NEXUS\n\nBEGIN CHARACTERS;\n"
        "    DIMENSIONS NCHAR=2;\n"
        "    MATRIX\n"
        "        Spk1    ??\n"
        "        Spk2    ??\n"
        "        Spk3    01\n"
        "    ;\nEND;\n"
    )
    warnings = nexus_readiness(nexus)
    assert any("no character data" in w for w in warnings)
    assert any("missingness" in w.lower() for w in warnings)


def test_nexus_readiness_flags_no_characters() -> None:
    nexus = "#NEXUS\n\nBEGIN CHARACTERS;\n    DIMENSIONS NCHAR=0;\nEND;\n"
    warnings = nexus_readiness(nexus)
    assert any("NCHAR=0" in w for w in warnings)


def test_nexus_readiness_clean_when_populated() -> None:
    nexus = (
        "#NEXUS\n\nBEGIN CHARACTERS;\n"
        "    DIMENSIONS NCHAR=2;\n"
        "    MATRIX\n"
        "        Spk1    10\n"
        "        Spk2    01\n"
        "    ;\nEND;\n"
    )
    assert nexus_readiness(nexus) == []
