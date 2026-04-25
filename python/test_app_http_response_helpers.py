import io
import json
import pathlib
import sys
from http import HTTPStatus

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.http.response_helpers import encode_json_body, send_json_error_response, send_json_response


class _RecordingWriter:
    def __init__(self) -> None:
        self.statuses: list[HTTPStatus] = []
        self.headers: list[tuple[str, str]] = []
        self.events: list[str] = []
        self.wfile = io.BytesIO()

    def send_response(self, status: HTTPStatus) -> None:
        self.statuses.append(status)
        self.events.append("send_response")

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))
        self.events.append(f"send_header:{key}")

    def end_headers(self) -> None:
        self.events.append("end_headers")


class _BrokenPipeWriter(_RecordingWriter):
    class _Sink:
        def write(self, data: bytes) -> None:
            raise BrokenPipeError()

    def __init__(self) -> None:
        super().__init__()
        self.wfile = self._Sink()



def test_encode_json_body_preserves_utf8_characters() -> None:
    encoded = encode_json_body({"word": "čî"})

    assert encoded.decode("utf-8") == json.dumps({"word": "čî"}, ensure_ascii=False)



def test_send_json_response_sets_headers_and_body() -> None:
    writer = _RecordingWriter()

    send_json_response(writer, HTTPStatus.CREATED, {"word": "čî"})

    expected_body = json.dumps({"word": "čî"}, ensure_ascii=False).encode("utf-8")
    assert writer.statuses == [HTTPStatus.CREATED]
    assert writer.headers == [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(expected_body))),
    ]
    assert writer.events == ["send_response", "send_header:Content-Type", "send_header:Content-Length", "end_headers"]
    assert writer.wfile.getvalue() == expected_body



def test_send_json_response_ignores_broken_pipe_errors() -> None:
    writer = _BrokenPipeWriter()

    send_json_response(writer, HTTPStatus.OK, {"ok": True})

    assert writer.statuses == [HTTPStatus.OK]



def test_send_json_error_response_wraps_message_in_error_payload() -> None:
    writer = _RecordingWriter()

    send_json_error_response(writer, HTTPStatus.BAD_REQUEST, "Invalid JSON body")

    assert writer.statuses == [HTTPStatus.BAD_REQUEST]
    assert json.loads(writer.wfile.getvalue().decode("utf-8")) == {"error": "Invalid JSON body"}
