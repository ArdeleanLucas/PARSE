"""Tests for the clef_clear_data chat/MCP tool."""

import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.chat_tools import ChatToolValidationError, ParseChatTools


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "annotations").mkdir()
    (tmp_path / "audio").mkdir()
    (tmp_path / "config" / "ai_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "sil_contact_languages.json").write_text(
        json.dumps(
            {
                "_meta": {
                    "primary_contact_languages": ["ar", "fa"],
                    "form_selections": {"water": {"ar": ["maːʔ"], "fa": ["ɒːb"]}},
                },
                "ar": {
                    "name": "Arabic",
                    "concepts": {
                        "water": [{"form": "maːʔ", "sources": ["wiktionary"]}],
                        "fire": ["naːr"],
                    },
                },
                "fa": {
                    "name": "Persian",
                    "concepts": {
                        "water": [{"form": "ɒːb", "sources": ["wikidata"]}],
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def tools(project_dir: Path) -> ParseChatTools:
    return ParseChatTools(project_root=project_dir)



def test_tool_is_in_allowlist(tools: ParseChatTools) -> None:
    assert "clef_clear_data" in tools.tool_names()



def test_tool_has_openai_schema(tools: ParseChatTools) -> None:
    schemas = tools.openai_tool_schemas()
    names = [schema["function"]["name"] for schema in schemas]
    assert "clef_clear_data" in names



def test_dry_run_preview_is_read_only_and_non_mutating(tools: ParseChatTools, project_dir: Path) -> None:
    sil_config_path = project_dir / "config" / "sil_contact_languages.json"
    before = sil_config_path.read_text(encoding="utf-8")

    result = tools.execute("clef_clear_data", {"dryRun": True, "languages": None, "concepts": None})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert inner["dryRun"] is True
    assert inner["readOnly"] is True
    assert inner["previewOnly"] is True
    assert inner["mode"] == "read-only"
    assert sil_config_path.read_text(encoding="utf-8") == before



def test_write_clear_is_write_allowed_and_removes_requested_scope(tools: ParseChatTools, project_dir: Path) -> None:
    result = tools.execute("clef_clear_data", {"dryRun": False, "concepts": ["water"]})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert inner["dryRun"] is False
    assert inner["readOnly"] is False
    assert inner["previewOnly"] is False
    assert inner["mode"] == "write-allowed"
    assert inner["summary"]["formsRemoved"] == 2

    payload = json.loads((project_dir / "config" / "sil_contact_languages.json").read_text(encoding="utf-8"))
    assert payload["ar"]["concepts"] == {"fire": ["naːr"]}
    assert payload["fa"]["concepts"] == {}
    assert payload["_meta"]["form_selections"] == {"water": {"ar": ["maːʔ"], "fa": ["ɒːb"]}}



def test_write_clear_can_remove_provider_caches(tools: ParseChatTools, project_dir: Path) -> None:
    cache_dir = project_dir / "config" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "wiktionary_ar.json").write_text("{}", encoding="utf-8")
    (cache_dir / "wikidata_ar.json").write_text("{}", encoding="utf-8")
    (cache_dir / "asjp_fa.json").write_text("{}", encoding="utf-8")

    result = tools.execute("clef_clear_data", {"dryRun": False, "clearCache": True})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["summary"]["cacheFilesRemoved"] == 3
    assert not (cache_dir / "wiktionary_ar.json").exists()
    assert not (cache_dir / "wikidata_ar.json").exists()
    assert not (cache_dir / "asjp_fa.json").exists()



def test_tool_schema_rejects_invalid_boolean_fields(tools: ParseChatTools) -> None:
    with pytest.raises(ChatToolValidationError) as exc_info:
        tools.execute("clef_clear_data", {"dryRun": "true"})

    assert "$.dryRun expected boolean" in str(exc_info.value)
