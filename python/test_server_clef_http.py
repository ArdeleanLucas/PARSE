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
        self.sent_json = []

    def _read_json_body(self, required: bool = True):
        return self._body

    def _expect_object(self, value, label: str):
        return value

    def _send_json(self, status, payload):
        self.sent_json.append((status, payload))


class _DummyClefHttpHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def test_api_get_contact_lexeme_coverage_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"languages": {"ar": {}}})

    monkeypatch.setattr(server, "_app_build_get_contact_lexeme_coverage_response", fake_builder, raising=False)

    handler._api_get_contact_lexeme_coverage()

    assert handler.sent_json == [(HTTPStatus.OK, {"languages": {"ar": {}}})]
    assert observed["config_path"] == server._sil_config_path()
    assert observed["project_root"] == server._project_root()
    assert observed["load_sil_config_safe"] == server._load_sil_config_safe


def test_api_get_clef_config_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"configured": False})

    monkeypatch.setattr(server, "_app_build_get_clef_config_response", fake_builder, raising=False)

    handler._api_get_clef_config()

    assert handler.sent_json == [(HTTPStatus.OK, {"configured": False})]
    assert observed["config_path"] == server._sil_config_path()
    assert observed["project_root"] == server._project_root()
    assert observed["load_sil_config_safe"] == server._load_sil_config_safe


def test_api_post_clef_config_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness({"primary_contact_languages": ["ar"], "languages": []})
    observed = {}

    def fake_builder(body, **kwargs):
        observed["body"] = body
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"success": True})

    monkeypatch.setattr(server, "_app_build_post_clef_config_response", fake_builder, raising=False)

    handler._api_post_clef_config()

    assert handler.sent_json == [(HTTPStatus.OK, {"success": True})]
    assert observed["body"] == {"primary_contact_languages": ["ar"], "languages": []}
    assert observed["config_path"] == server._sil_config_path()
    assert observed["load_sil_config_safe"] == server._load_sil_config_safe
    assert observed["write_sil_config"] == server._write_sil_config
    assert callable(observed["now_factory"])


def test_api_post_clef_config_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness({"primary_contact_languages": [], "languages": []})

    def fake_builder(body, **kwargs):
        raise _DummyClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "bad config")

    monkeypatch.setattr(server, "_app_ClefHttpHandlerError", _DummyClefHttpHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_post_clef_config_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_clef_config()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "bad config"


def test_api_post_clef_form_selections_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness({"concept_en": "water", "lang_code": "ar", "forms": []})
    observed = {}

    def fake_builder(body, **kwargs):
        observed["body"] = body
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"success": True})

    monkeypatch.setattr(server, "_app_build_post_clef_form_selections_response", fake_builder, raising=False)

    handler._api_post_clef_form_selections()

    assert handler.sent_json == [(HTTPStatus.OK, {"success": True})]
    assert observed["body"] == {"concept_en": "water", "lang_code": "ar", "forms": []}
    assert observed["config_path"] == server._sil_config_path()
    assert observed["load_sil_config_safe"] == server._load_sil_config_safe
    assert observed["write_sil_config"] == server._write_sil_config


def test_api_get_clef_catalog_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"languages": []})

    monkeypatch.setattr(server, "_app_build_get_clef_catalog_response", fake_builder, raising=False)

    handler._api_get_clef_catalog()

    assert handler.sent_json == [(HTTPStatus.OK, {"languages": []})]
    assert observed["project_root"] == server._project_root()
    assert isinstance(observed["sil_catalog"], list)


def test_api_get_clef_providers_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"providers": []})

    monkeypatch.setattr(server, "_app_build_get_clef_providers_response", fake_builder, raising=False)

    handler._api_get_clef_providers()

    assert handler.sent_json == [(HTTPStatus.OK, {"providers": []})]
    assert isinstance(observed["provider_priority"], list)


def test_api_get_clef_sources_report_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"languages": [], "providers": []})

    monkeypatch.setattr(server, "_app_build_get_clef_sources_report_response", fake_builder, raising=False)

    handler._api_get_clef_sources_report()

    assert handler.sent_json == [(HTTPStatus.OK, {"languages": [], "providers": []})]
    assert observed["config_path"] == server._sil_config_path()
    assert observed["project_root"] == server._project_root()
    assert observed["load_sil_config_safe"] == server._load_sil_config_safe
    assert callable(observed["iter_forms_with_sources"])
    assert callable(observed["get_citations"])
    assert isinstance(observed["citation_display_order"], tuple)
    assert callable(observed["now_factory"])


def test_api_get_contact_lexeme_coverage_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness()

    def fake_builder(**kwargs):
        raise _DummyClefHttpHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, "coverage failed")

    monkeypatch.setattr(server, "_app_ClefHttpHandlerError", _DummyClefHttpHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_get_contact_lexeme_coverage_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_get_contact_lexeme_coverage()

    assert exc_info.value.status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.message == "coverage failed"
