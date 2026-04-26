import pathlib
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ai.openai_auth as openai_auth
import server


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, path: str, body=None):
        self.path = path
        self._body = {} if body is None else body
        self.sent = []

    def _read_json_body(self, required: bool = True):
        return self._body

    def _send_json(self, status, payload):
        self.sent.append((status, payload))


class _DummyAuthHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message



def _fail_if_called(name: str):
    def _raiser(*args, **kwargs):
        raise AssertionError(f"{name} should be delegated through auth_handlers")

    return _raiser



def test_api_auth_key_wrapper_delegates_to_helper_and_sends_response(monkeypatch) -> None:
    handler = _HandlerHarness("/api/auth/key", {"key": "xai-key"})
    observed = {}

    def fake_builder(data, *, save_api_key, reset_chat_runtime, get_auth_status):
        observed["data"] = data
        observed["save_api_key"] = save_api_key
        observed["reset_chat_runtime"] = reset_chat_runtime
        observed["get_auth_status"] = get_auth_status
        return SimpleNamespace(status=HTTPStatus.ACCEPTED, payload={"ok": True})

    monkeypatch.setattr(server, "_app_build_auth_key_response", fake_builder, raising=False)
    monkeypatch.setattr(openai_auth, "save_api_key", _fail_if_called("save_api_key"))
    monkeypatch.setattr(server, "_reset_chat_runtime_after_auth_key_save", _fail_if_called("_reset_chat_runtime_after_auth_key_save"))
    monkeypatch.setattr(openai_auth, "get_auth_status", _fail_if_called("get_auth_status"))

    handler._api_auth_key()

    assert handler.sent == [(HTTPStatus.ACCEPTED, {"ok": True})]
    assert observed["data"] == {"key": "xai-key"}
    assert callable(observed["save_api_key"])
    assert callable(observed["reset_chat_runtime"])
    assert callable(observed["get_auth_status"])



def test_api_auth_key_wrapper_maps_helper_errors_to_error_payload(monkeypatch) -> None:
    handler = _HandlerHarness("/api/auth/key", {"key": ""})

    def fake_builder(data, *, save_api_key, reset_chat_runtime, get_auth_status):
        raise _DummyAuthHandlerError(HTTPStatus.BAD_REQUEST, "key is required")

    monkeypatch.setattr(server, "_app_AuthHandlerError", _DummyAuthHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_auth_key_response", fake_builder, raising=False)
    monkeypatch.setattr(openai_auth, "save_api_key", _fail_if_called("save_api_key"))
    monkeypatch.setattr(server, "_reset_chat_runtime_after_auth_key_save", _fail_if_called("_reset_chat_runtime_after_auth_key_save"))
    monkeypatch.setattr(openai_auth, "get_auth_status", _fail_if_called("get_auth_status"))

    handler._api_auth_key()

    assert handler.sent == [(HTTPStatus.BAD_REQUEST, {"error": "key is required"})]



def test_api_auth_key_wrapper_preserves_legacy_500_for_json_body_errors(monkeypatch) -> None:
    handler = _HandlerHarness("/api/auth/key")

    def fake_read_json_body(required: bool = True):
        raise server.ApiError(HTTPStatus.BAD_REQUEST, "Invalid JSON body")

    monkeypatch.setattr(handler, "_read_json_body", fake_read_json_body)
    monkeypatch.setattr(server, "_app_build_auth_key_response", _fail_if_called("_app_build_auth_key_response"), raising=False)

    handler._api_auth_key()

    assert handler.sent == [(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Invalid JSON body"})]



def test_api_auth_status_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness("/api/auth/status")

    monkeypatch.setattr(
        server,
        "_app_build_auth_status_response",
        lambda *, get_auth_status: SimpleNamespace(status=HTTPStatus.OK, payload={"authenticated": True, "provider": "xai"}),
        raising=False,
    )
    monkeypatch.setattr(openai_auth, "get_auth_status", _fail_if_called("get_auth_status"))

    handler._api_auth_status()

    assert handler.sent == [(HTTPStatus.OK, {"authenticated": True, "provider": "xai"})]



def test_api_auth_start_wrapper_delegates_to_helper_and_maps_errors(monkeypatch) -> None:
    handler = _HandlerHarness("/api/auth/start")

    def fake_builder(*, start_device_auth):
        raise _DummyAuthHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, "device flow unavailable")

    monkeypatch.setattr(server, "_app_AuthHandlerError", _DummyAuthHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_auth_start_response", fake_builder, raising=False)
    monkeypatch.setattr(openai_auth, "start_device_auth", _fail_if_called("start_device_auth"))

    handler._api_auth_start()

    assert handler.sent == [(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "device flow unavailable"})]



def test_api_auth_poll_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness("/api/auth/poll")

    monkeypatch.setattr(
        server,
        "_app_build_auth_poll_response",
        lambda *, poll_device_auth: SimpleNamespace(status=HTTPStatus.OK, payload={"status": "pending"}),
        raising=False,
    )
    monkeypatch.setattr(openai_auth, "poll_device_auth", _fail_if_called("poll_device_auth"))

    handler._api_auth_poll()

    assert handler.sent == [(HTTPStatus.OK, {"status": "pending"})]



def test_api_auth_logout_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness("/api/auth/logout")

    monkeypatch.setattr(
        server,
        "_app_build_auth_logout_response",
        lambda *, clear_tokens: SimpleNamespace(status=HTTPStatus.OK, payload={"success": True}),
        raising=False,
    )
    monkeypatch.setattr(openai_auth, "clear_tokens", _fail_if_called("clear_tokens"))

    handler._api_auth_logout()

    assert handler.sent == [(HTTPStatus.OK, {"success": True})]
