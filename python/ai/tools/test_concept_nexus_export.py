"""export_concept_nexus: appendix-style NEXUS (tagId / conceptIds / speakers)."""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools  # noqa: E402


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
            "53": groups, "150": dict(groups),           # byte-identical duplicate of big
            "54": {"A": ["Spk1"], "B": ["Spk2", "Spk3"]},
            "999": {"A": ["Spk1", "Spk2", "Spk3"]},       # water — outside the tag
        }}}),
        encoding="utf-8",
    )
    (root / "project.json").write_text(
        json.dumps({"speakers": {"Spk1": {}, "Spk2": {}, "Spk3": {}}}), encoding="utf-8"
    )
    (root / "annotations").mkdir(exist_ok=True)


def _nchar(nexus: str) -> int:
    return int(re.search(r"NCHAR=(\d+)", nexus).group(1))


def _taxa(nexus: str) -> list[str]:
    block = re.search(r"TAXLABELS(.*?);", nexus, re.S)
    return re.findall(r"\b(Spk\d+)\b", block.group(1)) if block else []


def _matrix_row(nexus: str, speaker: str) -> str:
    block = re.search(r"MATRIX(.*?);", nexus, re.S)
    assert block, nexus
    row = re.search(rf"^\s*{re.escape(speaker)}\s+([01?]+)\s*$", block.group(1), re.M)
    assert row, f"no matrix row for {speaker} in:\n{nexus}"
    return row.group(1)


def test_concept_nexus_resolves_uid_keyed_membership_over_stale_legacy(tmp_path: pathlib.Path) -> None:
    """MC-468-C: a concept keyed both legacy (``53``, stale) and uid (``c-53``,
    current — the value compare-mode writes) must export the uid membership, like
    export_concept_appendix_md. A speaker grouped only under the uid key must code
    ``1``, not ``?`` from the stale legacy block (the export_concept_appendix /
    PR #666 fix that this tool's separate _consolidated_sets path never received)."""
    (tmp_path / "concepts.csv").write_text(
        "id,concept_en,source_survey,source_item\n53,big,KLQ,4.1\n",
        encoding="utf-8",
    )
    (tmp_path / "parse-tags.json").write_text(
        json.dumps([{"id": "custom-sk-concept-list", "label": "thesis", "concepts": ["53"]}]),
        encoding="utf-8",
    )
    (tmp_path / "parse-enrichments.json").write_text(
        json.dumps({"manual_overrides": {"cognate_sets": {
            "53": {"A": ["Spk1", "Spk2"]},               # legacy — stale (Spk3 ungrouped)
            "c-53": {"A": ["Spk1", "Spk2", "Spk3"]},     # uid — current compare-mode decision
        }}}),
        encoding="utf-8",
    )
    (tmp_path / "project.json").write_text(
        json.dumps({"speakers": {"Spk1": {}, "Spk2": {}, "Spk3": {}}}), encoding="utf-8"
    )
    (tmp_path / "annotations").mkdir(exist_ok=True)

    res = ParseChatTools(project_root=tmp_path)._tool_export_concept_nexus(
        {"tagId": "custom-sk-concept-list", "dryRun": True}
    )
    nexus = res["nexus"]

    # One character (single group A); Spk3 is grouped (1), not dropped to ? by the stale legacy key.
    assert _nchar(nexus) == 1, nexus
    assert _matrix_row(nexus, "Spk1") == "1"
    assert _matrix_row(nexus, "Spk2") == "1"
    assert _matrix_row(nexus, "Spk3") == "1", "Spk3 grouped under uid key c-53 must export 1, not ?"


def test_concept_nexus_tag_filters_and_returns_full_text(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    res = tools._tool_export_concept_nexus({"tagId": "custom-sk-concept-list", "dryRun": True})

    assert res["consolidated"] is True
    assert res["tagId"] == "custom-sk-concept-list"
    assert res["consolidation"]["collapsed_groups"] == 1  # big (53 == 150) folds
    # Full NEXUS is returned (no 2000-char truncation): the matrix block is present.
    assert "MATRIX" in res["nexus"]
    assert "preview" not in res  # the appendix-style tool returns the whole document
    # big(2) + small(2) = 4 chars; water excluded by the tag filter.
    assert _nchar(res["nexus"]) == 4
    assert sorted(_taxa(res["nexus"])) == ["Spk1", "Spk2", "Spk3"]


def test_concept_nexus_explicit_concept_ids_override_tag(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    # Only big (both survey ids) — small is dropped even though it is in the tag.
    res = tools._tool_export_concept_nexus({"conceptIds": ["53", "150"], "dryRun": True})

    assert res["consolidated"] is True
    assert _nchar(res["nexus"]) == 2  # big folds to one 2-group block


def test_concept_nexus_speaker_subset_drops_all_absent_columns(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    res = tools._tool_export_concept_nexus(
        {"tagId": "custom-sk-concept-list", "speakers": ["Spk1", "Spk2"], "dryRun": True}
    )

    taxa = _taxa(res["nexus"])
    assert taxa == ["Spk1", "Spk2"]      # Spk3 dropped
    assert "Spk3" not in res["nexus"]
    # big: B={Spk3} becomes all-absent -> dropped (1 char left); small: A={Spk1}, B={Spk2} (2 chars).
    assert _nchar(res["nexus"]) == 3


def test_concept_nexus_writes_file(tmp_path: pathlib.Path) -> None:
    _seed_workspace(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    res = tools._tool_export_concept_nexus(
        {"tagId": "custom-sk-concept-list", "outputPath": "exports/concept.nex"}
    )

    assert res["success"] is True
    written = (tmp_path / "exports" / "concept.nex").read_text(encoding="utf-8")
    assert "#NEXUS" in written and _nchar(written) == 4
