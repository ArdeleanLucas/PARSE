from __future__ import annotations

import csv
import io
import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402


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


class _Handler(server.RangeRequestHandler):
    def __init__(self, body: bytes = b"") -> None:
        self.rfile = io.BytesIO(body)
        self.wfile = _FakeWfile()
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        self.status: int | None = None

    def send_response(self, code):
        self.status = code

    def send_header(self, *_args, **_kwargs):
        pass

    def end_headers(self):
        pass


def _seed_concepts(project_root: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with (project_root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})


def _post(body: dict | None = None) -> _Handler:
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    handler = _Handler(raw)
    handler._api_post_concepts_relink_by_gloss()
    return handler


def test_dry_run_relink_by_gloss_reports_strict_groups_without_writing(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "(1.5)- Nose"},
            {"id": "2", "concept_en": "Nose A", "source_item": "34", "source_survey": "JBIL"},
        ],
    )

    handler = _post()

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["ok"] is True
    assert payload["applied"] is False
    assert payload["groups"][0]["keep_concept_id"] == "2"
    assert payload["groups"][0]["merge_concept_ids"] == ["1"]
    with (tmp_path / "concepts.csv").open(newline="", encoding="utf-8") as handle:
        assert [row["id"] for row in csv.DictReader(handle)] == ["1", "2"]


def test_apply_relink_by_gloss_accepts_current_group_and_writes_backup(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "(1.5)- Nose"},
            {"id": "2", "concept_en": "Nose A", "source_item": "34", "source_survey": "JBIL"},
        ],
    )

    handler = _post({"apply": True, "accepted_groups": [{"keep_concept_id": "2", "merge_concept_ids": ["1"]}]})

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["applied"] is True
    assert payload["groups"] == [
        {
            "canonical_gloss": "nose",
            "keep_concept_id": "2",
            "merge_concept_ids": ["1"],
            "labels": {"1": "(1.5)- Nose", "2": "Nose A"},
            "links_by_survey": {"jbil": "34"},
            "source_rows": [
                {"concept_id": "1", "concept_en": "(1.5)- Nose", "source_survey": "", "source_item": ""},
                {"concept_id": "2", "concept_en": "Nose A", "source_survey": "JBIL", "source_item": "34"},
            ],
            "keep_reason": "metadata_rich_over_lowest_empty",
        }
    ]
    assert payload["annotation_rewrites"] == {}
    assert any(path.endswith("/concepts.csv") for path in payload["backup_paths"])
    assert any(path.endswith("/survey-overlap.json") for path in payload["backup_paths"])
    assert (tmp_path / payload["backup_paths"][0]).exists()


def test_apply_relink_by_gloss_rejects_stale_or_fuzzy_groups(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "1", "concept_en": "ear (inner)"}, {"id": "2", "concept_en": "ear"}])

    with pytest.raises(server.ApiError) as exc_info:
        _post({"apply": True, "accepted_groups": [{"incoming_label": "ear (inner)", "candidate_label": "ear", "reason": "parenthetical_stripped_match"}]})

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "fuzzy_candidates_require_manual_relabel"

    with pytest.raises(server.ApiError) as stale:
        _post({"apply": True, "accepted_groups": [{"keep_concept_id": "1", "merge_concept_ids": ["2"]}]})

    assert stale.value.status == HTTPStatus.BAD_REQUEST
    assert stale.value.message == "accepted_group_not_current"


@pytest.mark.parametrize("accepted_groups", ["not-a-list", ["not-an-object"]])
def test_apply_relink_by_gloss_400_on_malformed_accepted_groups(
    tmp_path: pathlib.Path,
    monkeypatch,
    accepted_groups,
) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [
            {"id": "1", "concept_en": "(1.5)- Nose"},
            {"id": "2", "concept_en": "Nose A", "source_item": "34", "source_survey": "JBIL"},
        ],
    )

    with pytest.raises(server.ApiError) as exc_info:
        _post({"apply": True, "accepted_groups": accepted_groups})

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "accepted_groups_must_be_group_objects"
