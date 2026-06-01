"""Tests for the consolidated (canonical-collapsed, tag-filtered) cognate matrix."""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compare.consolidated_matrix import (
    build_consolidated_cognate_sets,
    build_nexus_from_sets,
    build_wordlist_rows,
    tag_concept_ids,
    wordlist_rows_to_tsv,
)

CONCEPTS = [
    {"id": "53", "concept_en": "big", "source_survey": "KLQ", "source_item": "4.1"},
    {"id": "150", "concept_en": "big", "source_survey": "JBIL", "source_item": "169"},
    {"id": "54", "concept_en": "small", "source_survey": "KLQ", "source_item": "4.2"},
]


def _byte_identical_enrichments():
    groups = {"A": ["Spk1", "Spk2"], "B": ["Spk3"]}
    return {"manual_overrides": {"cognate_sets": {"53": groups, "150": dict(groups), "54": {"A": ["Spk1"], "B": ["Spk2", "Spk3"]}}}}


def test_safe_union_collapses_byte_identical_duplicate_to_one_character_block():
    cons, meta, id_to_key = build_consolidated_cognate_sets(CONCEPTS, _byte_identical_enrichments())
    assert sorted(cons.keys()) == ["big", "small"]
    # big folds 53+150 -> one block of 2 characters (not 4)
    assert len(cons["big"]) == 2
    assert meta["character_count"] == 4
    assert meta["collapsed"] == [{"gloss": "big", "ids": ["53", "150"], "kept": "53"}]
    assert id_to_key == {"53": "big", "150": "big", "54": "small"}
    assert meta["needs_recluster"] == []


def test_needs_recluster_kept_separate_with_warning():
    enr = {"manual_overrides": {"cognate_sets": {
        "53": {"A": ["Spk1", "Spk2"], "B": ["Spk3"]},
        "150": {"A": ["Spk1"], "B": ["Spk2", "Spk3"]},
    }}}
    cons, meta, _ = build_consolidated_cognate_sets(CONCEPTS, enr)
    # divergent letters are NOT merged
    assert sorted(cons.keys()) == ["big#150", "big#53"]
    assert meta["needs_recluster"] and meta["warnings"]


def test_tag_filter_restricts_to_tagged_ids():
    tags = [{"id": "custom-sk-concept-list", "concepts": ["53", "150"]}]
    ids = tag_concept_ids(tags, "custom-sk-concept-list")
    assert ids == {"53", "150"}
    cons, meta, _ = build_consolidated_cognate_sets(CONCEPTS, _byte_identical_enrichments(), allowed_ids=ids)
    assert sorted(cons.keys()) == ["big"]
    assert meta["character_count"] == 2


def test_tag_concept_ids_accepts_wrapper_and_mapping_shapes():
    assert tag_concept_ids({"tags": [{"id": "t", "concepts": {"7": True, "9": True}}]}, "t") == {"7", "9"}
    assert tag_concept_ids([{"id": "t", "concepts": ["1", "2"]}], "t") == {"1", "2"}
    assert tag_concept_ids([{"id": "other", "concepts": ["1"]}], "t") == set()


def test_nexus_matrix_encodes_membership():
    cons, _meta, _ = build_consolidated_cognate_sets(CONCEPTS, _byte_identical_enrichments())
    nexus = build_nexus_from_sets(cons, ["Spk1", "Spk2", "Spk3"])
    assert int(re.search(r"NTAX=(\d+)", nexus).group(1)) == 3
    assert int(re.search(r"NCHAR=(\d+)", nexus).group(1)) == 4
    # Spk1 is in big_A and small_A -> "1" there, "0" for the other (has form, other group)
    row = re.search(r"Spk1\s+([01?]+)", nexus).group(1)
    assert row == "1010"


def test_wordlist_remaps_forms_to_canonical_and_assigns_cogid(tmp_path: pathlib.Path):
    ann = tmp_path / "annotations"
    ann.mkdir()
    def write(speaker, concept_id, ipa):
        (ann / f"{speaker}.parse.json").write_text(json.dumps({
            "speaker": speaker,
            "tiers": {
                "concept": {"intervals": [{"text": "big", "concept_id": concept_id, "start": 0.0, "end": 1.0}]},
                "ipa": {"intervals": [{"text": ipa, "start": 0.0, "end": 1.0}]},
            },
        }), encoding="utf-8")
    # Spk1 tagged big under 53, Spk3 under the duplicate id 150 -> must fold to one concept
    write("Spk1", "53", "gewra")
    write("Spk3", "150", "kalan")
    cons, _meta, id_to_key = build_consolidated_cognate_sets(CONCEPTS, _byte_identical_enrichments())
    rows = build_wordlist_rows(ann, cons, id_to_key)
    tsv = wordlist_rows_to_tsv(rows)
    # both speakers land under the single canonical concept "big"
    concepts_in_tsv = {line.split("\t")[1] for line in tsv.splitlines()[1:]}
    assert concepts_in_tsv == {"big"}
    # Spk1 (group A) and Spk3 (group B) both get a non-zero, distinct COGID
    cog = {line.split("\t")[2]: line.split("\t")[4] for line in tsv.splitlines()[1:]}
    assert cog["Spk1"] != "0" and cog["Spk3"] != "0" and cog["Spk1"] != cog["Spk3"]
