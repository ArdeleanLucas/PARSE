"""Cross-check MCP tool registrations against ParseChatTools.

Prevents phantom-tool regressions — the MCP adapter forwards every call
through ParseChatTools.execute(), so registering an MCP tool that isn't
in the allowlist produces a runtime ChatToolValidationError on the
client side. A test at import time catches that before shipping.
"""
import os
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from ai.chat_tools import ParseChatTools


def test_load_repo_parse_env_sets_missing_vars(tmp_path, monkeypatch) -> None:
    from adapters import mcp_adapter

    (tmp_path / ".parse-env").write_text(
        "# local overrides\nPARSE_EXTERNAL_READ_ROOTS=*\nexport PARSE_CHAT_MEMORY_PATH=memory/custom.md\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PARSE_EXTERNAL_READ_ROOTS", raising=False)
    monkeypatch.delenv("PARSE_CHAT_MEMORY_PATH", raising=False)

    applied = mcp_adapter._load_repo_parse_env(tmp_path)

    assert applied == {
        "PARSE_EXTERNAL_READ_ROOTS": "*",
        "PARSE_CHAT_MEMORY_PATH": "memory/custom.md",
    }
    assert os.environ["PARSE_EXTERNAL_READ_ROOTS"] == "*"
    assert os.environ["PARSE_CHAT_MEMORY_PATH"] == "memory/custom.md"


def test_repo_parse_env_can_disable_mcp_path_sandbox(tmp_path, monkeypatch) -> None:
    import wave

    from adapters import mcp_adapter

    (tmp_path / ".parse-env").write_text("PARSE_EXTERNAL_READ_ROOTS=*\n", encoding="utf-8")
    monkeypatch.delenv("PARSE_EXTERNAL_READ_ROOTS", raising=False)

    project_root = tmp_path / "project"
    project_root.mkdir()

    stray_root = tmp_path / "external"
    stray_root.mkdir()
    wav = stray_root / "speaker.wav"
    with wave.open(str(wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)

    mcp_adapter._load_repo_parse_env(tmp_path)
    tools = ParseChatTools(
        project_root=project_root,
        external_read_roots=mcp_adapter._resolve_external_read_roots(),
    )

    result = tools.execute("read_audio_info", {"sourceWav": str(wav)})["result"]
    assert result["ok"] is True
    assert result["sampleRateHz"] == 16000


def _has_mcp() -> bool:
    try:
        import mcp.server.fastmcp  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_every_mcp_tool_is_allowlisted_in_parse_chat_tools(tmp_path) -> None:
    import asyncio

    from adapters.mcp_adapter import create_mcp_server

    # Minimal project root — the tools only need the path to exist; individual
    # tool calls exercise filesystem paths but this test only lists tools.
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    mcp_names = {t.name for t in mcp_tools}

    chat_names = set(ParseChatTools(project_root=tmp_path).tool_names())

    phantom = mcp_names - chat_names
    adapter_only = {"mcp_get_exposure_mode"}
    assert phantom <= adapter_only, (
        "MCP tools that are NOT in ParseChatTools.tool_names() will raise "
        "ChatToolValidationError at runtime unless they are explicit adapter-only tools. "
        "Unexpected phantom tools: {0}".format(sorted(phantom - adapter_only))
    )


def test_parse_chat_tools_get_all_tool_names_matches_instance(tmp_path) -> None:
    instance_names = ParseChatTools(project_root=tmp_path).tool_names()
    assert ParseChatTools.get_all_tool_names() == instance_names


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_create_mcp_server_defaults_to_30_tools_without_config(tmp_path, monkeypatch) -> None:
    import asyncio
    import json

    from adapters.mcp_adapter import create_mcp_server

    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in mcp_tools}

    assert len(mcp_tools) == 30
    assert "mcp_get_exposure_mode" in tool_names

    _, meta = asyncio.run(server.call_tool("mcp_get_exposure_mode", {}))
    payload = json.loads(meta["result"])
    assert payload["ok"] is True
    assert payload["result"]["exposeAllTools"] is False
    assert payload["result"]["configSource"] is None
    assert payload["result"]["mcpToolCount"] == 30
    assert payload["result"]["parseChatToolCount"] == 47


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_create_mcp_server_exposes_all_48_tools_when_enabled_in_config_dir(tmp_path, monkeypatch) -> None:
    import asyncio
    import json

    from adapters.mcp_adapter import create_mcp_server

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "mcp_config.json").write_text(
        '{"expose_all_tools": true}\n',
        encoding="utf-8",
    )

    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    assert len(mcp_tools) == 48

    _, meta = asyncio.run(server.call_tool("mcp_get_exposure_mode", {}))
    payload = json.loads(meta["result"])
    assert payload["ok"] is True
    assert payload["result"]["exposeAllTools"] is True
    assert payload["result"]["mcpToolCount"] == 48
    assert payload["result"]["parseChatToolCount"] == 47


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_create_mcp_server_exposes_all_48_tools_when_enabled_in_root_config(tmp_path, monkeypatch) -> None:
    import asyncio
    import json

    from adapters.mcp_adapter import create_mcp_server

    (tmp_path / "mcp_config.json").write_text(
        '{"expose_all_tools": true}\n',
        encoding="utf-8",
    )

    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    assert len(mcp_tools) == 48

    _, meta = asyncio.run(server.call_tool("mcp_get_exposure_mode", {}))
    payload = json.loads(meta["result"])
    assert payload["result"]["configSource"] == str(tmp_path / "mcp_config.json")
    assert payload["result"]["exposeAllTools"] is True


def test_load_mcp_config_rejects_non_boolean_expose_all_tools(tmp_path) -> None:
    from adapters import mcp_adapter

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "mcp_config.json").write_text(
        '{"expose_all_tools": "false"}\n',
        encoding="utf-8",
    )

    config = mcp_adapter._load_mcp_config(tmp_path)
    assert config["expose_all_tools"] is False


def test_resolve_onboard_http_timeout_scales_for_large_files(monkeypatch) -> None:
    from adapters import mcp_adapter

    monkeypatch.delenv("PARSE_MCP_ONBOARD_TIMEOUT_SEC", raising=False)

    small = mcp_adapter._resolve_onboard_http_timeout(10 * 1024 * 1024)
    fail02_like = mcp_adapter._resolve_onboard_http_timeout(1519246722)

    assert small == 120.0
    assert fail02_like > 120.0
    assert fail02_like < 1800.0

    monkeypatch.setenv("PARSE_MCP_ONBOARD_TIMEOUT_SEC", "300")
    assert mcp_adapter._resolve_onboard_http_timeout(1519246722) == 300.0


def test_contact_lexeme_lookup_is_allowlisted(tmp_path) -> None:
    """contact_lexeme_lookup specifically — the bug that motivated this test."""
    tools = ParseChatTools(project_root=tmp_path)
    assert "contact_lexeme_lookup" in tools.tool_names()


def test_contact_lexeme_lookup_is_dry_run_gated(tmp_path) -> None:
    """contact_lexeme_lookup writes to sil_contact_languages.json, so it must
    require dryRun — agents should preview first, then persist after user
    confirms. Matches the tag-import tools' proven pattern."""
    tools = ParseChatTools(project_root=tmp_path)
    spec = tools._tool_specs["contact_lexeme_lookup"]
    assert spec.parameters.get("additionalProperties") is False
    assert "dryRun" in spec.parameters.get("required", []), (
        "dryRun must be required to prevent accidental writes"
    )
    assert "dryRun" in spec.parameters.get("properties", {})


def test_no_duplicate_tool_specs_or_handlers() -> None:
    """Dict literals silently keep the last value for duplicate keys — and
    class-attribute method redefinitions silently keep the last def. A past
    regression had two copies of contact_lexeme_lookup disagreeing on schema
    and behavior. Count source-level definitions to keep that from returning."""
    import re
    source = pathlib.Path(__file__).resolve().parent.parent / "ai" / "chat_tools.py"
    text = source.read_text(encoding="utf-8")
    for tool in [
        "annotation_read", "cognate_compute_preview", "contact_lexeme_lookup",
        "cross_speaker_match_preview", "import_processed_speaker", "import_tag_csv", "prepare_tag_import",
        "project_context_read", "read_csv_preview", "spectrogram_preview",
        "stt_start", "stt_status",
    ]:
        spec_count = len(re.findall(r'"{0}":\s*ChatToolSpec'.format(re.escape(tool)), text))
        handler_count = len(re.findall(r"^\s*def _tool_{0}\s*\(".format(re.escape(tool)), text, re.MULTILINE))
        assert spec_count == 1, "{0} has {1} ChatToolSpec entries".format(tool, spec_count)
        assert handler_count == 1, "{0} has {1} handlers".format(tool, handler_count)


def test_first_batch_mutators_publish_machine_readable_safety_metadata(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    expected = {
        "enrichments_write": {
            "dry_run": True,
            "postcondition": "enrichments_file_updated",
        },
        "lexeme_notes_write": {
            "dry_run": True,
            "postcondition": "lexeme_note_written",
        },
        "apply_timestamp_offset": {
            "dry_run": True,
            "postcondition": "annotation_timestamps_shifted",
        },
        "pipeline_run": {
            "dry_run": True,
            "postcondition": "pipeline_job_started",
        },
        "onboard_speaker_import": {
            "dry_run": True,
            "postcondition": "speaker_source_registered",
        },
        "import_processed_speaker": {
            "dry_run": True,
            "postcondition": "processed_speaker_imported",
        },
        "export_annotations_csv": {
            "dry_run": True,
            "postcondition": "export_file_written",
        },
        "export_annotations_elan": {
            "dry_run": True,
            "postcondition": "export_file_written",
        },
        "export_annotations_textgrid": {
            "dry_run": True,
            "postcondition": "export_file_written",
        },
        "export_lingpy_tsv": {
            "dry_run": True,
            "postcondition": "export_file_written",
        },
        "export_nexus": {
            "dry_run": True,
            "postcondition": "export_file_written",
        },
    }

    for tool_name, checks in expected.items():
        spec = tools._tool_specs[tool_name]
        assert spec.mutability == "mutating"
        assert spec.supports_dry_run is checks["dry_run"]
        assert spec.dry_run_parameter == "dryRun"
        assert spec.parameters.get("additionalProperties") is False
        assert "dryRun" in spec.parameters.get("properties", {})
        assert spec.parameters["properties"]["dryRun"]["description"]
        assert any(cond.id == "project_loaded" for cond in spec.preconditions)
        assert any(cond.id == checks["postcondition"] for cond in spec.postconditions)


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_mcp_forwards_annotations_meta_and_strict_schema_for_dangerous_mutator(tmp_path, monkeypatch) -> None:
    import asyncio

    from adapters.mcp_adapter import create_mcp_server

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "mcp_config.json").write_text('{"expose_all_tools": true}\n', encoding="utf-8")

    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    by_name = {tool.name: tool for tool in mcp_tools}

    enrichments_write = by_name["enrichments_write"]
    schema = enrichments_write.inputSchema

    assert schema["additionalProperties"] is False
    assert schema["properties"]["dryRun"]["type"] == "boolean"
    assert schema["properties"]["dryRun"]["description"]
    assert enrichments_write.annotations.destructiveHint is True
    assert enrichments_write.annotations.readOnlyHint is False
    assert enrichments_write.meta["x-parse"]["mutability"] == "mutating"
    assert enrichments_write.meta["x-parse"]["supports_dry_run"] is True
    assert enrichments_write.meta["x-parse"]["dry_run_parameter"] == "dryRun"
    assert any(
        cond["id"] == "project_loaded"
        for cond in enrichments_write.meta["x-parse"]["preconditions"]
    )


def test_can_list_tools_requiring_project_loaded(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    requiring_project = {
        spec.name
        for spec in tools.iter_tool_specs()
        if any(cond.id == "project_loaded" for cond in spec.preconditions)
    }

    assert "enrichments_write" in requiring_project
    assert "pipeline_run" in requiring_project
    assert "project_context_read" not in requiring_project
