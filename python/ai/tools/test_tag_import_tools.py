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


def _write_variant_concepts_csv(project_root: pathlib.Path) -> None:
    with open(project_root / "concepts.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerow({"id": "cold-a", "concept_en": "cold (A)"})
        writer.writerow({"id": "cold-b", "concept_en": "cold (B)"})
        writer.writerow({"id": "cold-c", "concept_en": "cold (C)"})
        writer.writerow({"id": "dog", "concept_en": "dog"})


def _write_input_csv(project_root: pathlib.Path) -> pathlib.Path:
    path = project_root / "tag-input.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["concept_en"])
        writer.writeheader()
        writer.writerow({"concept_en": "ash"})
        writer.writerow({"concept_en": "bark"})
    return path


def _write_variant_input_csv(project_root: pathlib.Path, labels: list[str]) -> pathlib.Path:
    path = project_root / "tag-input.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["concept_en"])
        writer.writeheader()
        for label in labels:
            writer.writerow({"concept_en": label})
    return path


def _annotation_record(speaker: str, concept_ids: list[str], existing_tags: dict[str, list[str]] | None = None) -> dict:
    return {
        "version": 1,
        "project_id": "test-project",
        "speaker": speaker,
        "source_audio": f"audio/raw/{speaker}.wav",
        "source_audio_duration_sec": 10.0,
        "tiers": {
            "concept": {
                "label": "Concept",
                "display_order": 3,
                "intervals": [
                    {"start": float(index), "end": float(index) + 0.5, "text": concept_id, "concept_id": concept_id}
                    for index, concept_id in enumerate(concept_ids, start=1)
                ],
            },
            "ortho": {"label": "Orthography", "display_order": 2, "intervals": []},
            "ipa": {"label": "IPA", "display_order": 1, "intervals": []},
            "speaker": {"label": "Speaker", "display_order": 0, "intervals": []},
        },
        "concept_tags": existing_tags or {},
        "metadata": {"created": "2026-05-08T00:00:00Z", "modified": "2026-05-08T00:00:00Z"},
    }


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_tool_prepare_tag_import_writes_parse_tags_json_directly(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_prepare_tag_import(
        tools,
        {
            "tagName": "Basic Concepts",
            "color": "#123456",
            "conceptIds": ["2", "1"],
            "dryRun": False,
            "propagateToSpeakers": False,
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
            "propagateToSpeakers": False,
        },
    )

    assert payload["ok"] is True
    assert payload["tagId"] == "imported-set"
    assert payload["assignedCount"] == 2


def test_import_csv_matches_all_variants(tmp_path) -> None:
    _write_variant_concepts_csv(tmp_path)
    input_csv = _write_variant_input_csv(tmp_path, ["cold", "dog"])
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_import_tag_csv(tools, {"csvPath": str(input_csv), "dryRun": True})

    assert payload["ok"] is True
    assert payload["matchedCount"] == 2
    assert [entry["csvLabel"] for entry in payload["matched"]] == ["cold", "dog"]
    assert payload["matched"][0]["conceptId"] == "cold-a"
    assert payload["matched"][0]["conceptIds"] == ["cold-a", "cold-b", "cold-c"]
    assert payload["matched"][1]["conceptIds"] == ["dog"]
    matched_union = [concept_id for entry in payload["matched"] for concept_id in entry["conceptIds"]]
    assert matched_union == ["cold-a", "cold-b", "cold-c", "dog"]


def test_matchAllVariants_false_keeps_legacy_first_hit(tmp_path) -> None:
    _write_variant_concepts_csv(tmp_path)
    input_csv = _write_variant_input_csv(tmp_path, ["cold", "dog"])
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_import_tag_csv(
        tools,
        {"csvPath": str(input_csv), "dryRun": True, "matchAllVariants": False},
    )

    assert payload["ok"] is True
    matched_union = [concept_id for entry in payload["matched"] for concept_id in entry["conceptIds"]]
    assert len([concept_id for concept_id in matched_union if concept_id.startswith("cold-")]) == 1
    assert matched_union == ["cold-a", "dog"]


def test_fuzzy_only_runs_when_base_match_empty(tmp_path) -> None:
    _write_variant_concepts_csv(tmp_path)
    input_csv = _write_variant_input_csv(tmp_path, ["dgo"])
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_import_tag_csv(tools, {"csvPath": str(input_csv), "dryRun": True})

    assert payload["ok"] is True
    assert payload["matched"] == [
        {"csvLabel": "dgo", "conceptId": "dog", "conceptIds": ["dog"], "conceptLabel": "dog"}
    ]


def test_propagates_to_speaker_concept_tags(tmp_path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    speaker_1 = annotations_dir / "Speaker01.json"
    speaker_2 = annotations_dir / "Speaker02.json"
    untouched = annotations_dir / "Speaker03.json"
    parse_json = annotations_dir / "SpeakerParse.parse.json"
    speaker_1.write_text(json.dumps(_annotation_record("Speaker01", ["cold-a", "cold-b"])), encoding="utf-8")
    speaker_2.write_text(json.dumps(_annotation_record("Speaker02", ["cold-a"])), encoding="utf-8")
    untouched.write_text(json.dumps(_annotation_record("Speaker03", ["dog"])), encoding="utf-8")
    parse_json.write_text(json.dumps(_annotation_record("SpeakerParse", ["cold-a"])), encoding="utf-8")
    untouched_before = untouched.stat().st_mtime_ns
    parse_json_before = parse_json.stat().st_mtime_ns
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_prepare_tag_import(
        tools,
        {
            "tagName": "Thesis",
            "color": "#123456",
            "conceptIds": ["cold-a", "cold-b"],
            "dryRun": False,
        },
    )

    assert payload["ok"] is True
    assert payload["assignedCount"] == 2
    assert payload["propagatedSpeakerCount"] == 2
    assert payload["propagatedConceptAssignments"] == 3
    assert _read_json(speaker_1)["concept_tags"] == {"cold-a": ["thesis"], "cold-b": ["thesis"]}
    assert _read_json(speaker_2)["concept_tags"] == {"cold-a": ["thesis"]}
    assert _read_json(untouched)["concept_tags"] == {}
    assert untouched.stat().st_mtime_ns == untouched_before
    assert parse_json.stat().st_mtime_ns == parse_json_before
    assert len(list(annotations_dir.glob("Speaker01.json.bak-*-pre-tag-import"))) == 1
    assert len(list(annotations_dir.glob("Speaker02.json.bak-*-pre-tag-import"))) == 1
    assert not list(annotations_dir.glob("Speaker03.json.bak-*-pre-tag-import"))

    second = tool_prepare_tag_import(
        tools,
        {
            "tagName": "Thesis",
            "color": "#123456",
            "conceptIds": ["cold-a", "cold-b"],
            "dryRun": False,
        },
    )

    assert second["ok"] is True
    assert second["propagatedSpeakerCount"] == 0
    assert second["propagatedConceptAssignments"] == 0
    assert _read_json(speaker_1)["concept_tags"] == {"cold-a": ["thesis"], "cold-b": ["thesis"]}
    assert _read_json(speaker_2)["concept_tags"] == {"cold-a": ["thesis"]}
    assert len(list(annotations_dir.glob("Speaker01.json.bak-*-pre-tag-import"))) == 1
    assert len(list(annotations_dir.glob("Speaker02.json.bak-*-pre-tag-import"))) == 1


def test_propagateToSpeakers_false_skips_per_speaker_writes(tmp_path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    speaker = annotations_dir / "Speaker01.json"
    speaker.write_text(json.dumps(_annotation_record("Speaker01", ["cold-a"])), encoding="utf-8")
    before = speaker.read_text(encoding="utf-8")
    before_mtime = speaker.stat().st_mtime_ns
    tools = ParseChatTools(project_root=tmp_path)

    payload = tool_prepare_tag_import(
        tools,
        {
            "tagName": "Thesis",
            "color": "#123456",
            "conceptIds": ["cold-a"],
            "dryRun": False,
            "propagateToSpeakers": False,
        },
    )

    assert payload["ok"] is True
    assert payload["assignedCount"] == 1
    assert payload["propagatedSpeakerCount"] == 0
    assert payload["propagatedConceptAssignments"] == 0
    tags = json.loads((tmp_path / "parse-tags.json").read_text(encoding="utf-8"))
    assert tags[0]["concepts"] == ["cold-a"]
    assert speaker.read_text(encoding="utf-8") == before
    assert speaker.stat().st_mtime_ns == before_mtime
    assert not list(annotations_dir.glob("*.bak-*-pre-tag-import"))
