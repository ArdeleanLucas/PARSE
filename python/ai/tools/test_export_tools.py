from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools import export_tools
from external_api.catalog import build_mcp_http_catalog

DEFAULT_TAG_ID = "custom-sk-concept-list"
EXISTING_EXPORT_TOOL_NAMES = (
    "export_annotations_csv",
    "export_lingpy_tsv",
    "export_nexus",
    "export_annotations_elan",
    "export_annotations_textgrid",
)


def _make_review_export_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "project.json").write_text(
        json.dumps(
            {
                "project_id": "review-export-test",
                "speakers": {"TestA": {}},
                "concepts": {"source": "concepts.csv", "id_column": "id"},
            }
        ),
        encoding="utf-8",
    )
    with (workspace / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "53",
                "concept_en": "big (A)",
                "source_item": "53",
                "source_survey": "SurveyA",
                "custom_order": "1",
            }
        )

    annotations = workspace / "annotations"
    annotations.mkdir()
    (annotations / "TestA.parse.json").write_text(
        json.dumps(
            {
                "version": 1,
                "speaker": "TestA",
                "source_audio": "audio/working/TestA/TestA.wav",
                "tiers": {
                    "concept": {
                        "type": "interval",
                        "intervals": [
                            {
                                "concept_id": "53",
                                "start": 1.25,
                                "end": 2.0,
                                "ipa": "bɪg",
                                "ortho": "big",
                            }
                        ],
                    }
                },
                "concept_tags": {"53": [DEFAULT_TAG_ID]},
            }
        ),
        encoding="utf-8",
    )
    return workspace


def test_export_review_data_chat_tool_happy_path_writes_review_data_summary(
    tmp_path: pathlib.Path,
) -> None:
    workspace = _make_review_export_workspace(tmp_path)
    out_dir = tmp_path / "review-out"

    result = ParseChatTools(project_root=tmp_path).execute(
        "export_review_data",
        {"workspace": str(workspace), "out": str(out_dir), "skip_audio": True},
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["ok"] is True
    assert payload["mode"] == "write-allowed"
    assert payload["review_data_path"] == str(out_dir / "review_data.json")
    assert payload["concept_count"] == 1
    assert payload["speaker_count"] == 1
    assert payload["clip_plan_count"] == 1
    assert payload["audio_clipped"] == 0
    assert payload["audio_errors"] == []
    assert payload["skipped_audio"] is True
    assert set(payload["analytical_coverage"]) == {
        "forms_with_cognate_class",
        "forms_with_arabic_similarity",
        "forms_with_persian_similarity",
        "forms_with_borrowing_flag",
        "concepts_with_arabic_ref",
        "concepts_with_persian_ref",
    }
    written = json.loads((out_dir / "review_data.json").read_text(encoding="utf-8"))
    assert written["metadata"]["speakers"] == ["TestA"]
    assert written["concepts"][0]["concept_en"] == "big"


def test_export_review_data_chat_tool_prefers_workspace_contact_cache(
    tmp_path: pathlib.Path,
) -> None:
    workspace = _make_review_export_workspace(tmp_path)
    (workspace / "config").mkdir()
    (workspace / "config" / "sil_contact_languages.json").write_text(
        json.dumps(
            {
                "ar": {"concepts": {"big (A)": [{"script": "كبير"}]}},
                "fa": {"concepts": {"big (A)": [{"script": "بزرگ"}]}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "review-out"

    result = ParseChatTools(project_root=tmp_path).execute(
        "export_review_data",
        {"workspace": str(workspace), "out": str(out_dir), "skip_audio": True},
    )

    assert result["ok"] is True
    written = json.loads((out_dir / "review_data.json").read_text(encoding="utf-8"))
    concept = written["concepts"][0]
    assert concept["arabic"] == {"form": "كبير", "ipa": ""}
    assert concept["persian"] == {"form": "بزرگ", "ipa": ""}


def test_export_review_data_unknown_speaker_returns_invalid_args_envelope(
    tmp_path: pathlib.Path,
) -> None:
    workspace = _make_review_export_workspace(tmp_path)
    out_dir = tmp_path / "review-out"

    result = export_tools.export_review_data(
        ParseChatTools(project_root=tmp_path),
        {
            "workspace": str(workspace),
            "out": str(out_dir),
            "speakers": ["NonexistentSpeaker"],
            "skip_audio": True,
        },
    )

    assert result["ok"] is False
    assert result["error_kind"] == "invalid_args"
    assert "NonexistentSpeaker" in result["error"]
    assert not (out_dir / "review_data.json").exists()


def test_export_review_data_is_registered_for_chat_and_http_mcp_catalog(
    tmp_path: pathlib.Path,
) -> None:
    # The historical export tools remain registered in their original relative
    # order (newer tools such as export_concept_nexus may be interleaved).
    historical_in_order = [n for n in export_tools.EXPORT_TOOL_NAMES if n in EXISTING_EXPORT_TOOL_NAMES]
    assert historical_in_order == list(EXISTING_EXPORT_TOOL_NAMES)
    assert "export_review_data" in export_tools.EXPORT_TOOL_NAMES
    assert "export_review_data" in export_tools.EXPORT_TOOL_SPECS
    assert "export_review_data" in export_tools.EXPORT_TOOL_HANDLERS

    tools = ParseChatTools(project_root=tmp_path)
    assert "export_review_data" in tools.tool_names()
    spec = tools.tool_spec("export_review_data")
    assert spec.mutability == "mutating"
    assert spec.parameters["additionalProperties"] is False
    assert set(spec.parameters["required"]) == {"workspace", "out"}
    assert spec.parameters["properties"]["speakers"]["items"] == {"type": "string"}

    catalog = build_mcp_http_catalog(project_root=tmp_path, mode="all")
    tool_names = {tool["name"] for tool in catalog["tools"]}
    assert "export_review_data" in tool_names


def test_existing_export_tools_remain_registered() -> None:
    for name in EXISTING_EXPORT_TOOL_NAMES:
        assert name in export_tools.EXPORT_TOOL_NAMES
        assert name in export_tools.EXPORT_TOOL_SPECS
        assert name in export_tools.EXPORT_TOOL_HANDLERS
