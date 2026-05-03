import csv
import email.parser
import email.policy
import io
import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
from app.http.project_config_handlers import (
    ProjectConfigHandlerError,
    build_concepts_import_response,
    build_get_config_response,
    build_tags_import_response,
    build_update_config_response,
)


def _multipart_headers(body: bytes, boundary: str):
    hdr_text = (
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    )
    return email.parser.Parser(policy=email.policy.compat32).parsestr(hdr_text)


def _make_concepts_multipart(csv_body: str, mode: str = "") -> tuple[bytes, str]:
    boundary = "----parseboundary"
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="csv"; filename="concepts.csv"\r\n',
        b"Content-Type: text/csv\r\n\r\n",
        csv_body.encode("utf-8"),
        b"\r\n",
    ]
    if mode:
        parts += [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="mode"\r\n\r\n',
            mode.encode(),
            b"\r\n",
        ]
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def _make_tags_multipart(
    csv_body: str,
    *,
    filename: str = "custom.csv",
    tag_name: str | None = None,
    color: str | None = None,
) -> tuple[bytes, str]:
    boundary = "----parseboundary"
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="csv"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: text/csv\r\n\r\n",
        csv_body.encode("utf-8"),
        b"\r\n",
    ]
    if tag_name is not None:
        parts += [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="tagName"\r\n\r\n',
            tag_name.encode(),
            b"\r\n",
        ]
    if color is not None:
        parts += [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="color"\r\n\r\n',
            color.encode(),
            b"\r\n",
        ]
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def test_build_get_config_response_wraps_workspace_frontend_config() -> None:
    response = build_get_config_response(
        load_config=lambda: {"chat": {"enabled": True}},
        workspace_frontend_config=lambda config: {
            "project_name": "PARSE",
            "chatEnabled": config["chat"]["enabled"],
        },
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {"config": {"project_name": "PARSE", "chatEnabled": True}}


def test_build_update_config_response_deep_merges_and_writes() -> None:
    written: dict[str, object] = {}

    response = build_update_config_response(
        {"chat": {"enabled": False}, "auth": {"provider": "xai"}},
        load_config=lambda: {"chat": {"enabled": True, "history": 200}, "auth": {"method": "api_key"}},
        deep_merge_dicts=server._deep_merge_dicts,
        write_config=lambda merged: written.setdefault("config", merged),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "success": True,
        "config": {
            "chat": {"enabled": False, "history": 200},
            "auth": {"method": "api_key", "provider": "xai"},
        },
    }
    assert written["config"] == response.payload["config"]


def test_build_concepts_import_response_merges_matching_rows(tmp_path: pathlib.Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    with open(concepts_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "hair", "source_item": "", "source_survey": "", "custom_order": ""})
        writer.writerow({"id": "2", "concept_en": "forehead", "source_item": "", "source_survey": "", "custom_order": ""})

    body, boundary = _make_concepts_multipart(
        "id,concept_en,source_item,source_survey,custom_order\n1,hair,1.1,KLQ,10\n2,forehead,1.2,KLQ,20\n"
    )
    response = build_concepts_import_response(
        headers=_multipart_headers(body, boundary),
        rfile=io.BytesIO(body),
        project_root=tmp_path,
        normalize_concept_id=server._normalize_concept_id,
        upload_limit=server.ONBOARD_MAX_UPLOAD_BYTES,
    )

    with open(concepts_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows_by_id = {row["id"]: row for row in rows}

    assert response.status == HTTPStatus.OK
    assert response.payload == {"ok": True, "matched": 2, "added": 0, "total": 2, "mode": "merge"}
    assert rows_by_id["1"]["source_item"] == "1.1"
    assert rows_by_id["1"]["source_survey"] == "KLQ"
    assert rows_by_id["1"]["custom_order"] == "10"
    assert rows_by_id["2"]["source_item"] == "1.2"
    assert rows_by_id["2"]["source_survey"] == "KLQ"


def test_build_concepts_import_response_replace_mode_clears_unmatched_rows(tmp_path: pathlib.Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    with open(concepts_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "hair", "source_item": "1.1", "source_survey": "KLQ", "custom_order": "10"})
        writer.writerow({"id": "2", "concept_en": "forehead", "source_item": "1.2", "source_survey": "KLQ", "custom_order": "20"})

    body, boundary = _make_concepts_multipart("id,custom_order\n1,1\n", mode="replace")
    response = build_concepts_import_response(
        headers=_multipart_headers(body, boundary),
        rfile=io.BytesIO(body),
        project_root=tmp_path,
        normalize_concept_id=server._normalize_concept_id,
        upload_limit=server.ONBOARD_MAX_UPLOAD_BYTES,
    )

    with open(concepts_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows_by_id = {row["id"]: row for row in rows}

    assert response.payload["mode"] == "replace"
    assert rows_by_id["1"]["custom_order"] == "1"
    assert rows_by_id["1"]["source_item"] == ""
    assert rows_by_id["1"]["source_survey"] == ""
    assert rows_by_id["2"]["custom_order"] == ""
    assert rows_by_id["2"]["source_item"] == ""
    assert rows_by_id["2"]["source_survey"] == ""


def test_build_tags_import_response_defaults_tag_name_from_filename_and_writes_tag_file(tmp_path: pathlib.Path) -> None:
    with open(tmp_path / "concepts.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "hair"})
        writer.writerow({"id": "2", "concept_en": "forehead"})

    body, boundary = _make_tags_multipart("concept_en\nhair\nforehead\n", filename="oxford_85.csv")
    response = build_tags_import_response(
        headers=_multipart_headers(body, boundary),
        rfile=io.BytesIO(body),
        project_root=tmp_path,
        normalize_concept_id=server._normalize_concept_id,
        concept_sort_key=server._concept_sort_key,
        upload_limit=server.ONBOARD_MAX_UPLOAD_BYTES,
    )

    tags = json.loads((tmp_path / "parse-tags.json").read_text("utf-8"))

    assert response.status == HTTPStatus.OK
    assert response.payload["tagName"] == "oxford_85"
    assert response.payload["tagId"] == "oxford-85"
    assert response.payload["matchedCount"] == 2
    assert tags == [
        {
            "id": "oxford-85",
            "label": "oxford_85",
            "color": "#4461d4",
            "concepts": ["1", "2"],
        }
    ]


def test_build_tags_import_response_raises_on_all_misses(tmp_path: pathlib.Path) -> None:
    with open(tmp_path / "concepts.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "hair"})

    body, boundary = _make_tags_multipart("concept_en\nsky\ncloud\n")
    with pytest.raises(ProjectConfigHandlerError) as exc_info:
        build_tags_import_response(
            headers=_multipart_headers(body, boundary),
            rfile=io.BytesIO(body),
            project_root=tmp_path,
            normalize_concept_id=server._normalize_concept_id,
            concept_sort_key=server._concept_sort_key,
            upload_limit=server.ONBOARD_MAX_UPLOAD_BYTES,
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "No rows matched any existing concept by id or concept_en. Import concepts first."
