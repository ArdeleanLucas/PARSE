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
from app.http.job_observability_handlers import JsonResponseSpec
from app.http.lexeme_note_handlers import (
    LexemeNoteHandlerError,
    build_post_lexeme_note_response,
    build_post_lexeme_notes_import_response,
)


def _multipart_headers(body: bytes, boundary: str):
    hdr_text = (
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    )
    return email.parser.Parser(policy=email.policy.compat32).parsestr(hdr_text)


def _make_import_multipart(*, speaker_id: str | None = "Fail01", csv_bytes: bytes | None = None, filename: str = "comments.csv") -> tuple[bytes, str]:
    boundary = "----parselexemenotes"
    parts: list[bytes] = []
    if speaker_id is not None:
        parts.extend([
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="speaker_id"\r\n\r\n',
            speaker_id.encode("utf-8"),
            b"\r\n",
        ])
    if csv_bytes is not None:
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="csv"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: text/csv\r\n\r\n",
            csv_bytes,
            b"\r\n",
        ])
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def test_build_post_lexeme_note_response_writes_note_and_delete_semantics(tmp_path: pathlib.Path) -> None:
    enrichments_path = tmp_path / "parse-enrichments.json"

    response = build_post_lexeme_note_response(
        {"speaker": " Fail01 ", "concept_id": "1", "user_note": "keep vowel length"},
        normalize_speaker_id=server._normalize_speaker_id,
        normalize_concept_id=server._normalize_concept_id,
        read_json_file=server._read_json_file,
        default_enrichments_payload=server._default_enrichments_payload,
        write_json_file=server._write_json_file,
        enrichments_path=enrichments_path,
        utc_now_iso=lambda: "2026-04-26T14:30:00Z",
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "success": True,
            "lexeme_notes": {
                "Fail01": {
                    "1": {
                        "user_note": "keep vowel length",
                        "updated_at": "2026-04-26T14:30:00Z",
                    }
                }
            },
        },
    )

    delete_response = build_post_lexeme_note_response(
        {"speaker": "Fail01", "concept_id": "1", "delete": True},
        normalize_speaker_id=server._normalize_speaker_id,
        normalize_concept_id=server._normalize_concept_id,
        read_json_file=server._read_json_file,
        default_enrichments_payload=server._default_enrichments_payload,
        write_json_file=server._write_json_file,
        enrichments_path=enrichments_path,
        utc_now_iso=lambda: "unused",
    )

    assert delete_response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"success": True, "lexeme_notes": {}},
    )
    saved_payload = json.loads(enrichments_path.read_text(encoding="utf-8"))
    assert saved_payload.get("lexeme_notes") == {}


def test_build_post_lexeme_note_response_requires_speaker_and_concept_id(tmp_path: pathlib.Path) -> None:
    with pytest.raises(LexemeNoteHandlerError) as exc_info:
        build_post_lexeme_note_response(
            {"speaker": "", "concept_id": ""},
            normalize_speaker_id=server._normalize_speaker_id,
            normalize_concept_id=server._normalize_concept_id,
            read_json_file=server._read_json_file,
            default_enrichments_payload=server._default_enrichments_payload,
            write_json_file=server._write_json_file,
            enrichments_path=tmp_path / "parse-enrichments.json",
            utc_now_iso=lambda: "unused",
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "speaker and concept_id are required"


def test_build_post_lexeme_notes_import_response_imports_notes_and_matches_intervals(tmp_path: pathlib.Path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    (tmp_path / "concepts.csv").write_text(
        "id,concept_en,survey_item\n1,hair,SK_1\n",
        encoding="utf-8",
    )
    annotation_path = annotations_dir / "Fail01.parse.json"
    annotation_path.write_text(
        json.dumps(
            {
                "tiers": {
                    "concept": {
                        "intervals": [
                            {"text": "1", "start": 0.0, "end": 0.5},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    csv_text = "Name\tStart\tDuration\n(1)- hair - keep nasalization\t0:00.000\t0:00.050\n"
    body, boundary = _make_import_multipart(csv_bytes=csv_text.encode("utf-8"))

    response = build_post_lexeme_notes_import_response(
        headers=_multipart_headers(body, boundary),
        rfile=io.BytesIO(body),
        project_root=tmp_path,
        upload_limit=server.ONBOARD_MAX_UPLOAD_BYTES,
        normalize_speaker_id=server._normalize_speaker_id,
        normalize_concept_id=server._normalize_concept_id,
        annotation_read_path_for_speaker=lambda speaker: annotation_path,
        read_json_any_file=server._read_json_any_file,
        normalize_annotation_record=server._normalize_annotation_record,
        read_json_file=server._read_json_file,
        default_enrichments_payload=server._default_enrichments_payload,
        write_json_file=server._write_json_file,
        enrichments_path=tmp_path / "parse-enrichments.json",
        utc_now_iso=lambda: "2026-04-26T14:31:00Z",
    )

    assert response == JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "success": True,
            "speaker": "Fail01",
            "total_rows": 1,
            "imported": 1,
            "matched": 1,
            "lexeme_notes": {
                "Fail01": {
                    "1": {
                        "import_note": "keep nasalization",
                        "import_raw": "(1)- hair - keep nasalization",
                        "updated_at": "2026-04-26T14:31:00Z",
                    }
                }
            },
        },
    )


def test_build_post_lexeme_notes_import_response_requires_csv_field(tmp_path: pathlib.Path) -> None:
    body, boundary = _make_import_multipart(csv_bytes=None)

    with pytest.raises(LexemeNoteHandlerError) as exc_info:
        build_post_lexeme_notes_import_response(
            headers=_multipart_headers(body, boundary),
            rfile=io.BytesIO(body),
            project_root=tmp_path,
            upload_limit=server.ONBOARD_MAX_UPLOAD_BYTES,
            normalize_speaker_id=server._normalize_speaker_id,
            normalize_concept_id=server._normalize_concept_id,
            annotation_read_path_for_speaker=lambda speaker: tmp_path / "annotations" / f"{speaker}.parse.json",
            read_json_any_file=server._read_json_any_file,
            normalize_annotation_record=server._normalize_annotation_record,
            read_json_file=server._read_json_file,
            default_enrichments_payload=server._default_enrichments_payload,
            write_json_file=server._write_json_file,
            enrichments_path=tmp_path / "parse-enrichments.json",
            utc_now_iso=lambda: "unused",
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "csv file is required (field name: csv)"


def test_build_post_lexeme_notes_import_response_rejects_bad_encoding(tmp_path: pathlib.Path) -> None:
    body, boundary = _make_import_multipart(csv_bytes=b"\xff\xfe\x00")

    with pytest.raises(LexemeNoteHandlerError) as exc_info:
        build_post_lexeme_notes_import_response(
            headers=_multipart_headers(body, boundary),
            rfile=io.BytesIO(body),
            project_root=tmp_path,
            upload_limit=server.ONBOARD_MAX_UPLOAD_BYTES,
            normalize_speaker_id=server._normalize_speaker_id,
            normalize_concept_id=server._normalize_concept_id,
            annotation_read_path_for_speaker=lambda speaker: tmp_path / "annotations" / f"{speaker}.parse.json",
            read_json_any_file=server._read_json_any_file,
            normalize_annotation_record=server._normalize_annotation_record,
            read_json_file=server._read_json_file,
            default_enrichments_payload=server._default_enrichments_payload,
            write_json_file=server._write_json_file,
            enrichments_path=tmp_path / "parse-enrichments.json",
            utc_now_iso=lambda: "unused",
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message.startswith("csv must be UTF-8:")
