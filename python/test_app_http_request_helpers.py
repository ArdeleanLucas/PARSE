import io
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.http.request_helpers import JsonBodyError, path_parts, read_json_body, request_path, request_query_params


def test_request_path_falls_back_to_root_when_url_has_no_path() -> None:
    assert request_path("?speaker=Fail01") == "/"



def test_request_query_params_keeps_blank_and_repeated_values() -> None:
    assert request_query_params("/api/export?format=&speaker=Fail01&speaker=Fail02") == {
        "format": [""],
        "speaker": ["Fail01", "Fail02"],
    }



def test_path_parts_url_decodes_each_segment() -> None:
    assert path_parts("/api/annotations/Fail%2001/%C3%A7ase") == ["api", "annotations", "Fail 01", "çase"]



def test_read_json_body_rejects_missing_required_body() -> None:
    with pytest.raises(JsonBodyError, match="JSON request body is required"):
        read_json_body({}, io.BytesIO(b""))



def test_read_json_body_returns_empty_dict_for_optional_empty_body() -> None:
    assert read_json_body({}, io.BytesIO(b""), required=False) == {}



def test_read_json_body_rejects_invalid_content_length_header() -> None:
    with pytest.raises(JsonBodyError, match="Invalid Content-Length header"):
        read_json_body({"Content-Length": "abc"}, io.BytesIO(b"{}"))



def test_read_json_body_rejects_invalid_json_bytes() -> None:
    with pytest.raises(JsonBodyError, match="Invalid JSON body"):
        read_json_body({"Content-Length": "3"}, io.BytesIO(b"{"))



def test_read_json_body_decodes_utf8_json_payload() -> None:
    body = '{"word":"čî"}'.encode("utf-8")
    payload = read_json_body({"Content-Length": str(len(body))}, io.BytesIO(body))

    assert payload == {"word": "čî"}
