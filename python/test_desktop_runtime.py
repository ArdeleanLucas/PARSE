"""Stage 1 (Gate A) desktop-runtime hardening tests.

These exercise the light, dependency-free helpers in
``app.http.desktop_runtime`` so they run without importing ``server.py`` (which
pulls torch/faster-whisper and other heavy runtime deps). ``server.py`` wires
these exact helpers into the health route, ``_add_cors_headers``, the
spectrogram CORS path, and the bind-host resolution, so covering the helpers
covers the behavior the desktop shell depends on.
"""
import importlib

import pytest

from app.http import desktop_runtime as dr


# The static base CORS headers server.py ships today (wildcard origin).
BASE_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Range, Content-Type",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS, POST, PUT, DELETE",
    "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
    "Accept-Ranges": "bytes",
}


@pytest.fixture(autouse=True)
def _clean_desktop_env(monkeypatch):
    """Ensure each test starts with desktop env vars unset."""
    monkeypatch.delenv("PARSE_DESKTOP", raising=False)
    monkeypatch.delenv("PARSE_HOST", raising=False)
    # Re-import to be safe against any module-level caching (there is none, but
    # this makes the isolation explicit).
    importlib.reload(dr)
    yield


# --------------------------------------------------------------------------- #
# /api/health payload
# --------------------------------------------------------------------------- #
def test_health_payload_default_mode():
    payload = dr.build_health_payload()
    assert payload == {"status": "ok", "service": "parse", "desktop": False}


def test_health_payload_desktop_mode(monkeypatch):
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    payload = dr.build_health_payload()
    assert payload == {"status": "ok", "service": "parse", "desktop": True}


def test_health_payload_non_one_flag_is_not_desktop(monkeypatch):
    # Only exactly "1" enables desktop mode.
    monkeypatch.setenv("PARSE_DESKTOP", "true")
    assert dr.build_health_payload()["desktop"] is False


# --------------------------------------------------------------------------- #
# is_desktop_mode gating
# --------------------------------------------------------------------------- #
def test_is_desktop_mode_gating(monkeypatch):
    assert dr.is_desktop_mode() is False
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    assert dr.is_desktop_mode() is True
    monkeypatch.setenv("PARSE_DESKTOP", "0")
    assert dr.is_desktop_mode() is False


# --------------------------------------------------------------------------- #
# Host resolver
# --------------------------------------------------------------------------- #
def test_resolve_host_default_mode_unchanged():
    # Without PARSE_DESKTOP the default 0.0.0.0 bind is preserved exactly.
    assert dr.resolve_host("0.0.0.0") == "0.0.0.0"


def test_resolve_host_desktop_mode_is_loopback(monkeypatch):
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    assert dr.resolve_host("0.0.0.0") == "127.0.0.1"


def test_resolve_host_desktop_honors_explicit_override(monkeypatch):
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    monkeypatch.setenv("PARSE_HOST", "0.0.0.0")
    assert dr.resolve_host("0.0.0.0") == "0.0.0.0"
    monkeypatch.setenv("PARSE_HOST", "192.168.1.5")
    assert dr.resolve_host("0.0.0.0") == "192.168.1.5"


def test_resolve_host_override_ignored_in_default_mode(monkeypatch):
    # PARSE_HOST is only consulted in desktop mode; default mode ignores it.
    monkeypatch.setenv("PARSE_HOST", "127.0.0.1")
    assert dr.resolve_host("0.0.0.0") == "0.0.0.0"


# --------------------------------------------------------------------------- #
# Loopback origin classification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1",
        "http://127.0.0.1:5173",
        "http://localhost",
        "http://localhost:8766",
        "http://[::1]:3000",
    ],
)
def test_loopback_origins_accepted(origin):
    assert dr.is_loopback_origin(origin) is True


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "https://127.0.0.1",          # https is not reflected
        "http://evil.example.com",
        "http://127.0.0.1.evil.com",  # not a real loopback host
        "http://10.0.0.5:8766",
        "garbage",
    ],
)
def test_non_loopback_origins_rejected(origin):
    assert dr.is_loopback_origin(origin) is False


# --------------------------------------------------------------------------- #
# CORS header resolution — the core regression guard
# --------------------------------------------------------------------------- #
def test_default_mode_cors_is_wildcard_verbatim():
    # Guards the existing media_search_handlers test / web-dev behavior.
    headers = dr.resolve_cors_headers(BASE_CORS, origin="http://anything.example.com")
    assert headers["Access-Control-Allow-Origin"] == "*"
    # No Vary added in default mode; headers pass through unchanged.
    assert headers == dict(BASE_CORS)


def test_default_mode_ignores_origin_completely(monkeypatch):
    headers = dr.resolve_cors_headers(BASE_CORS, origin=None)
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_desktop_mode_reflects_loopback_origin(monkeypatch):
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    headers = dr.resolve_cors_headers(BASE_CORS, origin="http://127.0.0.1:5173")
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert "Origin" in headers.get("Vary", "")


def test_desktop_mode_reflects_localhost_origin(monkeypatch):
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    headers = dr.resolve_cors_headers(BASE_CORS, origin="http://localhost:8766")
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:8766"


def test_desktop_mode_no_wildcard_for_non_loopback(monkeypatch):
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    headers = dr.resolve_cors_headers(BASE_CORS, origin="http://evil.example.com")
    # Must NOT emit a wildcard, and must NOT reflect the foreign origin.
    assert "Access-Control-Allow-Origin" not in headers
    assert "Origin" in headers.get("Vary", "")


def test_desktop_mode_no_origin_header_no_acao(monkeypatch):
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    headers = dr.resolve_cors_headers(BASE_CORS, origin=None)
    assert "Access-Control-Allow-Origin" not in headers


def test_desktop_mode_explicit_flag_override(monkeypatch):
    # The `desktop=` kwarg overrides the env for callers that already know.
    headers = dr.resolve_cors_headers(
        BASE_CORS, origin="http://127.0.0.1:5173", desktop=True
    )
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"

    monkeypatch.setenv("PARSE_DESKTOP", "1")
    headers = dr.resolve_cors_headers(
        BASE_CORS, origin="http://127.0.0.1:5173", desktop=False
    )
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_desktop_mode_does_not_mutate_base_headers(monkeypatch):
    monkeypatch.setenv("PARSE_DESKTOP", "1")
    before = dict(BASE_CORS)
    dr.resolve_cors_headers(BASE_CORS, origin="http://127.0.0.1:5173")
    assert BASE_CORS == before  # input mapping untouched
