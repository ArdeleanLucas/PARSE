"""Integration test: consolidate/conceptTag params wired through the export tools."""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools  # noqa: E402  (import first; avoids export_tools load cycle)


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
