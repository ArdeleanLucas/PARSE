import io
import pathlib
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _RecordingWfile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, *, path: str = "/api/lexeme/search", body=None, headers=None, rfile=None):
        self.path = path
        self._body = {} if body is None else body
        self.headers = headers or {}
        self.rfile = rfile or io.BytesIO()
        self.sent_json = []
        self.response_statuses = []
        self.response_headers = []
        self.ended = 0
        self.wfile = _RecordingWfile()

    def _read_json_body(self, required: bool = True):
        return self._body

    def _expect_object(self, value, label: str):
        return value

    def _send_json(self, status, payload):
        self.sent_json.append((status, payload))

    def send_response(self, status):
        self.response_statuses.append(status)

    def send_header(self, key, value):
        self.response_headers.append((key, value))

    def end_headers(self):
        self.ended += 1


class _DispatchHarness(server.RangeRequestHandler):
    def __init__(self):
        self.calls = []

    def _api_post_lexeme_note(self):
        self.calls.append("lexeme-note")

    def _api_post_lexeme_notes_import(self):
        self.calls.append("lexeme-notes-import")

    def _api_get_spectrogram(self):
        self.calls.append("spectrogram")

    def _api_get_lexeme_search(self):
        self.calls.append("lexeme-search")


class _DummyLexemeNoteHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class _DummyMediaSearchHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message



def test_api_post_lexeme_note_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness(body={"speaker": "Fail01", "concept_id": "1"})
    observed = {}

    def fake_builder(data, **kwargs):
        observed["data"] = data
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"success": True, "lexeme_notes": {}})

    monkeypatch.setattr(server, "_app_build_post_lexeme_note_response", fake_builder, raising=False)

    handler._api_post_lexeme_note()

    assert handler.sent_json == [(HTTPStatus.OK, {"success": True, "lexeme_notes": {}})]
    assert observed["data"] == {"speaker": "Fail01", "concept_id": "1"}
    assert observed["normalize_speaker_id"] == server._normalize_speaker_id
    assert observed["normalize_concept_id"] == server._normalize_concept_id
    assert observed["enrichments_path"] == server._enrichments_path()



def test_api_post_lexeme_notes_import_wrapper_maps_helper_errors(monkeypatch) -> None:
    handler = _HandlerHarness(headers={"Content-Type": "multipart/form-data", "Content-Length": "0"}, rfile=io.BytesIO())

    def fake_builder(**kwargs):
        raise _DummyLexemeNoteHandlerError(HTTPStatus.BAD_REQUEST, "csv file is required (field name: csv)")

    monkeypatch.setattr(server, "_app_LexemeNoteHandlerError", _DummyLexemeNoteHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_post_lexeme_notes_import_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_lexeme_notes_import()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "csv file is required (field name: csv)"



def test_api_get_spectrogram_wrapper_writes_binary_response(monkeypatch) -> None:
    handler = _HandlerHarness(path="/api/spectrogram?speaker=Fail01&start=0&end=1")

    def fake_builder(raw_path, **kwargs):
        assert raw_path == handler.path
        return SimpleNamespace(
            status=HTTPStatus.OK,
            body=b"PNGDATA",
            headers={
                "Content-Type": "image/png",
                "Content-Length": "7",
                "Cache-Control": "public, max-age=3600",
            },
        )

    monkeypatch.setitem(sys.modules, "spectrograms", SimpleNamespace())
    monkeypatch.setattr(server, "_app_build_get_spectrogram_response", fake_builder, raising=False)

    handler._api_get_spectrogram()

    assert handler.response_statuses == [HTTPStatus.OK]
    assert handler.response_headers == [
        ("Content-Type", "image/png"),
        ("Content-Length", "7"),
        ("Cache-Control", "public, max-age=3600"),
    ]
    assert handler.ended == 1
    assert handler.wfile.chunks == [b"PNGDATA"]



def test_api_get_lexeme_search_wrapper_maps_helper_errors(monkeypatch) -> None:
    handler = _HandlerHarness(path="/api/lexeme/search?speaker=Fail01")

    def fake_builder(raw_path, **kwargs):
        raise _DummyMediaSearchHandlerError(HTTPStatus.BAD_REQUEST, "variants is required (comma or space separated)")

    monkeypatch.setattr(server, "_app_MediaSearchHandlerError", _DummyMediaSearchHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_get_lexeme_search_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_get_lexeme_search()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "variants is required (comma or space separated)"



def test_dispatch_routes_preserve_lexeme_media_search_endpoints() -> None:
    handler = _DispatchHarness()

    handler._dispatch_api_get("/api/spectrogram")
    handler._dispatch_api_get("/api/lexeme/search")
    handler._dispatch_api_post("/api/lexeme-notes")
    handler._dispatch_api_post("/api/lexeme-notes/import")

    assert handler.calls == [
        "spectrogram",
        "lexeme-search",
        "lexeme-note",
        "lexeme-notes-import",
    ]
