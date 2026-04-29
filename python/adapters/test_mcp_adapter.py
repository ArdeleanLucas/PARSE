"""Cross-check MCP tool registrations against ParseChatTools.

Prevents phantom-tool regressions — the MCP adapter forwards every call
through ParseChatTools.execute(), so registering an MCP tool that isn't
in the allowlist produces a runtime ChatToolValidationError on the
client side. A test at import time catches that before shipping.
"""
import json
import os
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from ai.chat_tools import ParseChatTools
from ai.workflow_tools import WorkflowTools


def _seed_minimal_annotation_project(project_root: pathlib.Path) -> None:
    import wave

    (project_root / "config").mkdir(parents=True, exist_ok=True)
    (project_root / "annotations").mkdir(parents=True, exist_ok=True)
    audio_dir = project_root / "audio" / "original" / "Base01"
    audio_dir.mkdir(parents=True, exist_ok=True)

    with wave.open(str(audio_dir / "source.wav"), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 1600)

    (project_root / "project.json").write_text(
        json.dumps({"project_id": "mcp-adapter-test", "speakers": {"Base01": {}}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_root / "parse-enrichments.json").write_text("{}\n", encoding="utf-8")
    (project_root / "annotations" / "Base01.parse.json").write_text(
        json.dumps(
            {
                "speaker": "Base01",
                "source_audio": "audio/original/Base01/source.wav",
                "metadata": {
                    "language_code": "sdh",
                    "created": "2026-01-01T00:00:00Z",
                    "modified": "2026-01-01T00:00:00Z",
                },
                "tiers": {
                    "concept": {"intervals": [{"start": 0.0, "end": 0.1, "text": "1: ash"}]},
                    "speaker": {"intervals": [{"start": 0.0, "end": 0.1, "text": "Base01"}]},
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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
    workflow_names = set(WorkflowTools(project_root=tmp_path).tool_names())

    phantom = mcp_names - (chat_names | workflow_names)
    adapter_only = {"mcp_get_exposure_mode"}
    assert phantom <= adapter_only, (
        "MCP tools that are NOT in ParseChatTools.tool_names() will raise "
        "ChatToolValidationError at runtime unless they are explicit adapter-only tools. "
        "Unexpected phantom tools: {0}".format(sorted(phantom - adapter_only))
    )


def test_parse_chat_tools_get_all_tool_names_matches_instance(tmp_path) -> None:
    instance_names = ParseChatTools(project_root=tmp_path).tool_names()
    assert ParseChatTools.get_all_tool_names() == instance_names



def test_job_observability_tools_are_allowlisted(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    for tool_name in ["jobs_list", "job_status", "job_logs"]:
        assert tool_name in tools.tool_names()


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_create_mcp_server_exposes_55_parse_tools_by_default_without_config(tmp_path, monkeypatch) -> None:
    import asyncio
    import json

    from adapters.mcp_adapter import create_mcp_server

    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in mcp_tools}

    assert len(mcp_tools) == 59
    assert "mcp_get_exposure_mode" in tool_names
    assert "run_full_annotation_pipeline" in tool_names
    assert "prepare_compare_mode" in tool_names
    assert "export_complete_lingpy_dataset" in tool_names
    assert "retranscribe_with_boundaries_start" in tool_names
    assert "retranscribe_with_boundaries_status" in tool_names
    assert "compute_boundaries_start" in tool_names
    assert "compute_boundaries_status" in tool_names
    assert "audio_normalize_start" in tool_names
    assert "audio_normalize_status" in tool_names
    assert "clef_clear_data" in tool_names
    assert "export_annotations_csv" in tool_names
    assert "transcript_reformat" in tool_names

    _, meta = asyncio.run(server.call_tool("mcp_get_exposure_mode", {}))
    payload = json.loads(meta["result"])
    assert payload["ok"] is True
    assert payload["result"]["exposeAllTools"] is False
    assert payload["result"]["configSource"] is None
    assert payload["result"]["mcpToolCount"] == 59
    assert payload["result"]["parseChatToolCount"] == 55
    assert payload["result"]["workflowToolCount"] == 3


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_create_mcp_server_explicit_false_config_preserves_legacy_curated_surface(tmp_path, monkeypatch) -> None:
    import asyncio
    import json

    from adapters.mcp_adapter import create_mcp_server

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "mcp_config.json").write_text('{"expose_all_tools": false}\n', encoding="utf-8")

    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in mcp_tools}

    assert len(mcp_tools) == 40
    assert "annotation_read" in tool_names
    assert "jobs_list" in tool_names
    assert "audio_normalize_start" not in tool_names
    assert "clef_clear_data" not in tool_names
    assert "export_annotations_csv" not in tool_names
    assert "transcript_reformat" not in tool_names

    _, meta = asyncio.run(server.call_tool("mcp_get_exposure_mode", {}))
    payload = json.loads(meta["result"])
    assert payload["ok"] is True
    assert payload["result"]["exposeAllTools"] is False
    assert payload["result"]["configSource"] == str(config_dir / "mcp_config.json")
    assert payload["result"]["mcpToolCount"] == 40
    assert payload["result"]["defaultParseMcpToolCount"] == 55


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_create_mcp_server_exposes_all_55_tools_when_enabled_in_config_dir(tmp_path, monkeypatch) -> None:
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
    assert len(mcp_tools) == 59

    _, meta = asyncio.run(server.call_tool("mcp_get_exposure_mode", {}))
    payload = json.loads(meta["result"])
    assert payload["ok"] is True
    assert payload["result"]["exposeAllTools"] is True
    assert payload["result"]["mcpToolCount"] == 59
    assert payload["result"]["parseChatToolCount"] == 55
    assert payload["result"]["workflowToolCount"] == 3


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_create_mcp_server_exposes_all_55_tools_when_enabled_in_root_config(tmp_path, monkeypatch) -> None:
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
    assert len(mcp_tools) == 59

    _, meta = asyncio.run(server.call_tool("mcp_get_exposure_mode", {}))
    payload = json.loads(meta["result"])
    assert payload["result"]["configSource"] == str(tmp_path / "mcp_config.json")
    assert payload["result"]["exposeAllTools"] is True


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_create_mcp_server_accepts_direct_named_arguments_for_registered_tools(tmp_path, monkeypatch) -> None:
    import asyncio

    from adapters.mcp_adapter import create_mcp_server

    _seed_minimal_annotation_project(tmp_path)
    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)

    server = create_mcp_server(str(tmp_path))
    _, meta = asyncio.run(server.call_tool("annotation_read", {"speaker": "Base01"}))
    payload = json.loads(meta["result"])

    assert payload["ok"] is True
    assert payload["tool"] == "annotation_read"
    assert payload["result"]["speaker"] == "Base01"


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_mcp_apply_timestamp_offset_returns_shifted_concepts(tmp_path, monkeypatch) -> None:
    import asyncio

    from adapters.mcp_adapter import create_mcp_server

    _seed_minimal_annotation_project(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "mcp_config.json").write_text('{"expose_all_tools": true}\n', encoding="utf-8")
    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)

    server = create_mcp_server(str(tmp_path))
    _, meta = asyncio.run(
        server.call_tool(
            "apply_timestamp_offset",
            {"speaker": "Base01", "offsetSec": 0.25, "dryRun": False},
        )
    )
    payload = json.loads(meta["result"])

    assert payload["ok"] is True
    assert payload["tool"] == "apply_timestamp_offset"
    assert payload["result"]["shiftedIntervals"] == 2
    assert payload["result"]["shiftedConcepts"] == 1


@pytest.mark.skipif(not _has_mcp(), reason="mcp package not installed")
def test_default_mcp_tool_metadata_matches_oracle_contract_for_preview_and_job_observability_tools(tmp_path, monkeypatch) -> None:
    import asyncio

    from adapters.mcp_adapter import create_mcp_server

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "mcp_config.json").write_text('{"expose_all_tools": true}\n', encoding="utf-8")

    monkeypatch.delenv("PARSE_PROJECT_ROOT", raising=False)
    server = create_mcp_server(str(tmp_path))
    mcp_tools = asyncio.run(server.list_tools())
    by_name = {tool.name: tool for tool in mcp_tools}

    assert by_name["audio_normalize_status"].description == (
        "Poll status of a normalize job started with audio_normalize_start. Returns status, progress, error, and result when complete."
    )
    assert by_name["compute_status"].description == (
        "Poll any compute job (full_pipeline, ortho, ipa, contact-lexemes, …) by jobId. Read-only. Returns the job snapshot with status, progress, message, and — for completed jobs — the full ``result`` payload. For pipeline jobs the result includes per-step status and summary counts so the agent can reason about success/skip/error cells."
    )
    assert by_name["compute_status"].inputSchema["properties"]["computeType"]["description"] == (
        'Optional expected compute type (e.g. "full_pipeline"). If provided, the tool validates the job\'s type matches before returning the snapshot.'
    )
    assert by_name["forced_align_status"].description == "Read status/progress of an existing Tier 2 forced-alignment job."
    assert by_name["ipa_transcribe_acoustic_status"].description == "Read status/progress of an existing Tier 3 acoustic IPA job."
    assert by_name["job_logs"].description == (
        "Read structured log lines for any PARSE background job. Returns timestamped entries for progress and terminal events."
    )
    assert by_name["job_logs"].inputSchema["properties"]["limit"]["maximum"] == 200
    assert by_name["job_logs"].inputSchema["properties"]["offset"]["maximum"] == 10000
    assert by_name["job_status"].description == (
        "Read the generic status of any PARSE background job by jobId. Returns type, status, progress, message, error, result, timestamps, and logCount."
    )
    assert by_name["jobs_list"].description == (
        "List jobs from the PARSE job registry, including active and recent completed jobs. Supports filtering by status, type, and speaker, plus a bounded result limit."
    )
    assert by_name["jobs_list"].inputSchema["properties"]["statuses"]["items"]["maxLength"] == 32
    assert by_name["jobs_list"].inputSchema["properties"]["statuses"]["maxItems"] == 10
    assert by_name["jobs_list"].inputSchema["properties"]["types"]["items"]["maxLength"] == 128
    assert by_name["jobs_list"].inputSchema["properties"]["types"]["maxItems"] == 20
    assert by_name["jobs_list_active"].description == (
        "List all currently-running jobs in the PARSE job registry (STT, normalize, compute, onboard, etc.). Returns type, status, progress, speaker, and message for each active job. Useful for recovering jobIds after a session restart."
    )
    assert by_name["read_audio_info"].description == (
        "Read metadata for a WAV file in the project audio directory: duration, sample rate, channels, sample width, frame count, and file size. Read-only; does not return audio samples."
    )
    assert by_name["read_audio_info"].inputSchema["properties"]["sourceWav"]["maxLength"] == 512
    assert by_name["read_csv_preview"].description == (
        "Read first N rows of any CSV file and return column names, delimiter, total row count, and a sample. Defaults to concepts.csv in project root if no path given. Path must stay within the project root. Read-only."
    )
    assert by_name["read_csv_preview"].inputSchema["properties"]["csvPath"]["maxLength"] == 512
    assert "minLength" not in by_name["read_csv_preview"].inputSchema["properties"]["csvPath"]
    assert by_name["read_csv_preview"].inputSchema["properties"]["maxRows"]["default"] == 20
    assert by_name["read_text_preview"].description == (
        "Read a Markdown/text file preview from workspace or docs root. Allowed extensions: .md, .markdown, .txt, .rst. Read-only."
    )
    assert by_name["read_text_preview"].inputSchema["properties"]["path"]["maxLength"] == 1024
    assert by_name["read_text_preview"].inputSchema["properties"]["startLine"]["default"] == 1
    assert by_name["read_text_preview"].inputSchema["properties"]["startLine"]["maximum"] == 200000
    assert by_name["read_text_preview"].inputSchema["properties"]["maxLines"]["default"] == 120
    assert by_name["read_text_preview"].inputSchema["properties"]["maxLines"]["maximum"] == 400
    assert by_name["read_text_preview"].inputSchema["properties"]["maxChars"]["default"] == 12000
    assert by_name["read_text_preview"].inputSchema["properties"]["maxChars"]["minimum"] == 200
    assert by_name["speakers_list"].description == (
        "List every speaker with an annotation file under ``annotations/``. Read-only. Use as the starting point for a batch pipeline run — pair with ``pipeline_state_batch`` to see which speakers are ready to process. Filters out non-annotation entries (e.g. a ``backups/`` directory) so the list is directly usable as input to ``pipeline_run``."
    )
    assert by_name["spectrogram_preview"].description == (
        "Read-only placeholder/backend hook for spectrogram preview requests. Validates bounds and reports capability status."
    )
    assert by_name["spectrogram_preview"].inputSchema["properties"]["sourceWav"]["maxLength"] == 512
    assert by_name["spectrogram_preview"].inputSchema["properties"]["windowSize"]["enum"] == [256, 512, 1024, 2048, 4096]
    assert by_name["stt_status"].description == "Read status/progress of an existing STT job."
    assert by_name["stt_status"].inputSchema["properties"]["maxSegments"]["maximum"] == 300
    assert by_name["stt_word_level_status"].description == (
        "Read status of a Tier 1 word-level STT job. When includeSegments=true the returned segments include the nested words[] payload produced by word_timestamps=True."
    )
    assert by_name["stt_word_level_status"].inputSchema["properties"]["maxSegments"]["maximum"] == 300


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
    and behavior. Count source-level definitions across the monolith + extracted
    bundle modules to keep that from returning."""
    import re

    ai_dir = pathlib.Path(__file__).resolve().parent.parent / "ai"
    chat_tools_source = ai_dir / "chat_tools.py"
    tool_module_sources = sorted((ai_dir / "tools").glob("*.py"))

    chat_tools_text = chat_tools_source.read_text(encoding="utf-8")
    combined_specs_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [chat_tools_source, *tool_module_sources]
    )

    for tool in [
        "annotation_read", "audio_normalize_start", "cognate_compute_preview", "contact_lexeme_lookup",
        "cross_speaker_match_preview", "detect_timestamp_offset", "detect_timestamp_offset_from_pair",
        "apply_timestamp_offset", "forced_align_start", "import_processed_speaker", "import_tag_csv",
        "ipa_transcribe_acoustic_start", "onboard_speaker_import", "parse_memory_read",
        "parse_memory_upsert_section", "pipeline_run", "pipeline_state_batch", "pipeline_state_read",
        "prepare_tag_import", "project_context_read", "read_csv_preview", "spectrogram_preview",
        "stt_start", "stt_status", "stt_word_level_start",
    ]:
        spec_count = len(re.findall(r'"{0}":\s*ChatToolSpec'.format(re.escape(tool)), combined_specs_text))
        handler_count = len(re.findall(r"^\s*def _tool_{0}\s*\(".format(re.escape(tool)), chat_tools_text, re.MULTILINE))
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


def test_all_tools_expose_project_loaded_precondition_when_required(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    requiring_project = {
        spec.name
        for spec in tools.iter_tool_specs()
        if any(cond.id == "project_loaded" for cond in spec.preconditions)
    }

    assert "enrichments_write" in requiring_project
    assert "pipeline_run" in requiring_project
    assert "project_context_read" not in requiring_project


def test_all_tools_publish_machine_readable_metadata(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    for spec in tools.iter_tool_specs():
        assert spec.mutability in {"read_only", "stateful_job", "mutating"}
        assert isinstance(spec.preconditions, tuple)
        assert isinstance(spec.postconditions, tuple)
        meta = spec.mcp_meta_payload()
        assert "mutability" in meta
        assert "supports_dry_run" in meta
        assert "dry_run_parameter" in meta
        assert isinstance(meta["preconditions"], list)
        assert isinstance(meta["postconditions"], list)


def test_stateful_job_starters_are_marked_stateful_with_project_preconditions(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)

    for tool_name in [
        "stt_start",
        "stt_word_level_start",
        "forced_align_start",
        "ipa_transcribe_acoustic_start",
        "compute_boundaries_start",
        "retranscribe_with_boundaries_start",
        "audio_normalize_start",
    ]:
        spec = tools.tool_spec(tool_name)
        assert spec.mutability == "stateful_job"
        assert any(cond.id == "project_loaded" for cond in spec.preconditions)
        assert any(cond.kind == "job_state" for cond in spec.postconditions)


def test_retranscribe_with_boundaries_start_dispatches_compute_job(tmp_path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_start_compute(compute_type: str, payload: dict[str, object]) -> str:
        calls.append((compute_type, dict(payload)))
        return "job-bnd-stt"

    tools = ParseChatTools(
        project_root=tmp_path,
        start_compute_job=fake_start_compute,
    )
    payload = tools.execute(
        "retranscribe_with_boundaries_start",
        {"speaker": "Fail02", "language": "ku"},
    )["result"]

    assert calls == [
        (
            "retranscribe_with_boundaries",
            {"speaker": "Fail02", "language": "ku"},
        )
    ]
    assert payload["jobId"] == "job-bnd-stt"
    assert payload["status"] == "running"
    assert payload["tier"] == "boundary_constrained_stt"
    assert payload["speaker"] == "Fail02"
    assert payload["language"] == "ku"


def test_retranscribe_with_boundaries_start_omits_blank_language(tmp_path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_start_compute(compute_type: str, payload: dict[str, object]) -> str:
        calls.append((compute_type, dict(payload)))
        return "job-bnd-stt"

    tools = ParseChatTools(
        project_root=tmp_path,
        start_compute_job=fake_start_compute,
    )
    tools.execute(
        "retranscribe_with_boundaries_start",
        {"speaker": "Fail02", "language": "   "},
    )

    assert calls == [("retranscribe_with_boundaries", {"speaker": "Fail02"})]


def test_retranscribe_with_boundaries_start_dry_run_does_not_launch(tmp_path) -> None:
    calls: list[object] = []

    def fake_start_compute(compute_type: str, payload: dict[str, object]) -> str:
        calls.append((compute_type, payload))
        return "job-bnd-stt"

    tools = ParseChatTools(
        project_root=tmp_path,
        start_compute_job=fake_start_compute,
    )
    payload = tools.execute(
        "retranscribe_with_boundaries_start",
        {"speaker": "Fail02", "dryRun": True},
    )["result"]

    assert payload["status"] == "dry_run"
    assert payload["tool"] == "retranscribe_with_boundaries_start"
    assert payload["plan"]["speaker"] == "Fail02"
    assert calls == []


def test_retranscribe_with_boundaries_status_reads_snapshot(tmp_path) -> None:
    snapshot = {
        "jobId": "job-bnd-stt",
        "type": "retranscribe_with_boundaries",
        "status": "complete",
        "progress": 100.0,
        "message": "done",
        "result": {
            "speaker": "Fail02",
            "boundary_intervals": 12,
            "segments_written": 12,
            "source": "boundary_constrained",
        },
    }
    tools = ParseChatTools(
        project_root=tmp_path,
        get_job_snapshot=lambda job_id: snapshot,
    )

    payload = tools.execute(
        "retranscribe_with_boundaries_status",
        {"jobId": "job-bnd-stt"},
    )["result"]

    assert payload["jobId"] == "job-bnd-stt"
    assert payload["status"] == "complete"
    assert payload["tier"] == "boundary_constrained_stt"
    assert payload["result"]["source"] == "boundary_constrained"


def test_compute_boundaries_start_dispatches_canonical_compute_type(tmp_path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_start_compute(compute_type: str, payload: dict[str, object]) -> str:
        calls.append((compute_type, dict(payload)))
        return "job-bnd"

    tools = ParseChatTools(
        project_root=tmp_path,
        start_compute_job=fake_start_compute,
    )
    payload = tools.execute(
        "compute_boundaries_start",
        {"speaker": "Fail02"},
    )["result"]

    assert calls == [("boundaries", {"speaker": "Fail02", "overwrite": False})]
    assert payload["jobId"] == "job-bnd"
    assert payload["status"] == "running"
    assert payload["tier"] == "tier2_boundaries_only"
    assert payload["speaker"] == "Fail02"
    assert payload["overwrite"] is False


def test_compute_boundaries_start_forwards_overwrite_flag(tmp_path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_start_compute(compute_type: str, payload: dict[str, object]) -> str:
        calls.append((compute_type, dict(payload)))
        return "job-bnd"

    tools = ParseChatTools(
        project_root=tmp_path,
        start_compute_job=fake_start_compute,
    )
    tools.execute(
        "compute_boundaries_start",
        {"speaker": "Fail02", "overwrite": True},
    )

    assert calls == [("boundaries", {"speaker": "Fail02", "overwrite": True})]


def test_compute_boundaries_start_dry_run_does_not_launch(tmp_path) -> None:
    calls: list[object] = []

    def fake_start_compute(compute_type: str, payload: dict[str, object]) -> str:
        calls.append((compute_type, payload))
        return "job-bnd"

    tools = ParseChatTools(
        project_root=tmp_path,
        start_compute_job=fake_start_compute,
    )
    payload = tools.execute(
        "compute_boundaries_start",
        {"speaker": "Fail02", "dryRun": True},
    )["result"]

    assert payload["status"] == "dry_run"
    assert payload["tool"] == "compute_boundaries_start"
    assert payload["plan"]["speaker"] == "Fail02"
    assert calls == []


def test_compute_boundaries_status_reads_snapshot(tmp_path) -> None:
    snapshot = {
        "jobId": "job-bnd",
        "type": "boundaries",
        "status": "complete",
        "progress": 100.0,
        "message": "done",
        "result": {
            "speaker": "Fail02",
            "generated": 8,
            "preserved_manual": 2,
            "total": 10,
        },
    }
    tools = ParseChatTools(
        project_root=tmp_path,
        get_job_snapshot=lambda job_id: snapshot,
    )

    payload = tools.execute(
        "compute_boundaries_status",
        {"jobId": "job-bnd"},
    )["result"]

    assert payload["jobId"] == "job-bnd"
    assert payload["status"] == "complete"
    assert payload["tier"] == "tier2_boundaries_only"
    assert payload["result"]["generated"] == 8
    assert payload["result"]["preserved_manual"] == 2


def test_compute_boundaries_distinct_from_forced_align_and_retranscribe(tmp_path) -> None:
    seen: list[str] = []

    def fake_start_compute(compute_type: str, payload: dict[str, object]) -> str:
        seen.append(compute_type)
        return "job"

    tools = ParseChatTools(
        project_root=tmp_path,
        start_compute_job=fake_start_compute,
    )
    tools.execute("forced_align_start", {"speaker": "Fail02"})
    tools.execute("compute_boundaries_start", {"speaker": "Fail02"})
    tools.execute("retranscribe_with_boundaries_start", {"speaker": "Fail02"})

    assert seen == ["forced_align", "boundaries", "retranscribe_with_boundaries"]


def test_stt_start_supports_dry_run_preview(tmp_path) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "clip.wav").write_bytes(b"RIFFWAVE")

    calls = []

    def fake_start_stt(speaker: str, source_wav: str, language: str | None) -> str:
        calls.append((speaker, source_wav, language))
        return "job-stt"

    tools = ParseChatTools(project_root=tmp_path, start_stt_job=fake_start_stt)
    payload = tools.execute(
        "stt_start",
        {"speaker": "Fail02", "sourceWav": "audio/clip.wav", "dryRun": True},
    )["result"]

    assert payload["status"] == "dry_run"
    assert payload["plan"]["speaker"] == "Fail02"
    assert calls == []


def test_audio_normalize_start_supports_dry_run_preview(tmp_path) -> None:
    calls = []

    def fake_normalize(speaker: str, source_wav: str | None) -> str:
        calls.append((speaker, source_wav))
        return "job-normalize"

    tools = ParseChatTools(project_root=tmp_path, start_normalize_job=fake_normalize)
    payload = tools.execute(
        "audio_normalize_start",
        {"speaker": "Fail02", "sourceWav": "audio/clip.wav", "dryRun": True},
    )["result"]

    assert payload["status"] == "dry_run"
    assert payload["plan"]["speaker"] == "Fail02"
    assert calls == []


def test_job_status_surfaces_speaker_lock_metadata(tmp_path) -> None:
    snapshot = {
        "jobId": "job-lock",
        "type": "stt",
        "status": "running",
        "progress": 12.5,
        "message": "Transcribing",
        "meta": {"speaker": "Fail01"},
        "locks": {
            "active": True,
            "ttl_seconds": 600,
            "resources": [{"kind": "speaker", "id": "Fail01"}],
        },
        "logs": [{"event": "job.created"}],
    }
    tools = ParseChatTools(project_root=tmp_path, get_job_snapshot=lambda job_id: snapshot)

    payload = tools.execute("job_status", {"jobId": "job-lock"})["result"]

    assert payload["jobId"] == "job-lock"
    assert payload["locks"]["active"] is True
    assert payload["locks"]["resources"] == [{"kind": "speaker", "id": "Fail01"}]


def test_source_index_validate_dry_run_does_not_write_output(tmp_path) -> None:
    tools = ParseChatTools(project_root=tmp_path)
    output_path = tmp_path / "source_index.json"
    manifest = {
        "speakers": {
            "Fail01": {
                "wav_files": [
                    {
                        "path": "Audio_Original/Fail01/a.wav",
                        "duration_sec": 10.0,
                        "file_size_bytes": 320000,
                        "bit_depth": 16,
                        "sample_rate": 16000,
                        "channels": 1,
                        "lexicon_start_sec": 0.0,
                        "is_primary": True,
                    }
                ],
                "has_csv": False,
            }
        }
    }

    payload = tools.execute(
        "source_index_validate",
        {
            "mode": "full",
            "manifest": manifest,
            "outputPath": str(output_path),
            "dryRun": True,
        },
    )["result"]

    assert payload["readOnly"] is True
    assert payload["previewOnly"] is True
    assert payload["dryRun"] is True
    assert output_path.exists() is False
