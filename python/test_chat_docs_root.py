import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


@pytest.fixture(autouse=True)
def _reset_cached_chat_runtime() -> None:
    server._chat_tools_runtime = None
    server._chat_orchestrator_runtime = None
    yield
    server._chat_tools_runtime = None
    server._chat_orchestrator_runtime = None


class _DummyTools:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _DummyOrchestrator:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_chat_docs_root_relative_to_project_root(monkeypatch, tmp_path) -> None:
    project = (tmp_path / "workspace").resolve()
    docs_rel = "docs/chat"

    monkeypatch.setattr(server, "_project_root", lambda: project)
    monkeypatch.setenv("PARSE_CHAT_DOCS_ROOT", docs_rel)

    resolved = server._chat_docs_root()
    assert resolved == (project / docs_rel).resolve()


def test_get_chat_runtime_passes_docs_root(monkeypatch, tmp_path) -> None:
    project = (tmp_path / "workspace").resolve()
    docs = (tmp_path / "notes").resolve()

    captured = {}

    def _fake_tools_ctor(**kwargs):
        captured.update(kwargs)
        return _DummyTools(**kwargs)

    monkeypatch.setattr(server, "ParseChatTools", _fake_tools_ctor)
    monkeypatch.setattr(server, "ChatOrchestrator", lambda **kwargs: _DummyOrchestrator(**kwargs))
    monkeypatch.setattr(server, "_project_root", lambda: project)
    monkeypatch.setattr(server, "_config_path", lambda: project / "config" / "ai_config.json")
    monkeypatch.setattr(server, "_chat_start_stt_job", lambda *args, **kwargs: "job-1")
    monkeypatch.setattr(server, "_chat_get_job_snapshot", lambda job_id: None)
    monkeypatch.setattr(server, "_chat_docs_root", lambda: docs)

    server._chat_tools_runtime = None
    server._chat_orchestrator_runtime = None

    server._get_chat_runtime()

    assert captured["project_root"] == project
    assert captured["docs_root"] == docs
