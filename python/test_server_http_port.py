import os
import pathlib
import socket
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"PARSE_PORT": "8866"}, 8866),
        ({"PARSE_API_PORT": "8877"}, 8877),
        ({"PARSE_PORT": "8866", "PARSE_API_PORT": "8877"}, 8866),
        ({}, 8766),
    ],
)
def test_resolve_http_port_supports_parse_port_and_parse_api_port(monkeypatch, env, expected) -> None:
    monkeypatch.delenv("PARSE_PORT", raising=False)
    monkeypatch.delenv("PARSE_API_PORT", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert server._resolve_http_port() == expected


@pytest.mark.parametrize(
    "value",
    ["", "not-a-number", "-1", "65536"],
)
def test_resolve_http_port_rejects_invalid_values(monkeypatch, value) -> None:
    monkeypatch.setenv("PARSE_PORT", value)
    monkeypatch.delenv("PARSE_API_PORT", raising=False)

    assert server._resolve_http_port() == 8766


def test_startup_banner_lines_use_resolved_http_port(monkeypatch, tmp_path: pathlib.Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("PARSE_API_PORT", "8866")
    monkeypatch.delenv("PARSE_PORT", raising=False)
    monkeypatch.setattr(server, "_resolve_ws_port", lambda: 9001)

    lines = server._startup_banner_lines(tmp_path, ["192.168.1.20"])

    assert "  Port   : 8866" in lines
    assert "    PARSE   : http://localhost:8866/" in lines
    assert "    Compare : http://localhost:8866/compare" in lines
    assert "    PARSE   : http://192.168.1.20:8866/" in lines
    assert "    Compare : http://192.168.1.20:8866/compare" in lines


def test_server_script_mode_starts_without_server_module_nameerror(tmp_path: pathlib.Path) -> None:
    log_path = tmp_path / "server.log"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = dict(os.environ)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        http_port = sock.getsockname()[1]
    env["PARSE_PORT"] = str(http_port)
    env["PARSE_WS_PORT"] = "0"
    env["PYTHONUNBUFFERED"] = "1"

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [sys.executable, str(pathlib.Path(server.__file__).resolve())],
            cwd=workspace,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    started = False
    try:
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if process.poll() is not None:
                break
            try:
                with socket.create_connection(("127.0.0.1", http_port), timeout=0.2):
                    started = True
                    break
            except OSError:
                time.sleep(0.25)

        text = log_path.read_text(encoding="utf-8")
        assert "NameError: name '_api_get_annotation' is not defined" not in text
        assert started is True
        assert process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
