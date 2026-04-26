from __future__ import annotations

import csv
import json
import pathlib
import sys
from types import MethodType

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools.tag_import_tools import tool_import_tag_csv, tool_prepare_tag_import


def _write_concepts_csv(project_root: pathlib.Path) -> None:
    with open(project_root / "concepts.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "ash"})
        writer.writerow({"id": "2", "concept_en": "bark"})


def _write_input_csv(project_root: pathlib.Path) -> pathlib.Path:
    path = project_root / "tag-input.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["concept_en"])
        writer.writeheader()
        writer.writerow({"concept_en": "ash"})
        writer.writerow({"concept_en": "bark"})
    return path


def test_tool_prepare_tag_import_writes_parse_tags_json_directly(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_prepare_tag_import(
        tools,
        {
            "tagName": "Basic Concepts",
            "color": "#123456",
            "conceptIds": ["2", "1"],
            "dryRun": False,
        },
    )

    assert payload["ok"] is True
    assert payload["tagId"] == "basic-concepts"
    assert payload["assignedCount"] == 2

    tags = json.loads((tmp_path / "parse-tags.json").read_text(encoding="utf-8"))
    assert tags == [
        {
            "id": "basic-concepts",
            "label": "Basic Concepts",
            "color": "#123456",
            "concepts": ["1", "2"],
        }
    ]


def test_tool_import_tag_csv_uses_shared_prepare_helper_not_wrapper_bounce(tmp_path) -> None:
    _write_concepts_csv(tmp_path)
    input_csv = _write_input_csv(tmp_path)
    tools = ParseChatTools(project_root=tmp_path)

    def _unexpected_wrapper(self, args):
        raise AssertionError("tag import bundle should call shared prepare helper directly")

    tools._tool_prepare_tag_import = MethodType(_unexpected_wrapper, tools)

    payload = tool_import_tag_csv(
        tools,
        {
            "csvPath": str(input_csv),
            "tagName": "Imported Set",
            "color": "#4461d4",
            "dryRun": False,
        },
    )

    assert payload["ok"] is True
    assert payload["tagId"] == "imported-set"
    assert payload["assignedCount"] == 2
