import pathlib
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _BinaryBuffer:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def payload(self) -> bytes:
        return b"".join(self.chunks)


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, body=None):
        self._body = {} if body is None else body
        self.sent_json = []
        self.response_codes = []
        self.headers_sent = []
        self.ended = 0
        self.wfile = _BinaryBuffer()

    def _read_json_body(self, required: bool = True):
        return self._body

    def _expect_object(self, value, label: str):
        return value

    def _send_json(self, status, payload):
        self.sent_json.append((status, payload))

    def send_response(self, code):
        self.response_codes.append(code)

    def send_header(self, key, value):
        self.headers_sent.append((key, value))

    def end_headers(self):
        self.ended += 1


class _DummyProjectArtifactHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message



def test_api_get_tags_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(*, project_root):
        observed["project_root"] = project_root
        return SimpleNamespace(status=HTTPStatus.OK, payload={"tags": [{"id": "x"}]})

    monkeypatch.setattr(
        server,
        "_app_build_get_tags_response",
        fake_builder,
        raising=False,
    )

    handler._api_get_tags()

    assert handler.sent_json == [(HTTPStatus.OK, {"tags": [{"id": "x"}]})]
    assert observed["project_root"] == server._project_root()



def test_api_get_tags_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness()

    def fake_builder(*, project_root):
        raise _DummyProjectArtifactHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, "boom")

    monkeypatch.setattr(server, "_app_ProjectArtifactHandlerError", _DummyProjectArtifactHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_get_tags_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_get_tags()

    assert exc_info.value.status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.message == "boom"



def test_api_post_tags_merge_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness({"tags": [{"id": "confirmed"}]})
    observed = {}

    def fake_builder(data, *, project_root):
        observed["data"] = data
        observed["project_root"] = project_root
        return SimpleNamespace(status=HTTPStatus.OK, payload={"ok": True, "tagCount": 1})

    monkeypatch.setattr(server, "_app_build_post_tags_merge_response", fake_builder, raising=False)

    handler._api_post_tags_merge()

    assert handler.sent_json == [(HTTPStatus.OK, {"ok": True, "tagCount": 1})]
    assert observed["data"] == {"tags": [{"id": "confirmed"}]}
    assert observed["project_root"] == server._project_root()



def test_api_post_tags_merge_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness({"tags": "bad"})

    def fake_builder(data, *, project_root):
        raise _DummyProjectArtifactHandlerError(HTTPStatus.BAD_REQUEST, "tags must be an array")

    monkeypatch.setattr(server, "_app_ProjectArtifactHandlerError", _DummyProjectArtifactHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_post_tags_merge_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_tags_merge()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "tags must be an array"



def test_api_get_export_lingpy_wrapper_delegates_binary_response(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            status=HTTPStatus.OK,
            content_type="text/tab-separated-values; charset=utf-8",
            content_disposition='attachment; filename="parse-wordlist.tsv"',
            body=b"tsv-body",
        )

    monkeypatch.setattr(
        server,
        "_app_build_get_export_lingpy_response",
        fake_builder,
        raising=False,
    )

    handler._api_get_export_lingpy()

    assert observed["export_wordlist_tsv"] == server.cognate_compute_module.export_wordlist_tsv
    assert observed["enrichments_path"] == server._enrichments_path()
    assert observed["annotations_dir"] == server._project_root() / "annotations"
    assert handler.response_codes == [HTTPStatus.OK]
    assert ("Content-Type", "text/tab-separated-values; charset=utf-8") in handler.headers_sent
    assert ("Content-Disposition", 'attachment; filename="parse-wordlist.tsv"') in handler.headers_sent
    assert ("Content-Length", str(len(b"tsv-body"))) in handler.headers_sent
    assert handler.ended == 1
    assert handler.wfile.payload() == b"tsv-body"



def test_api_get_export_nexus_wrapper_delegates_binary_response(monkeypatch) -> None:
    handler = _HandlerHarness()
    observed = {}

    def fake_builder(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            status=HTTPStatus.OK,
            content_type="text/plain; charset=utf-8",
            content_disposition='attachment; filename="parse-cognates.nex"',
            body=b"#NEXUS\n",
        )

    monkeypatch.setattr(
        server,
        "_app_build_get_export_nexus_response",
        fake_builder,
        raising=False,
    )

    handler._api_get_export_nexus()

    assert observed["enrichments_path"] == server._enrichments_path()
    assert observed["project_json_path"] == server._project_json_path()
    assert observed["read_json_file"] == server._read_json_file
    assert observed["default_enrichments_payload"] == server._default_enrichments_payload
    assert observed["concept_sort_key"] == server._concept_sort_key
    assert handler.response_codes == [HTTPStatus.OK]
    assert ("Content-Type", "text/plain; charset=utf-8") in handler.headers_sent
    assert ("Content-Disposition", 'attachment; filename="parse-cognates.nex"') in handler.headers_sent
    assert ("Content-Length", str(len(b"#NEXUS\n"))) in handler.headers_sent
    assert handler.ended == 1
    assert handler.wfile.payload() == b"#NEXUS\n"
