import pathlib
import subprocess
import sys


def _python_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def test_server_imports_without_websockets_installed() -> None:
    script = f"""
import builtins
import pathlib
import sys

orig_import = builtins.__import__

def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'websockets' or name.startswith('websockets.'):
        raise ImportError("No module named 'websockets'")
    return orig_import(name, globals, locals, fromlist, level)

builtins.__import__ = fake_import
sys.path.insert(0, {str(_python_dir())!r})
import server
print('SERVER_IMPORT_OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SERVER_IMPORT_OK" in result.stdout


def test_starting_sidecar_without_websockets_gives_clear_error() -> None:
    script = f"""
import builtins
import pathlib
import sys

orig_import = builtins.__import__

def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'websockets' or name.startswith('websockets.'):
        raise ImportError("No module named 'websockets'")
    return orig_import(name, globals, locals, fromlist, level)

builtins.__import__ = fake_import
sys.path.insert(0, {str(_python_dir())!r})
import server
try:
    server._start_websocket_sidecar(host='127.0.0.1', port=0)
except RuntimeError as exc:
    print(str(exc))
else:
    raise SystemExit('expected RuntimeError')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "requires the optional 'websockets' package" in result.stdout
