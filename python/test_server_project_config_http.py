import pathlib
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, body=None):
        self._body = {} if body is None else body
        self.sent = []
        self.headers = {}
        self.rfile = None

    def _read_json_body(self, required: bool = True):
        return self._body

    def _expect_object(self, value, label: str):
        return value

    def _send_json(self, status, payload):
        self.sent.append((status, payload))


class _DummyProjectConfigHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message



def _fail_if_called(name: str):
    def _raiser(*args, **kwargs):
        raise AssertionError(f"{name} should be delegated through project_config_handlers")

    return _raiser



def test_api_get_config_wrapper_delegates_to_helper_and_sends_response(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(*, load_config, workspace_frontend_config):
        observed["load_config"] = load_config
        observed["workspace_frontend_config"] = workspace_frontend_config
        return SimpleNamespace(status=HTTPStatus.OK, payload={"config": {"project_name": "PARSE"}})

    monkeypatch.setattr(server, "_app_build_get_config_response", fake_builder, raising=False)
    monkeypatch.setattr(server, "load_ai_config", _fail_if_called("load_ai_config"))
    monkeypatch.setattr(server, "_workspace_frontend_config", _fail_if_called("_workspace_frontend_config"))

    handler._api_get_config()

    assert handler.sent == [(HTTPStatus.OK, {"config": {"project_name": "PARSE"}})]
    assert callable(observed["load_config"])
    assert callable(observed["workspace_frontend_config"])



def test_api_update_config_wrapper_delegates_to_helper_and_sends_response(monkeypatch) -> None:
    handler = _HandlerHarness({"chat": {"enabled": False}})
    observed = {}

    def fake_builder(body, *, load_config, deep_merge_dicts, write_config):
        observed["body"] = body
        observed["load_config"] = load_config
        observed["deep_merge_dicts"] = deep_merge_dicts
        observed["write_config"] = write_config
        return SimpleNamespace(status=HTTPStatus.OK, payload={"success": True, "config": {"chat": {"enabled": False}}})

    monkeypatch.setattr(server, "_app_build_update_config_response", fake_builder, raising=False)
    monkeypatch.setattr(server, "load_ai_config", _fail_if_called("load_ai_config"))
    monkeypatch.setattr(server, "_deep_merge_dicts", _fail_if_called("_deep_merge_dicts"))
    monkeypatch.setattr(server, "_write_json_file", _fail_if_called("_write_json_file"))

    handler._api_update_config()

    assert handler.sent == [(HTTPStatus.OK, {"success": True, "config": {"chat": {"enabled": False}}})]
    assert observed["body"] == {"chat": {"enabled": False}}
    assert callable(observed["load_config"])
    assert callable(observed["deep_merge_dicts"])
    assert callable(observed["write_config"])



def test_api_update_config_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness({"chat": {}})

    def fake_builder(body, *, load_config, deep_merge_dicts, write_config):
        raise _DummyProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "bad config patch")

    monkeypatch.setattr(server, "_app_ProjectConfigHandlerError", _DummyProjectConfigHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_update_config_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_update_config()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "bad config patch"



def test_api_post_concepts_import_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness()
    handler.headers = {"Content-Type": "multipart/form-data"}

    def fake_builder(**kwargs):
        raise _DummyProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "csv is empty")

    monkeypatch.setattr(server, "_app_ProjectConfigHandlerError", _DummyProjectConfigHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_concepts_import_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_concepts_import()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "csv is empty"



def test_api_post_tags_import_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness()
    handler.headers = {"Content-Type": "multipart/form-data"}

    def fake_builder(**kwargs):
        raise _DummyProjectConfigHandlerError(HTTPStatus.BAD_REQUEST, "No rows matched any existing concept by id or concept_en. Import concepts first.")

    monkeypatch.setattr(server, "_app_ProjectConfigHandlerError", _DummyProjectConfigHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_tags_import_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_tags_import()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "No rows matched any existing concept by id or concept_en. Import concepts first."
