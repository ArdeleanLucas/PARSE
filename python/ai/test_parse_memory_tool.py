"""Tests for parse_memory_read / parse_memory_upsert_section chat tools."""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from ai.chat_tools import ParseChatTools, WRITE_ALLOWED_TOOL_NAMES


def _tools(tmp_path) -> ParseChatTools:
    return ParseChatTools(project_root=tmp_path)


def test_memory_read_returns_not_exists_when_file_missing(tmp_path) -> None:
    result = _tools(tmp_path).execute("parse_memory_read", {})["result"]
    assert result["ok"] is True
    assert result["exists"] is False
    assert result["content"] == ""


def test_memory_upsert_creates_file_with_header_and_section(tmp_path) -> None:
    tools = _tools(tmp_path)

    payload = tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- Faili01: /mnt/c/...", "dryRun": False},
    )["result"]
    assert payload["ok"] is True
    assert payload["action"] == "create"

    memory = (tmp_path / "parse-memory.md").read_text(encoding="utf-8")
    assert memory.startswith("# PARSE chat memory")
    assert "## Speakers" in memory
    assert "Faili01" in memory


def test_memory_upsert_replaces_existing_section_without_touching_others(tmp_path) -> None:
    tools = _tools(tmp_path)

    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- Faili01", "dryRun": False},
    )
    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Preferences", "body": "- terse tone", "dryRun": False},
    )
    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- Faili01\n- Kalh01", "dryRun": False},
    )

    memory = (tmp_path / "parse-memory.md").read_text(encoding="utf-8")
    # Preferences section untouched
    assert "- terse tone" in memory
    # Speakers section now has both entries
    assert "- Faili01" in memory
    assert "- Kalh01" in memory
    # Section heading appears exactly once
    assert memory.count("## Speakers") == 1


def test_memory_upsert_dry_run_does_not_write(tmp_path) -> None:
    tools = _tools(tmp_path)

    preview = tools.execute(
        "parse_memory_upsert_section",
        {"section": "Notes", "body": "hello", "dryRun": True},
    )["result"]
    assert preview["dryRun"] is True
    assert not (tmp_path / "parse-memory.md").exists()


def test_memory_read_section_filter_returns_just_that_block(tmp_path) -> None:
    tools = _tools(tmp_path)

    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- A", "dryRun": False},
    )
    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Preferences", "body": "- terse", "dryRun": False},
    )

    result = tools.execute("parse_memory_read", {"section": "Speakers"})["result"]
    assert result["ok"] is True
    assert "## Speakers" in result["content"]
    assert "Preferences" not in result["content"]


def test_memory_tools_are_write_allowlisted() -> None:
    # parse_memory_read is read-only; the upsert tool must be in the write allowlist.
    assert "parse_memory_upsert_section" in WRITE_ALLOWED_TOOL_NAMES
    assert "parse_memory_read" not in WRITE_ALLOWED_TOOL_NAMES


def test_onboard_speaker_import_is_write_allowlisted() -> None:
    assert "onboard_speaker_import" in WRITE_ALLOWED_TOOL_NAMES


def test_onboard_speaker_dry_run_reports_plan_without_callback(tmp_path) -> None:
    import wave

    external_root = tmp_path / "external"
    external_root.mkdir()
    wav = external_root / "spk1.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)

    project_root = tmp_path / "proj"
    project_root.mkdir()

    tools = ParseChatTools(
        project_root=project_root,
        external_read_roots=[external_root],
    )

    result = tools.execute(
        "onboard_speaker_import",
        {"speaker": "Speaker01", "sourceWav": str(wav), "dryRun": True},
    )["result"]
    assert result["ok"] is True
    assert result["plan"]["speaker"] == "Speaker01"
    assert result["plan"]["isPrimary"] is True
    assert result["plan"]["wavDest"].endswith("Speaker01/spk1.wav")


def test_onboard_speaker_rejects_source_outside_allowed_roots(tmp_path) -> None:
    import wave

    import pytest

    from ai.chat_tools import ChatToolValidationError

    stray_root = tmp_path / "stray"
    stray_root.mkdir()
    wav = stray_root / "spk.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)

    project_root = tmp_path / "proj"
    project_root.mkdir()

    tools = ParseChatTools(project_root=project_root)  # no external_read_roots

    with pytest.raises(ChatToolValidationError, match="outside allowed read roots"):
        tools.execute(
            "onboard_speaker_import",
            {"speaker": "Speaker01", "sourceWav": str(wav), "dryRun": True},
        )
