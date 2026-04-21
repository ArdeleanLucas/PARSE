"""Tests for chat turn priming — parse-memory.md and source_index.json are
auto-injected into every turn's system context so the model doesn't have to
call parse_memory_read / project_context_read to see them."""
import json
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

import pytest

from ai import chat_orchestrator
from ai.chat_orchestrator import ChatOrchestrator
from ai.chat_tools import ParseChatTools


class _StubRuntime:
    def __init__(self, chat_config):
        self.chat_config = chat_config
        self.model = "stub-model"


@pytest.fixture
def stub_runtime(monkeypatch):
    def _install(chat_config):
        monkeypatch.setattr(
            chat_orchestrator,
            "OpenAIChatRuntime",
            lambda *args, **kwargs: _StubRuntime(chat_config),
        )

    return _install


def test_priming_block_empty_when_no_memory_or_source_index(tmp_path, monkeypatch, stub_runtime) -> None:
    stub_runtime({})
    tools = ParseChatTools(project_root=tmp_path)
    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    assert orch._build_turn_priming_block() == ""


def test_priming_block_includes_parse_memory_content(tmp_path, monkeypatch, stub_runtime) -> None:
    stub_runtime({})
    (tmp_path / "parse-memory.md").write_text(
        "# PARSE chat memory\n\n## User preferences\n- terse tone\n",
        encoding="utf-8",
    )
    tools = ParseChatTools(project_root=tmp_path)
    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    block = orch._build_turn_priming_block()
    assert "Persistent memory" in block
    assert "terse tone" in block
    assert "parse-memory.md" in block


def test_priming_block_truncates_oversize_memory(tmp_path, monkeypatch, stub_runtime) -> None:
    stub_runtime({})
    big_payload = "# memory\n\n" + ("a" * (32 * 1024))
    (tmp_path / "parse-memory.md").write_text(big_payload, encoding="utf-8")
    tools = ParseChatTools(project_root=tmp_path)
    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    block = orch._build_turn_priming_block()
    assert "(truncated — call parse_memory_read for full content)" in block


def test_priming_block_includes_source_index_summary(tmp_path, monkeypatch, stub_runtime) -> None:
    stub_runtime({})
    source_index = {
        "speakers": {
            "Faili01": {
                "source_wavs": [
                    {
                        "path": "audio/original/Faili01/Faili_M_1984.wav",
                        "filename": "Faili_M_1984.wav",
                        "is_primary": True,
                    }
                ],
            },
            "Kalh01": {
                "source_wavs": [
                    {"path": "audio/original/Kalh01/Kalh_F_1990.wav", "is_primary": True},
                    {"path": "audio/original/Kalh01/alt_take.wav", "is_primary": False},
                ],
            },
        }
    }
    (tmp_path / "source_index.json").write_text(json.dumps(source_index), encoding="utf-8")
    tools = ParseChatTools(project_root=tmp_path)
    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    block = orch._build_turn_priming_block()
    assert "Source index summary" in block
    assert "Faili01" in block
    assert "Faili_M_1984.wav" in block
    assert "Kalh01" in block
    assert "+1 more" in block  # secondary wav counted


def test_run_injects_priming_block_as_second_system_message(tmp_path, monkeypatch, stub_runtime) -> None:
    """The priming block must appear as its own system message so the model
    sees it even when the static system prompt is cached upstream."""
    stub_runtime({})
    (tmp_path / "parse-memory.md").write_text(
        "## User preferences\n- terse tone\n", encoding="utf-8"
    )

    tools = ParseChatTools(project_root=tmp_path)
    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    captured: dict = {}

    class _FakeChoice:
        def __init__(self, text):
            self.message = type("Msg", (), {"content": text, "tool_calls": None})()

    class _FakeResponse:
        def __init__(self, text):
            self.choices = [_FakeChoice(text)]

    def _fake_complete(messages, tools=None, tool_choice=None):
        captured["messages"] = list(messages)
        return _FakeResponse("ok"), {"model": "stub-model"}

    orch.runtime.complete = _fake_complete  # type: ignore[assignment]

    orch.run(
        session_id="session-1",
        session_messages=[{"role": "user", "content": "hi"}],
    )

    msgs = captured["messages"]
    # [0] is the static system prompt; [1] is the auto-priming block; [2] is the user turn.
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "system"
    assert "terse tone" in msgs[1]["content"]
    assert msgs[2]["role"] == "user"


def test_priming_reflects_parse_memory_updates_between_turns(tmp_path, monkeypatch, stub_runtime) -> None:
    """An update from turn N must be visible in turn N+1's priming block."""
    stub_runtime({})
    tools = ParseChatTools(project_root=tmp_path)
    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    # Simulate a write that the agent made on turn N.
    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- Faili01 from Fail01", "dryRun": False},
    )

    block = orch._build_turn_priming_block()
    assert "Faili01 from Fail01" in block

    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- Faili01 from Fail01\n- Kalh01 from Kalh01", "dryRun": False},
    )

    block2 = orch._build_turn_priming_block()
    assert "Kalh01 from Kalh01" in block2
