"""Integration test: consolidate/conceptTag params wired through the export tools."""
from __future__ import annotations

import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools  # noqa: E402  (import first; avoids export_tools load cycle)
from ai.workflow_tools import WorkflowTools  # noqa: E402


def _seed_workspace(root: pathlib.Path) -> None:
    (root / "concepts.csv").write_text(
        "id,concept_en,source_survey,source_item\n"
        "53,big,KLQ,4.1\n"
        "150,big,JBIL,169\n"
        "54,small,KLQ,4.2\n"
        "999,water,KLQ,3.1\n",
        encoding="utf-8",
    )
    (root / "parse-tags.json").write_text(
        json.dumps([{"id": "custom-sk-concept-list", "label": "thesis", "concepts": ["53", "150", "54"]}]),
        encoding="utf-8",
    )
    groups = {"A": ["Spk1", "Spk2"], "B": ["Spk3"]}
    (root / "parse-enrichments.json").write_text(
        json.dumps({"manual_overrides": {"cognate_sets": {
            "53": groups, "150": dict(groups),          # byte-identical duplicate of big
            "54": {"A": ["Spk1"], "B": ["Spk2", "Spk3"]},
            "999": {"A": ["Spk1", "Spk2", "Spk3"]},      # water — outside the tag
        }}}),
        encoding="utf-8",
    )
    (root / "project.json").write_text(
        json.dumps({"speakers": {"Spk1": {}, "Spk2": {}, "Spk3": {}}}), encoding="utf-8"
    )
    ann = root / "annotations"
    ann.mkdir(exist_ok=True)
    def write(speaker: str, concept_id: str, ipa: str) -> None:
        (ann / f"{speaker}.parse.json").write_text(json.dumps({
            "speaker": speaker,
            "tiers": {
                "concept": {"intervals": [{"text": "big", "concept_id": concept_id, "start": 0.0, "end": 1.0}]},
                "ipa": {"intervals": [{"text": ipa, "start": 0.0, "end": 1.0}]},
            },
        }), encoding="utf-8")
    write("Spk1", "53", "gewra")   # tagged under KLQ id
    write("Spk3", "150", "kalan")  # tagged under the duplicate JBIL id


def _write_annotation(root: pathlib.Path, speaker: str, intervals: list[dict[str, Any]]) -> None:
    ann = root / "annotations"
    ann.mkdir(exist_ok=True)
    concept_intervals = []
    ipa_intervals = []
    for index, item in enumerate(intervals):
        start = float(index)
        end = start + 0.5
        concept_intervals.append(
            {"text": item.get("label", ""), "concept_id": item["concept_id"], "start": start, "end": end}
        )
        ipa_intervals.append({"text": item["ipa"], "start": start, "end": end})
    (ann / f"{speaker}.parse.json").write_text(
        json.dumps({"speaker": speaker, "tiers": {"concept": {"intervals": concept_intervals}, "ipa": {"intervals": ipa_intervals}}}),
        encoding="utf-8",
    )


def _seed_roundtrip_workspace(root: pathlib.Path) -> None:
    (root / "concepts.csv").write_text(
        "id,concept_en,source_survey,source_item\n"
        "101,hand,KLQ,1.1\n"
        "201,hand,JBIL,101\n"
        "102,foot,KLQ,1.2\n"
        "202,foot,JBIL,102\n"
        "103,salt,KLQ,1.3\n"
        "203,salt,JBIL,103\n",
        encoding="utf-8",
    )
    groups = {"A": ["Spk1", "Spk2"], "B": ["Spk3"]}
    (root / "parse-enrichments.json").write_text(
        json.dumps({
            "manual_overrides": {
                "cognate_sets": {
                    "101": groups,
                    "201": dict(groups),
                    "102": {"A": ["Spk1"], "B": ["Spk2", "Spk3"]},
                    "202": {"A": ["Spk1"], "B": ["Spk2", "Spk3"]},
                    # Disagreement safety: this overlapping gloss must stay split.
                    "103": {"A": ["Spk1", "Spk2"], "B": ["Spk3"]},
                    "203": {"A": ["Spk1"], "B": ["Spk2", "Spk3"]},
                },
                # Spk1 has both survey forms for hand; the explicit canonical
                # choice should select row 201 rather than the earlier 101 form.
                "canonical_lexemes": {"bundle:hand": {"Spk1": {"csv_row_id": "201", "source": "manual"}}},
            }
        }),
        encoding="utf-8",
    )
    (root / "project.json").write_text(
        json.dumps({"speakers": {"Spk1": {}, "Spk2": {}, "Spk3": {}}}), encoding="utf-8"
    )
    _write_annotation(
        root,
        "Spk1",
        [
            {"concept_id": "101", "label": "hand", "ipa": "old-hand"},
            {"concept_id": "201", "label": "hand", "ipa": "chosen-hand"},
            {"concept_id": "102", "label": "foot", "ipa": "foot-one"},
            {"concept_id": "103", "label": "salt", "ipa": "salt-one"},
            {"concept_id": "203", "label": "salt", "ipa": "salt-two"},
        ],
    )
    _write_annotation(root, "Spk2", [{"concept_id": "201", "label": "hand", "ipa": "hand-two"}, {"concept_id": "202", "label": "foot", "ipa": "foot-two"}])
    _write_annotation(root, "Spk3", [{"concept_id": "101", "label": "hand", "ipa": "hand-three"}, {"concept_id": "202", "label": "foot", "ipa": "foot-three"}])


def test_export_nexus_consolidates_and_tag_filters(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    plain = tools._tool_export_nexus({"dryRun": True})
    consolidated = tools._tool_export_nexus({"conceptTag": "custom-sk-concept-list", "dryRun": True})

    plain_nchar = int(re.search(r"NCHAR=(\d+)", plain["preview"]).group(1))
    cons_nchar = int(re.search(r"NCHAR=(\d+)", consolidated["preview"]).group(1))

    # Plain export: big counted twice (53_*, 150_*) + small + water.
    # Consolidated + tag-filtered: big folds to one block, water (untagged) dropped.
    assert consolidated["consolidated"] is True
    assert consolidated["conceptTag"] == "custom-sk-concept-list"
    assert consolidated["consolidation"]["collapsed_groups"] == 1
    assert cons_nchar < plain_nchar
    # big(2) + small(2) = 4 characters; water excluded by the tag filter
    assert cons_nchar == 4


def test_export_lingpy_tsv_consolidates_duplicate_ids(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    res = tools._tool_export_lingpy_tsv({"conceptTag": "custom-sk-concept-list", "dryRun": True})
    assert res["consolidated"] is True
    # Spk1 (id 53) and Spk3 (id 150) fold into a single canonical "big" concept.
    concept_col = {line.split("\t")[1] for line in res["previewLines"].splitlines()[1:]}
    assert concept_col == {"big"}


def test_unknown_concept_tag_emits_distinct_warning(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    res = tools._tool_export_nexus({"conceptTag": "does-not-exist", "dryRun": True})
    assert res["consolidated"] is True
    # A typo'd / unknown tag must not look like a silent "no data" export.
    assert any("matched 0 concepts" in w for w in res["warnings"])


def test_export_beast2_xml_wraps_consolidated_matrix(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    res = tools._tool_export_beast2_xml(
        {"conceptTag": "custom-sk-concept-list", "chainLength": 12345, "outputPath": "exports/a.xml"}
    )
    assert res["consolidated"] is True and res["chainLength"] == 12345
    root = ET.fromstring((tmp_path / "exports" / "a.xml").read_text(encoding="utf-8"))
    assert root.get("version") == "2.7"
    assert root.find("run").get("chainLength") == "12345"
    assert root.find("data").get("dataType") == "binary"
    # 3 speakers in the seed workspace -> 3 taxa sequences
    assert len(root.find("data").findall("sequence")) == 3


def test_export_beast2_xml_rejects_bad_chain_length(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)
    with pytest.raises(Exception):
        tools._tool_export_beast2_xml({"consolidate": True, "chainLength": 0, "dryRun": True})


def test_complete_export_consolidate_roundtrip_collapses_n_not_2n(tmp_path: pathlib.Path) -> None:
    _seed_roundtrip_workspace(tmp_path)
    workflow = WorkflowTools(project_root=tmp_path)

    payload = workflow.execute(
        "export_complete_lingpy_dataset",
        {"with_contact_lexemes": False, "consolidate": True, "outputDir": "exports/roundtrip", "dryRun": False},
    )["result"]

    nexus_text = (tmp_path / "exports" / "roundtrip" / "dataset.nex").read_text(encoding="utf-8")
    wordlist_text = (tmp_path / "exports" / "roundtrip" / "wordlist.tsv").read_text(encoding="utf-8")
    nchar = int(re.search(r"NCHAR=(\d+)", nexus_text).group(1))
    concept_values = [line.split("\t")[1] for line in wordlist_text.splitlines()[1:]]
    hand_rows = [line.split("\t") for line in wordlist_text.splitlines()[1:] if line.split("\t")[1] == "hand"]

    assert payload["consolidated"] is True
    assert payload["stages"][0]["payload"]["consolidation"]["collapsed_groups"] == 2
    assert payload["stages"][0]["payload"]["consolidation"]["concept_count"] == 4
    assert payload["stages"][0]["payload"]["consolidation"]["needs_recluster_groups"] == 1
    assert any("kept separate" in warning for warning in payload["warnings"])
    # N=2 safe overlapping meanings (hand + foot) produce N consolidated concept
    # blocks, not 2N per-survey duplicates; disagreeing salt remains split.
    assert "hand#" not in nexus_text
    assert "foot#" not in nexus_text
    assert "salt#103" in nexus_text and "salt#203" in nexus_text
    assert nchar == 8  # hand(2) + foot(2) + safe split salt#103(2) + salt#203(2)
    assert concept_values.count("hand") == 3
    assert len({row[2] for row in hand_rows}) == len(hand_rows)
    assert any(row[3] == "chosen-hand" for row in hand_rows)
    assert all(row[3] != "old-hand" for row in hand_rows)
