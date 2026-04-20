"""Tests for the contact_lexeme_lookup chat tool."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure the compare package is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools, ChatToolValidationError


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal PARSE project structure."""
    # concepts.csv
    concepts_csv = tmp_path / "concepts.csv"
    concepts_csv.write_text(
        "id,concept_en\n"
        "1,water\n"
        "2,fire\n"
        "3,hand\n",
        encoding="utf-8",
    )

    # config directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    ai_config = config_dir / "ai_config.json"
    ai_config.write_text("{}", encoding="utf-8")
    sil_config = config_dir / "sil_contact_languages.json"
    sil_config.write_text("{}", encoding="utf-8")

    # annotations directory
    (tmp_path / "annotations").mkdir()
    (tmp_path / "audio").mkdir()

    return tmp_path


@pytest.fixture
def tools(project_dir):
    return ParseChatTools(project_root=project_dir)


def test_tool_is_in_allowlist(tools):
    """contact_lexeme_lookup must appear in tool names."""
    assert "contact_lexeme_lookup" in tools.tool_names()


def test_tool_has_openai_schema(tools):
    """Tool schema must be generated for OpenAI function calling."""
    schemas = tools.openai_tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "contact_lexeme_lookup" in names


def test_no_languages_and_no_config_returns_error(tools):
    """When no languages given and config is empty, should return helpful error."""
    result = tools.execute("contact_lexeme_lookup", {})
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is False
    assert "No languages" in inner["error"]


@patch("compare.contact_lexeme_fetcher.fetch_and_merge")
def test_fetches_with_explicit_languages(mock_fetch, tools, project_dir):
    """Should call fetch_and_merge with provided language codes."""
    mock_fetch.return_value = {"ar": 3, "fa": 2}

    result = tools.execute("contact_lexeme_lookup", {
        "languages": ["ar", "fa"],
    })
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert inner["languages"] == ["ar", "fa"]
    assert inner["totalConceptsFetched"] == 5

    # Verify fetch_and_merge was called correctly
    mock_fetch.assert_called_once()
    call_kwargs = mock_fetch.call_args
    assert call_kwargs[1]["language_codes"] == ["ar", "fa"]
    assert call_kwargs[1]["overwrite"] is False


@patch("compare.contact_lexeme_fetcher.fetch_and_merge")
def test_fetches_with_concept_filter(mock_fetch, tools, project_dir):
    """Should create temp CSV when conceptIds are provided."""
    mock_fetch.return_value = {"ar": 1}

    result = tools.execute("contact_lexeme_lookup", {
        "languages": ["ar"],
        "conceptIds": ["water"],
    })
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True

    # The concepts_path passed should NOT be the project's concepts.csv
    # (it should be a temp file), but it gets cleaned up
    mock_fetch.assert_called_once()


@patch("compare.contact_lexeme_fetcher.fetch_and_merge")
def test_fetches_with_provider_override(mock_fetch, tools, project_dir):
    """Should pass provider list when specified."""
    mock_fetch.return_value = {"ar": 2}

    result = tools.execute("contact_lexeme_lookup", {
        "languages": ["ar"],
        "providers": ["grokipedia"],
    })
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True

    call_kwargs = mock_fetch.call_args
    assert call_kwargs[1]["providers"] == ["grokipedia"]


@patch("compare.contact_lexeme_fetcher.fetch_and_merge")
def test_fetches_with_overwrite(mock_fetch, tools, project_dir):
    """Should pass overwrite flag."""
    mock_fetch.return_value = {"ar": 5}

    result = tools.execute("contact_lexeme_lookup", {
        "languages": ["ar"],
        "overwrite": True,
    })
    assert result["ok"] is True
    inner = result["result"]
    assert inner["overwrite"] is True

    call_kwargs = mock_fetch.call_args
    assert call_kwargs[1]["overwrite"] is True


@patch("compare.contact_lexeme_fetcher.fetch_and_merge")
def test_handles_fetch_exception(mock_fetch, tools, project_dir):
    """Should gracefully handle provider failures."""
    mock_fetch.side_effect = RuntimeError("Network timeout")

    result = tools.execute("contact_lexeme_lookup", {
        "languages": ["ar"],
    })
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is False
    assert "Network timeout" in inner["error"]


def test_no_concepts_csv_returns_error(tmp_path):
    """Should error when concepts.csv doesn't exist."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "ai_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "annotations").mkdir()
    (tmp_path / "audio").mkdir()

    tools = ParseChatTools(project_root=tmp_path)
    result = tools.execute("contact_lexeme_lookup", {"languages": ["ar"]})
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is False
    assert "concepts.csv" in inner["error"]


def test_reads_languages_from_config(project_dir):
    """When no languages arg, should read from sil_contact_languages.json."""
    sil_config = project_dir / "config" / "sil_contact_languages.json"
    sil_config.write_text(json.dumps({
        "ar": {"name": "Arabic", "concepts": {}},
        "fa": {"name": "Persian", "concepts": {}},
    }), encoding="utf-8")

    tools = ParseChatTools(project_root=project_dir)

    with patch("compare.contact_lexeme_fetcher.fetch_and_merge") as mock_fetch:
        mock_fetch.return_value = {"ar": 1, "fa": 1}
        result = tools.execute("contact_lexeme_lookup", {})
        assert result["ok"] is True
        inner = result["result"]
        assert inner["ok"] is True
        assert set(inner["languages"]) == {"ar", "fa"}
