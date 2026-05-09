"""Tests for POST /api/concepts/{conceptId}/duplicate."""

from __future__ import annotations

import csv
import io
import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


class _FakeWfile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def payload(self) -> dict:
        return json.loads(b"".join(self.chunks).decode("utf-8"))


class _FakeHandler(server.RangeRequestHandler):
    def __init__(self, path: str) -> None:
        self.path = path
        self.rfile = io.BytesIO(b"")
        self.wfile = _FakeWfile()
        self.headers = {"Host": "127.0.0.1:8766", "Content-Length": "0"}
        self.status: HTTPStatus | None = None
        self.sent_headers: dict[str, str] = {}

    def send_response(self, code):  # type: ignore[no-untyped-def]
        self.status = code

    def send_header(self, key, value):  # type: ignore[no-untyped-def]
        self.sent_headers[str(key)] = str(value)

    def end_headers(self) -> None:
        pass


def _write_concepts(path: pathlib.Path, rows: list[dict[str, str]]) -> bytes:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})
    return path.read_bytes()


def _read_concepts(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _post_duplicate(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, concept_id: str) -> tuple[int, dict]:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    server._install_route_bindings()
    handler = _FakeHandler(f"/api/concepts/{concept_id}/duplicate")
    assert handler._handle_api("POST") is True
    assert handler.status is not None
    return int(handler.status), handler.wfile.payload()


def test_duplicate_single_row_renames_original_appends_sibling_and_writes_backup(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    prewrite = _write_concepts(
        concepts_path,
        [
            {"id": "12", "concept_en": "ash", "source_item": "12", "source_survey": "JBIL", "custom_order": "12"},
            {"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": "322"},
            {"id": "617", "concept_en": "rain", "source_item": "150", "source_survey": "JBIL", "custom_order": "617"},
        ],
    )

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    assert payload == {
        "primary": {
            "id": "322",
            "concept_en": "leaf (A)",
            "source_item": "102",
            "source_survey": "JBIL",
            "custom_order": "322",
        },
        "sibling": {
            "id": "618",
            "concept_en": "leaf (B)",
            "source_item": "102",
            "source_survey": "JBIL",
            "custom_order": "",
        },
    }
    assert _read_concepts(concepts_path) == [
        {"id": "12", "concept_en": "ash", "source_item": "12", "source_survey": "JBIL", "custom_order": "12"},
        {"id": "322", "concept_en": "leaf (A)", "source_item": "102", "source_survey": "JBIL", "custom_order": "322"},
        {"id": "617", "concept_en": "rain", "source_item": "150", "source_survey": "JBIL", "custom_order": "617"},
        {"id": "618", "concept_en": "leaf (B)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
    ]
    backups = sorted(tmp_path.glob("concepts.csv.bak-*-pre-duplicate-322"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == prewrite


def test_duplicate_creates_C_when_AB_already_exist(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(
        concepts_path,
        [
            {"id": "322", "concept_en": "leaf (A)", "source_item": "102", "source_survey": "JBIL", "custom_order": "322"},
            {"id": "618", "concept_en": "leaf (B)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
        ],
    )

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    assert payload["primary"]["concept_en"] == "leaf (A)"
    assert payload["sibling"] == {
        "id": "619",
        "concept_en": "leaf (C)",
        "source_item": "102",
        "source_survey": "JBIL",
        "custom_order": "",
    }
    assert _read_concepts(concepts_path)[-1]["concept_en"] == "leaf (C)"


def test_duplicate_creates_D_after_three(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(
        concepts_path,
        [
            {"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": "322"},
            {"id": "618", "concept_en": "leaf (B)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
        ],
    )

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")
    assert status == HTTPStatus.OK
    assert payload["sibling"]["concept_en"] == "leaf (C)"

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    assert payload["primary"]["concept_en"] == "leaf (A)"
    assert payload["sibling"]["id"] == "620"
    assert payload["sibling"]["concept_en"] == "leaf (D)"
    assert [row["concept_en"] for row in _read_concepts(concepts_path) if row["source_item"] == "102"] == [
        "leaf (A)",
        "leaf (B)",
        "leaf (C)",
        "leaf (D)",
    ]


def test_duplicate_falls_back_to_numeric_after_Z(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    rows = [
        {
            "id": str(index),
            "concept_en": f"leaf ({chr(64 + index)})",
            "source_item": "102",
            "source_survey": "JBIL",
            "custom_order": "",
        }
        for index in range(1, 27)
    ]
    _write_concepts(concepts_path, rows)

    status, payload = _post_duplicate(tmp_path, monkeypatch, "1")

    assert status == HTTPStatus.OK
    assert payload["primary"]["concept_en"] == "leaf (A)"
    assert payload["sibling"]["id"] == "27"
    assert payload["sibling"]["concept_en"] == "leaf (27)"


def test_duplicate_leaves_bare_primary_when_A_sibling_already_exists(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(
        concepts_path,
        [
            {"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": "322"},
            {"id": "618", "concept_en": "leaf (A)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
        ],
    )

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    assert payload["primary"]["concept_en"] == "leaf"
    assert payload["sibling"]["concept_en"] == "leaf (B)"
    assert _read_concepts(concepts_path) == [
        {"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": "322"},
        {"id": "618", "concept_en": "leaf (A)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
        {"id": "619", "concept_en": "leaf (B)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
    ]


def test_duplicate_does_not_double_suffix_when_primary_already_lettered(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(concepts_path, [{"id": "322", "concept_en": "leaf (C)", "source_item": "102", "source_survey": "JBIL", "custom_order": "322"}])

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    assert payload["primary"]["concept_en"] == "leaf (C)"
    # Sparse families intentionally allocate the first free label, not the next ordinal after the target.
    assert payload["sibling"]["concept_en"] == "leaf (A)"
    assert _read_concepts(concepts_path) == [
        {"id": "322", "concept_en": "leaf (C)", "source_item": "102", "source_survey": "JBIL", "custom_order": "322"},
        {"id": "323", "concept_en": "leaf (A)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
    ]


def test_duplicate_returns_404_when_concept_missing(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_concepts(tmp_path / "concepts.csv", [{"id": "1", "concept_en": "ash", "source_item": "1", "source_survey": "JBIL", "custom_order": ""}])

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.NOT_FOUND
    assert payload == {"error": "concept not found"}


def test_duplicate_returns_400_when_concept_id_is_not_numeric(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_concepts(tmp_path / "concepts.csv", [{"id": "1", "concept_en": "ash", "source_item": "1", "source_survey": "JBIL", "custom_order": ""}])

    status, payload = _post_duplicate(tmp_path, monkeypatch, "not-a-number")

    assert status == HTTPStatus.BAD_REQUEST
    assert payload == {"error": "conceptId must be numeric"}


def test_duplicate_returns_400_for_malformed_concepts_duplicate_path(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_concepts(tmp_path / "concepts.csv", [{"id": "1", "concept_en": "ash", "source_item": "1", "source_survey": "JBIL", "custom_order": ""}])
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    server._install_route_bindings()
    handler = _FakeHandler("/api/concepts/1/not-duplicate")

    assert handler._handle_api("POST") is True

    assert int(handler.status or 0) == HTTPStatus.BAD_REQUEST
    assert handler.wfile.payload() == {"error": "Malformed concept path"}


def test_duplicate_restores_backup_when_atomic_write_fails(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import concepts_io

    concepts_path = tmp_path / "concepts.csv"
    prewrite = _write_concepts(concepts_path, [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])

    def fail_after_torn_write(path, rows, *, atomic=False):  # type: ignore[no-untyped-def]
        path.write_text("torn write\n", encoding="utf-8")
        raise OSError("simulated replace failure")

    monkeypatch.setattr(concepts_io, "write_concepts_csv_rows", fail_after_torn_write)

    with pytest.raises(concepts_io.ConceptDuplicateError) as excinfo:
        concepts_io.duplicate_concept_variant(tmp_path, "322")

    assert int(excinfo.value.status) == HTTPStatus.INTERNAL_SERVER_ERROR
    assert str(excinfo.value) == "failed to duplicate concept"
    assert concepts_path.read_bytes() == prewrite
    backups = sorted(tmp_path.glob("concepts.csv.bak-*-pre-duplicate-322"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == prewrite


def test_duplicate_copies_concept_tags_to_sibling_in_annotation_files(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(concepts_path, [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])

    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    annotation_data = {
        "version": 1,
        "speaker": "Saha01",
        "concept_tags": {
            "322": ["thesis", "confirmed"],
            "100": ["thesis"],
        },
    }
    annotation_path = annotations_dir / "Saha01.json"
    annotation_path.write_text(json.dumps(annotation_data), encoding="utf-8")

    # Speaker with no tags for concept 322 — sibling slot must stay absent
    empty_speaker_data = {"version": 1, "speaker": "Khan01", "concept_tags": {"100": ["thesis"]}}
    (annotations_dir / "Khan01.json").write_text(json.dumps(empty_speaker_data), encoding="utf-8")

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    sibling_id = payload["sibling"]["id"]

    # Tags copied for Saha01 who had them
    updated = json.loads(annotation_path.read_text(encoding="utf-8"))
    assert updated["concept_tags"][sibling_id] == ["thesis", "confirmed"]
    assert updated["concept_tags"]["322"] == ["thesis", "confirmed"]  # primary unchanged

    # No spurious entry for Khan01 who had no tags for 322
    khan_updated = json.loads((annotations_dir / "Khan01.json").read_text(encoding="utf-8"))
    assert sibling_id not in khan_updated["concept_tags"]


def test_duplicate_does_not_overwrite_existing_sibling_tags(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(concepts_path, [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])

    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()

    # Sibling slot already populated — must not be overwritten
    annotation_data = {
        "version": 1,
        "speaker": "Saha01",
        "concept_tags": {
            "322": ["thesis"],
            "618": ["confirmed"],
        },
    }
    annotation_path = annotations_dir / "Saha01.json"
    annotation_path.write_text(json.dumps(annotation_data), encoding="utf-8")

    status, payload = _post_duplicate(tmp_path, monkeypatch, "322")
    assert status == HTTPStatus.OK

    updated = json.loads(annotation_path.read_text(encoding="utf-8"))
    # Existing sibling tags must be preserved, not overwritten
    assert updated["concept_tags"]["618"] == ["confirmed"]
