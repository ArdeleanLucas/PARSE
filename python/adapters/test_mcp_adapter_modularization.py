import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest
from adapters import mcp_adapter


def test_mcp_adapter_py_is_thin_orchestrator() -> None:
    adapter_path = pathlib.Path(mcp_adapter.__file__).resolve()
    line_count = len(adapter_path.read_text(encoding="utf-8").splitlines())
    assert line_count < 600, f"python/adapters/mcp_adapter.py should be <600 LoC after decomposition, got {line_count}"


@pytest.mark.parametrize(
    ("module_name", "export_name"),
    [
        ("env_config", "_load_repo_parse_env"),
        ("env_config", "_resolve_onboard_http_timeout"),
        ("transport", "_build_stt_callbacks"),
        ("transport", "_build_onboard_callback"),
        ("tool_dispatch", "register_chat_tools"),
        ("schema", "sync_registered_tool_metadata"),
    ],
)
def test_mcp_adapter_re_exports_split_helpers(module_name: str, export_name: str) -> None:
    module = __import__(f"adapters.mcp.{module_name}", fromlist=[export_name])
    exported = getattr(mcp_adapter, export_name)
    assert exported is getattr(module, export_name)
    assert inspect.getmodule(exported).__name__ == module.__name__


def test_create_mcp_server_stays_orchestrator_owned() -> None:
    assert inspect.getmodule(mcp_adapter.create_mcp_server).__name__ == "adapters.mcp_adapter"


def test_repo_root_python_import_smoke() -> None:
    import subprocess

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "-c", "import adapters.mcp_adapter"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
