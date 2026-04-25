"""JSON response helpers for the PARSE HTTP server."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any, Mapping, Protocol


class BinaryWriter(Protocol):
    def write(self, data: bytes) -> Any:
        ...


class JsonResponseWriter(Protocol):
    wfile: BinaryWriter

    def send_response(self, status: HTTPStatus) -> None:
        ...

    def send_header(self, key: str, value: str) -> None:
        ...

    def end_headers(self) -> None:
        ...



def encode_json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")



def send_json_response(writer: JsonResponseWriter, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
    encoded = encode_json_body(payload)
    writer.send_response(status)
    writer.send_header("Content-Type", "application/json; charset=utf-8")
    writer.send_header("Content-Length", str(len(encoded)))
    writer.end_headers()
    try:
        writer.wfile.write(encoded)
    except BrokenPipeError:
        pass



def send_json_error_response(writer: JsonResponseWriter, status: HTTPStatus, message: str) -> None:
    send_json_response(writer, status, {"error": str(message)})
