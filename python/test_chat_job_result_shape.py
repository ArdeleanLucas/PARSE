"""Regression coverage for the chat-run job result shape.

The UI expects `result` to be a plain string (the assistant's content).
Prior code set the job result to a dict (`{assistant: {...}, session: {...}, ...}`)
which React then tried to render as a child, unmounting the chat panel and
blanking the page.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


def test_run_chat_job_stores_assistant_string_as_result(monkeypatch) -> None:
    job_id = server._create_job("chat:run", {"sessionId": "chat-1"})

    monkeypatch.setattr(
        server,
        "_chat_get_session_snapshot",
        lambda sid: {"id": sid, "messages": []},
    )

    class _FakeOrchestrator:
        def run(self, session_id, session_messages):
            return {
                "assistant": {"content": "hello from grok"},
                "model": "grok-4.20-0309-reasoning",
                "toolTrace": [],
            }

    monkeypatch.setattr(
        server,
        "_get_chat_runtime",
        lambda: (None, _FakeOrchestrator()),
    )
    monkeypatch.setattr(server, "_chat_append_message", lambda *a, **kw: None)

    server._run_chat_job(job_id, "chat-1")

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["status"] == "complete"
    assert snapshot["result"] == "hello from grok", (
        "Job result must be a plain string — a dict here crashes the React chat panel."
    )
    assert isinstance(snapshot["result"], str)


def test_run_chat_job_result_falls_back_to_default_when_content_missing(monkeypatch) -> None:
    job_id = server._create_job("chat:run", {"sessionId": "chat-2"})

    monkeypatch.setattr(
        server,
        "_chat_get_session_snapshot",
        lambda sid: {"id": sid, "messages": []},
    )

    class _EmptyOrchestrator:
        def run(self, session_id, session_messages):
            return {}

    monkeypatch.setattr(
        server,
        "_get_chat_runtime",
        lambda: (None, _EmptyOrchestrator()),
    )
    monkeypatch.setattr(server, "_chat_append_message", lambda *a, **kw: None)

    server._run_chat_job(job_id, "chat-2")

    snapshot = server._get_job_snapshot(job_id)
    assert snapshot is not None
    assert snapshot["status"] == "complete"
    assert isinstance(snapshot["result"], str)
    assert snapshot["result"]  # non-empty fallback
