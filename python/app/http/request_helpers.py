"""Request parsing helpers for the PARSE HTTP server."""

from __future__ import annotations

import json
from typing import Any, BinaryIO, Dict, List, Mapping
from urllib.parse import parse_qs, unquote, urlparse


class JsonBodyError(ValueError):
    """Raised when an HTTP request body cannot be parsed as valid JSON."""



def request_path(raw_path: str) -> str:
    return urlparse(raw_path).path or "/"



def request_query_params(raw_path: str) -> Dict[str, List[str]]:
    return parse_qs(urlparse(raw_path).query, keep_blank_values=True)



def path_parts(request_path_value: str) -> List[str]:
    return [unquote(part) for part in request_path_value.strip("/").split("/") if part]



def read_json_body(headers: Mapping[str, str], body_stream: BinaryIO, required: bool = True) -> Any:
    raw_length = headers.get("Content-Length", "")
    if not raw_length:
        if required:
            raise JsonBodyError("JSON request body is required")
        return {}

    try:
        content_length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise JsonBodyError("Invalid Content-Length header") from exc

    if content_length < 0:
        raise JsonBodyError("Invalid Content-Length header")

    if content_length == 0:
        if required:
            raise JsonBodyError("JSON request body is required")
        return {}

    raw_body = body_stream.read(content_length)
    if not raw_body:
        if required:
            raise JsonBodyError("JSON request body is required")
        return {}

    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JsonBodyError("Invalid JSON body") from exc
