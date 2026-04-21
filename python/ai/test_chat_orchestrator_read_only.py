"""Regression coverage for chat orchestrator read-only resolution.

Before this change the orchestrator unconditionally forced ``read_only=True``,
ignoring ``chat.read_only`` in ``config/ai_config.json`` and ignoring the
``PARSE_CHAT_READ_ONLY`` environment override. New behavior: config drives the
default, env overrides config.
"""
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
def patched_runtime(monkeypatch):
    """Patch OpenAIChatRuntime to a stub so ChatOrchestrator can be constructed
    without touching credentials or network."""
    def _factory(chat_config):
        def _build(*args, **kwargs):
            return _StubRuntime(chat_config)

        monkeypatch.setattr(chat_orchestrator, "OpenAIChatRuntime", _build)

    return _factory


def test_read_only_defaults_to_config_value(tmp_path, monkeypatch, patched_runtime) -> None:
    monkeypatch.delenv("PARSE_CHAT_READ_ONLY", raising=False)
    patched_runtime({"read_only": False})
    tools = ParseChatTools(project_root=tmp_path)

    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    assert orch.read_only is False


def test_read_only_config_true_is_respected(tmp_path, monkeypatch, patched_runtime) -> None:
    monkeypatch.delenv("PARSE_CHAT_READ_ONLY", raising=False)
    patched_runtime({"read_only": True})
    tools = ParseChatTools(project_root=tmp_path)

    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    assert orch.read_only is True


def test_env_overrides_config_to_enable_writes(tmp_path, monkeypatch, patched_runtime) -> None:
    monkeypatch.setenv("PARSE_CHAT_READ_ONLY", "0")
    patched_runtime({"read_only": True})
    tools = ParseChatTools(project_root=tmp_path)

    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    assert orch.read_only is False


def test_env_overrides_config_to_enforce_read_only(tmp_path, monkeypatch, patched_runtime) -> None:
    monkeypatch.setenv("PARSE_CHAT_READ_ONLY", "1")
    patched_runtime({"read_only": False})
    tools = ParseChatTools(project_root=tmp_path)

    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    assert orch.read_only is True


def test_write_mode_system_prompt_omits_read_only_language(tmp_path, monkeypatch, patched_runtime) -> None:
    monkeypatch.setenv("PARSE_CHAT_READ_ONLY", "0")
    patched_runtime({"read_only": True})
    tools = ParseChatTools(project_root=tmp_path)

    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    assert "WRITE-ENABLED MODE" in orch._system_prompt
    assert "READ-ONLY MODE" not in orch._system_prompt


def test_read_mode_system_prompt_has_read_only_language(tmp_path, monkeypatch, patched_runtime) -> None:
    monkeypatch.setenv("PARSE_CHAT_READ_ONLY", "1")
    patched_runtime({"read_only": False})
    tools = ParseChatTools(project_root=tmp_path)

    orch = ChatOrchestrator(project_root=tmp_path, tools=tools)

    assert "READ-ONLY MODE" in orch._system_prompt
