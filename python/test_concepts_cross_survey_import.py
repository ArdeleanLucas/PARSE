"""Tests for cross-survey concept linking during /api/concepts/import.

The new import-time auto-linking behavior is specified in
docs/cross-survey-concept-linking-plan.md sections 3 and 4a (PR #319).

Key invariants:
- Allocating a new concept_id for a row whose normalized gloss already exists in
  concepts.csv is forbidden. The row's (survey_id, source_item) is added to the
  existing concept's concept_survey_links sidecar instead.
- The canonical key strips the KLQ ``(N.M)- `` prefix and a trailing single
  uppercase variant suffix, casefolds, and collapses whitespace. Parentheticals
  and comma-separated alternatives stay strict.
- Variant siblings (``elbow A`` vs ``elbow B``) keep distinct concept_ids in
  concepts.csv even though their canonical keys are equal: the existing
  variant-handling logic (python/concepts_io.py) is the system of record for
  splits. The matcher only uses the canonical key to discover an existing
  concept to link a foreign-survey row into; it does not collapse variants.
- The response payload gains ``linked``, ``survey_counts[*].linked_count``, and
  ``survey_counts[*].created_count`` (additive — existing keys preserved).
"""

from __future__ import annotations

import csv
import email.parser
import email.policy
import io
import json
import pathlib
import sys
from http import HTTPStatus

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402
from app.http.project_config_handlers import build_concepts_import_response  # noqa: E402


def _multipart_headers(body: bytes, boundary: str):
    hdr_text = (
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    )
    return email.parser.Parser(policy=email.policy.compat32).parsestr(hdr_text)


def _make_multipart(csv_body: str, mode: str = "") -> tuple[bytes, str]:
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


def _seed_concepts(tmp_path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path = tmp_path / "concepts.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in writer.fieldnames})


def _read_concepts(tmp_path: pathlib.Path) -> list[dict[str, str]]:
    with open(tmp_path / "concepts.csv", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_overlap(tmp_path: pathlib.Path) -> dict:
    path = tmp_path / "survey-overlap.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def _invoke(tmp_path: pathlib.Path, csv_body: str, mode: str = ""):
    body, boundary = _make_multipart(csv_body, mode=mode)
    return build_concepts_import_response(
        headers=_multipart_headers(body, boundary),
        rfile=io.BytesIO(body),
        project_root=tmp_path,
        normalize_concept_id=server._normalize_concept_id,
        upload_limit=server.ONBOARD_MAX_UPLOAD_BYTES,
    )


def test_import_links_normalized_gloss_match_into_existing_concept(tmp_path):
    """JBIL ``nose`` row should auto-link to KLQ ``(1.5)- nose`` via sidecar."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "nose", "source_item": "1.5", "source_survey": "klq"},
            {"id": "2", "concept_en": "elbow", "source_item": "1.7", "source_survey": "klq"},
        ],
    )

    upload = (
        "id,concept_en,source_item,source_survey\n"
        ",nose,34,jbil\n"
        ",elbow,43,jbil\n"
    )
    response = _invoke(tmp_path, upload)

    assert response.status == HTTPStatus.OK
    payload = response.payload
    assert payload["ok"] is True
    assert payload["added"] == 0
    assert payload["linked"] == 2
    rows = _read_concepts(tmp_path)
    assert {r["id"] for r in rows} == {"1", "2"}

    overlap = _read_overlap(tmp_path)
    links = overlap["concept_survey_links"]
    assert links["1"]["jbil"] == "34"
    assert links["2"]["jbil"] == "43"

    counts = payload["survey_counts"]
    assert counts["jbil"]["linked_count"] == 2
    assert counts["jbil"]["created_count"] == 0


def test_import_strips_klq_prefix_and_trailing_variant_when_matching(tmp_path):
    """``(1.7)- elbow B`` and ``elbow A`` should both find the existing ``elbow`` row."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "elbow", "source_item": "43", "source_survey": "jbil"},
        ],
    )
    upload = (
        "id,concept_en,source_item,source_survey\n"
        ",(1.7)- elbow A,1.7,klq\n"
        ",(1.7)- elbow B,1.7,klq\n"
    )
    response = _invoke(tmp_path, upload)
    payload = response.payload

    assert payload["added"] == 0
    assert payload["linked"] == 2
    overlap = _read_overlap(tmp_path)
    assert overlap["concept_survey_links"]["1"]["klq"] == "1.7"
    assert payload["survey_counts"]["klq"]["linked_count"] == 2


def test_import_keeps_parenthetical_clarifiers_strict(tmp_path):
    """``hair (collective)`` must NOT auto-link to bare ``hair``."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "hair", "source_item": "32", "source_survey": "jbil"},
        ],
    )
    upload = (
        "id,concept_en,source_item,source_survey\n"
        ",(1.1)- hair (collective),1.1,klq\n"
    )
    response = _invoke(tmp_path, upload)
    payload = response.payload

    assert payload["added"] == 1
    assert payload["linked"] == 0
    rows = _read_concepts(tmp_path)
    # Existing import keeps the raw upload label verbatim in concepts.csv.
    assert any(r["concept_en"] == "(1.1)- hair (collective)" for r in rows)
    overlap = _read_overlap(tmp_path)
    # No sidecar link should be auto-created when a brand-new concept row was added.
    assert "klq" not in overlap.get("concept_survey_links", {}).get("1", {})


def test_import_keeps_comma_alternatives_strict(tmp_path):
    """``daughter, girl`` must NOT auto-link to bare ``daughter`` or ``girl``."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "daughter", "source_item": "60", "source_survey": "jbil"},
            {"id": "2", "concept_en": "girl", "source_item": "61", "source_survey": "jbil"},
        ],
    )
    # Properly CSV-quote the comma-bearing label.
    upload = (
        "id,concept_en,source_item,source_survey\n"
        ',"(2.7)- daughter, girl",2.7,klq\n'
    )
    response = _invoke(tmp_path, upload)
    payload = response.payload
    assert payload["added"] == 1
    assert payload["linked"] == 0


def test_import_does_not_auto_link_when_normalized_key_is_ambiguous(tmp_path):
    """Two existing concepts with the same canonical key must produce an ambiguity record.

    ``nose A`` and ``nose B`` both canonicalize to ``nose``. The upload row has
    label ``nose`` which does not exact-match either label, so the canonical-key
    fallback runs and finds two candidates. The spec forbids auto-linking in
    that case; the row is created and an ambiguity record is reported.
    """
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "nose A"},
            {"id": "2", "concept_en": "nose B"},
        ],
    )
    upload = (
        "id,concept_en,source_item,source_survey\n"
        ",nose,34,jbil\n"
    )
    response = _invoke(tmp_path, upload)
    payload = response.payload

    assert payload["linked"] == 0
    assert payload["ambiguous"]
    record = payload["ambiguous"][0]
    assert record["source_survey"] == "jbil"
    assert record["source_item"] == "34"
    assert set(record["candidate_concept_ids"]) == {"1", "2"}
    overlap = _read_overlap(tmp_path)
    assert overlap.get("concept_survey_links", {}) == {}


def test_import_response_includes_linked_and_survey_counts(tmp_path):
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "nose", "source_item": "1.5", "source_survey": "klq"},
        ],
    )
    upload = (
        "id,concept_en,source_item,source_survey\n"
        ",nose,34,jbil\n"
        ",new-thing,9,jbil\n"
    )
    response = _invoke(tmp_path, upload)
    payload = response.payload

    assert payload["linked"] == 1
    assert payload["added"] == 1
    counts = payload["survey_counts"]["jbil"]
    assert counts["linked_count"] == 1
    assert counts["created_count"] == 1
    # matched_count tracks legacy id/label-exact updates; here that's zero for jbil.
    assert counts["matched_count"] == 0
