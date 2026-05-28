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
from canonical_lexemes import load_canonical_lexemes

FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


class _FakeWfile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def flush(self) -> None:
        pass

    def payload(self) -> dict:
        raw = b"".join(self.chunks).decode("utf-8")
        body = raw.split("\r\n\r\n", 1)[-1]
        return json.loads(body)

    def text(self) -> str:
        raw = b"".join(self.chunks).decode("utf-8")
        return raw.split("\r\n\r\n", 1)[-1]


class _Handler(server.RangeRequestHandler):
    def __init__(self, body: bytes = b"", path: str = "/api/compare/bundles") -> None:
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = _FakeWfile()
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        self.status: int | None = None
        self.sent_headers: dict[str, str] = {}

    def send_response(self, code):  # type: ignore[no-untyped-def]
        self.status = code

    def send_header(self, key, value):  # type: ignore[no-untyped-def]
        self.sent_headers[str(key)] = str(value)

    def end_headers(self) -> None:
        pass


def _seed_concepts(root: pathlib.Path) -> None:
    rows = [
        {"id": "53", "concept_en": "big (A)", "source_item": "4.1", "source_survey": "KLQ", "custom_order": "53"},
        {"id": "619", "concept_en": "big (B)", "source_item": "4.1", "source_survey": "KLQ", "custom_order": "619"},
        {"id": "150", "concept_en": "big (A)", "source_item": "169", "source_survey": "JBIL", "custom_order": "150"},
    ]
    with (root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _seed_annotation(root: pathlib.Path, speaker: str, concept_ids: list[str]) -> None:
    annotations = root / "annotations"
    annotations.mkdir(exist_ok=True)
    intervals = [
        {"text": "big", "concept_id": cid, "start": idx + 1, "end": idx + 2, "ipa": f"ipa-{cid}", "ortho": f"ortho-{cid}"}
        for idx, cid in enumerate(concept_ids)
    ]
    (annotations / f"{speaker}.parse.json").write_text(
        json.dumps({"audio": {"source_wav": f"{speaker}.wav"}, "tiers": {"concept": {"intervals": intervals}}}),
        encoding="utf-8",
    )


def _put(body: dict, bundle_id: str = "bundle:big", speaker: str = "Saha01") -> _Handler:
    encoded = json.dumps(body).encode("utf-8")
    handler = _Handler(encoded, f"/api/compare/canonical-lexemes/{bundle_id}/{speaker}")
    handler._api_put_compare_canonical_lexeme(bundle_id, speaker)
    return handler


def _delete(bundle_id: str = "bundle:big", speaker: str = "Saha01") -> _Handler:
    handler = _Handler(path=f"/api/compare/canonical-lexemes/{bundle_id}/{speaker}")
    handler._api_delete_compare_canonical_lexeme(bundle_id, speaker)
    return handler


def test_get_compare_bundles_filters_speaker_and_bundle(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    _seed_annotation(tmp_path, "Saha01", ["53"])
    _seed_annotation(tmp_path, "Khan02", ["619"])
    (tmp_path / "project.json").write_text(json.dumps({"speakers": {"Saha01": {}, "Khan02": {}}}), encoding="utf-8")

    handler = _Handler(path="/api/compare/bundles?speaker=Saha01&bundle_id=bundle:big")
    handler._api_get_compare_bundles()

    payload = handler.wfile.payload()
    assert handler.status == HTTPStatus.OK
    assert [bundle["bundle_id"] for bundle in payload["bundles"]] == ["bundle:big"]
    assert set(payload["bundles"][0]["candidates"]) == {"Saha01"}


def test_put_canonical_lexeme_validates_membership_and_writes_atomically(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    _seed_annotation(tmp_path, "Saha01", ["53", "619"])

    handler = _put({"csv_row_id": "53", "realization_index": 0})

    payload = handler.wfile.payload()
    assert handler.status == HTTPStatus.OK
    assert payload["bundle"]["canonical"]["Saha01"]["csv_row_id"] == "53"
    assert load_canonical_lexemes(tmp_path)["bundle:big"]["Saha01"]["source"] == "manual"
    assert not (tmp_path / "parse-enrichments.json.tmp").exists()


def test_put_canonical_lexeme_rejects_row_that_override_moved_out_of_visible_bundle(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    _seed_annotation(tmp_path, "Saha01", ["53"])
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps({"speaker_concept_survey_links": {"Saha01": {"53": {"ext": "999"}}}}),
        encoding="utf-8",
    )

    with pytest.raises(server.ApiError) as exc_info:
        _put({"csv_row_id": "53", "realization_index": 0})

    assert exc_info.value.status == HTTPStatus.CONFLICT
    assert "repair_hint" in exc_info.value.message
    assert not (tmp_path / "parse-enrichments.json").exists()


def test_delete_canonical_lexeme_is_idempotent(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    _seed_annotation(tmp_path, "Saha01", ["53"])
    _put({"csv_row_id": "53"})

    handler = _delete()
    second = _delete()

    assert handler.status == HTTPStatus.OK
    assert second.status == HTTPStatus.OK
    assert load_canonical_lexemes(tmp_path) == {}


def test_dispatch_routes_use_path_parts_for_compare_canonical_endpoints(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    _seed_annotation(tmp_path, "Saha01", ["53"])
    handler = _Handler(json.dumps({"csv_row_id": "53"}).encode("utf-8"), "/api/compare/canonical-lexemes/bundle%3Abig/Saha01")

    handler._dispatch_api_put("/api/compare/canonical-lexemes/bundle%3Abig/Saha01")

    assert handler.status == HTTPStatus.OK
    assert handler.wfile.payload()["bundle"]["bundle_id"] == "bundle:big"


def test_canonical_report_endpoint_returns_tsv(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)
    _seed_annotation(tmp_path, "Saha01", ["53"])
    (tmp_path / "project.json").write_text(json.dumps({"speakers": {"Saha01": {}}}), encoding="utf-8")

    handler = _Handler(path="/api/exports/canonical-lexemes-report")
    handler._api_get_canonical_lexemes_report()

    assert handler.status == HTTPStatus.OK
    assert handler.sent_headers["Content-Type"] == "text/tab-separated-values; charset=utf-8"
    assert handler.wfile.text().splitlines()[0].startswith("speaker\tbundle_id\tbundle_label")
    assert "Saha01\tbundle:big" in handler.wfile.text()
