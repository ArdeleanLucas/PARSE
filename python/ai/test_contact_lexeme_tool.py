"""Tests for the contact_lexeme_lookup chat tool."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure the compare package is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.chat_orchestrator import ChatOrchestrator, READ_ONLY_NOTICE as ORCHESTRATOR_READ_ONLY_NOTICE
from ai.chat_tools import ParseChatTools


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
    result = tools.execute("contact_lexeme_lookup", {"dryRun": False})
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is False
    assert "No languages" in inner["error"]


@patch("compare.contact_lexeme_fetcher.fetch_and_merge")
def test_fetches_with_explicit_languages(mock_fetch, tools, project_dir):
    """Should call fetch_and_merge with provided language codes."""
    mock_fetch.return_value = {"ar": 3, "fa": 2}

    result = tools.execute("contact_lexeme_lookup", {
        "dryRun": False,
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
        "dryRun": False,
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
def test_concept_ids_resolve_project_ids_to_labels(mock_fetch, tools):
    """Project concept IDs should resolve to concept_en labels before fetch."""
    observed = {}

    def fake_fetch_and_merge(**kwargs):
        observed["csv"] = Path(kwargs["concepts_path"]).read_text(encoding="utf-8")
        return {"ar": 1}

    mock_fetch.side_effect = fake_fetch_and_merge

    result = tools.execute("contact_lexeme_lookup", {
        "dryRun": False,
        "languages": ["ar"],
        "conceptIds": ["1"],
    })
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert "1,water" in observed["csv"]


@patch("compare.contact_lexeme_fetcher.fetch_and_merge")
def test_contact_lexeme_lookup_write_result_is_not_forced_read_only(mock_fetch, tools):
    """Successful contact lexeme writes must not be re-labeled as read-only."""
    mock_fetch.return_value = {"ar": 2}

    result = tools.execute("contact_lexeme_lookup", {
        "dryRun": False,
        "languages": ["ar"],
    })
    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert inner["readOnly"] is False
    assert inner["previewOnly"] is False
    assert inner["mode"] == "write-allowed"
    assert "readOnlyNotice" not in inner


@patch("compare.contact_lexeme_fetcher.fetch_and_merge")
def test_fetches_with_provider_override(mock_fetch, tools, project_dir):
    """Should pass provider list when specified."""
    mock_fetch.return_value = {"ar": 2}

    result = tools.execute("contact_lexeme_lookup", {
        "dryRun": False,
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
        "dryRun": False,
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
        "dryRun": False,
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
    result = tools.execute("contact_lexeme_lookup", {"dryRun": False, "languages": ["ar"]})
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
        result = tools.execute("contact_lexeme_lookup", {"dryRun": False})
        assert result["ok"] is True
        inner = result["result"]
        assert inner["ok"] is True
        assert set(inner["languages"]) == {"ar", "fa"}


def test_system_prompt_requires_readable_markdown_responses(project_dir, tools):
    """Chat prompt should tell the model to emit readable markdown, not one-line punctuation soup."""
    ai_config = project_dir / "config" / "ai_config.json"
    ai_config.write_text(json.dumps({}), encoding="utf-8")

    orchestrator = ChatOrchestrator(project_root=project_dir, tools=tools, config_path=ai_config)

    assert "Use readable Markdown" in orchestrator._system_prompt
    assert "blank lines between sections" in orchestrator._system_prompt
    assert "Never wrap the entire reply in a code fence" in orchestrator._system_prompt


def test_read_only_guard_allows_contact_lexeme_lookup_write_messages(project_dir):
    """Allowed mutating tools should not trigger the read-only refusal after success."""
    ai_config = project_dir / "config" / "ai_config.json"
    ai_config.write_text(json.dumps({
        "chat": {"provider": "openai", "model": "gpt-5.4", "read_only": True}
    }), encoding="utf-8")

    orchestrator = ChatOrchestrator(
        project_root=project_dir,
        tools=ParseChatTools(project_root=project_dir),
        config_path=ai_config,
    )

    text = orchestrator._apply_read_only_guard(
        "Fetched Arabic reference forms and wrote them to sil_contact_languages.json.",
        "Import Arabic reference forms for comparison.",
        used_tool_names={"contact_lexeme_lookup"},
    )

    assert not text.startswith(ORCHESTRATOR_READ_ONLY_NOTICE)
    assert "wrote them to sil_contact_languages.json" in text


def test_write_applied_tool_names_only_include_successful_persisted_tools(project_dir):
    """Only successful write-capable tool calls should bypass the read-only guard."""
    ai_config = project_dir / "config" / "ai_config.json"
    ai_config.write_text(json.dumps({
        "chat": {"provider": "openai", "model": "gpt-5.4", "read_only": True}
    }), encoding="utf-8")

    orchestrator = ChatOrchestrator(
        project_root=project_dir,
        tools=ParseChatTools(project_root=project_dir),
        config_path=ai_config,
    )

    write_tools = orchestrator._write_applied_tool_names([
        {"tool": "contact_lexeme_lookup", "ok": False, "readOnly": False},
        {"tool": "contact_lexeme_lookup", "ok": True, "readOnly": True},
        {"tool": "contact_lexeme_lookup", "ok": True, "readOnly": False},
        {"tool": "annotation_read", "ok": True, "readOnly": True},
    ])

    assert write_tools == ["contact_lexeme_lookup"]
