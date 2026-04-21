import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


def test_reset_chat_runtime_after_auth_key_save_clears_cached_runtime() -> None:
    original_tools = server._chat_tools_runtime
    original_orchestrator = server._chat_orchestrator_runtime
    try:
        server._chat_tools_runtime = object()
        server._chat_orchestrator_runtime = object()

        server._reset_chat_runtime_after_auth_key_save()

        assert server._chat_tools_runtime is None
        assert server._chat_orchestrator_runtime is None
    finally:
        server._chat_tools_runtime = original_tools
        server._chat_orchestrator_runtime = original_orchestrator
