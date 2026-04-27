import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _wait_for_http_json(url: str, *, timeout_seconds: float = 10.0) -> tuple[int, dict[str, object]]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return int(response.status), payload
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


def test_server_script_mode_boots_cleanly_and_serves_config(tmp_path: pathlib.Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server_path = pathlib.Path(__file__).resolve().parent / "server.py"
    log_path = tmp_path / "server.log"
    env = dict(os.environ)
    env["PARSE_WS_PORT"] = "0"
    env["PYTHONUNBUFFERED"] = "1"

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [sys.executable, str(server_path)],
            cwd=workspace,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    try:
        status, payload = _wait_for_http_json("http://127.0.0.1:8766/api/config")
        assert status == 200
        assert isinstance(payload, dict)
        assert process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    log_text = log_path.read_text(encoding="utf-8")
    assert "NameError: name '_api_get_annotation' is not defined" not in log_text


def test_importing_server_does_not_preinstall_route_handlers() -> None:
    code = """
import json
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(r'REPO_PYTHON').resolve()))
import server
print(json.dumps({
    'api_get_config_installed': '_api_get_config' in server.RangeRequestHandler.__dict__,
    'api_post_annotation_installed': '_api_post_annotation' in server.RangeRequestHandler.__dict__,
}))
""".replace("REPO_PYTHON", str(pathlib.Path(__file__).resolve().parent))
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout.strip())
    assert payload == {
        "api_get_config_installed": False,
        "api_post_annotation_installed": False,
    }
