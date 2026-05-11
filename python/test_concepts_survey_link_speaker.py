"""Speaker-scoped survey-link override tests for concept survey-link APIs."""

from __future__ import annotations

import csv
import io
import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import concepts_io  # noqa: E402
import server  # noqa: E402
from survey_overlap import SURVEY_OVERLAP_FILENAME, load_survey_overlap_state, update_survey_overlap_state  # noqa: E402

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


class _Handler(server.RangeRequestHandler):
    def __init__(self, body: bytes) -> None:
        self.rfile = io.BytesIO(body)
        self.wfile = _FakeWfile()
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        self.status: int | None = None

    def send_response(self, code):  # type: ignore[no-untyped-def]
        self.status = code

    def send_header(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        pass

    def end_headers(self) -> None:
        pass


def _seed_concepts(tmp_path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with (tmp_path / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})


def _read_concepts(tmp_path: pathlib.Path) -> list[dict[str, str]]:
    with (tmp_path / "concepts.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _seed_overlap(tmp_path: pathlib.Path, payload: dict) -> None:
    (tmp_path / SURVEY_OVERLAP_FILENAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_overlap(tmp_path: pathlib.Path) -> dict:
    return json.loads((tmp_path / SURVEY_OVERLAP_FILENAME).read_text(encoding="utf-8"))


def _post(body: dict, concept_id: str = "53") -> _Handler:
    handler = _Handler(json.dumps(body).encode("utf-8"))
    handler._api_post_concept_survey_link(concept_id)
    return handler


def _delete(body: dict, concept_id: str = "53") -> _Handler:
    handler = _Handler(json.dumps(body).encode("utf-8"))
    handler._api_delete_concept_survey_link(concept_id)
    return handler


def _base_overlap() -> dict:
    return {
        "version": 1,
        "color_coding_enabled": False,
        "surveys": {},
        "concept_survey_links": {},
        "speaker_choices": {},
    }


def test_survey_overlap_load_update_round_trips_speaker_concept_links(tmp_path: pathlib.Path) -> None:
    _seed_overlap(
        tmp_path,
        {
            **_base_overlap(),
            "speaker_concept_survey_links": {"Saha01": {"53": {"JBIL": "169"}}},
        },
    )

    state = load_survey_overlap_state(tmp_path)
    assert state["speaker_concept_survey_links"] == {"Saha01": {"53": {"jbil": "169"}}}

    updated = update_survey_overlap_state(
        tmp_path,
        {"speaker_concept_survey_links": {"Saha01": {"619": {"KLQ": "4.1"}}}},
    )

    assert updated["speaker_concept_survey_links"] == {
        "Saha01": {"53": {"jbil": "169"}, "619": {"klq": "4.1"}}
    }
    assert _read_overlap(tmp_path)["speaker_concept_survey_links"] == updated["speaker_concept_survey_links"]


def test_survey_overlap_missing_speaker_concept_links_defaults_to_empty(tmp_path: pathlib.Path) -> None:
    state = load_survey_overlap_state(tmp_path)
    assert state["speaker_concept_survey_links"] == {}


def test_post_without_speaker_keeps_global_behavior_and_omits_speaker_surveys(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose", "source_item": "1.5", "source_survey": "klq"}])

    handler = _post({"survey_id": "jbil", "source_item": "169"})

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["surveys"]["jbil"] == "169"
    assert "speaker_surveys" not in payload
    overlap = _read_overlap(tmp_path)
    assert overlap["concept_survey_links"]["53"] == {"jbil": "169"}
    assert overlap["speaker_concept_survey_links"] == {}


def test_post_with_speaker_writes_per_speaker_store_and_returns_speaker_surveys(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose", "source_item": "1.5", "source_survey": "klq"}])

    handler = _post({"survey_id": "jbil", "source_item": "169", "speaker": "Saha01"})

    assert handler.status == HTTPStatus.OK
    payload = handler.wfile.payload()
    assert payload["id"] == "53"
    assert payload["surveys"] == {"klq": "1.5"}
    assert payload["speaker_surveys"] == {"jbil": "169"}
    overlap = _read_overlap(tmp_path)
    assert overlap["concept_survey_links"] == {}
    assert overlap["speaker_concept_survey_links"] == {"Saha01": {"53": {"jbil": "169"}}}


def test_post_comma_separated_ids_with_speaker_writes_all_ids_atomically(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(
        tmp_path,
        [
            {"id": "53", "concept_en": "nose"},
            {"id": "619", "concept_en": "nose (B)"},
        ],
    )

    handler = _post({"survey_id": "jbil", "source_item": "169", "speaker": "Saha01"}, "53,619")

    assert handler.status == HTTPStatus.OK
    assert handler.wfile.payload()["speaker_surveys"] == {"jbil": "169"}
    assert _read_overlap(tmp_path)["speaker_concept_survey_links"] == {
        "Saha01": {"53": {"jbil": "169"}, "619": {"jbil": "169"}}
    }


def test_post_comma_separated_ids_without_speaker_is_400_and_does_not_write(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose"}, {"id": "619", "concept_en": "nose (B)"}])

    with pytest.raises(server.ApiError) as exc_info:
        _post({"survey_id": "jbil", "source_item": "169"}, "53,619")

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert not (tmp_path / SURVEY_OVERLAP_FILENAME).exists()


def test_post_comma_separated_ids_with_unknown_id_is_404_and_does_not_write(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose"}])

    with pytest.raises(server.ApiError) as exc_info:
        _post({"survey_id": "jbil", "source_item": "169", "speaker": "Saha01"}, "53,619")

    assert exc_info.value.status == HTTPStatus.NOT_FOUND
    assert "619" in exc_info.value.message
    assert not (tmp_path / SURVEY_OVERLAP_FILENAME).exists()


def test_post_empty_speaker_is_400(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose"}])

    with pytest.raises(server.ApiError) as exc_info:
        _post({"survey_id": "jbil", "source_item": "169", "speaker": "  "})

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST


def test_post_synthetic_group_key_still_404s_without_writing(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose"}])

    with pytest.raises(server.ApiError) as exc_info:
        _post({"survey_id": "jbil", "source_item": "169", "speaker": "Saha01"}, "4.1")

    assert exc_info.value.status == HTTPStatus.NOT_FOUND
    assert not (tmp_path / SURVEY_OVERLAP_FILENAME).exists()


def test_delete_speaker_override_prunes_empty_maps(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose"}])
    _seed_overlap(
        tmp_path,
        {**_base_overlap(), "speaker_concept_survey_links": {"Saha01": {"53": {"jbil": "169"}}}},
    )

    handler = _delete({"survey_id": "jbil", "speaker": "Saha01"})

    assert handler.status == HTTPStatus.OK
    assert handler.wfile.payload()["speaker_surveys"] == {}
    assert _read_overlap(tmp_path)["speaker_concept_survey_links"] == {}


def test_duplicate_copies_speaker_overrides_to_new_sibling(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose", "source_item": "169", "source_survey": "jbil", "custom_order": "53"}])
    _seed_overlap(
        tmp_path,
        {**_base_overlap(), "speaker_concept_survey_links": {"Saha01": {"53": {"jbil": "169"}}, "Anto02": {"53": {"klq": "4.1"}}}},
    )

    payload = concepts_io.duplicate_concept_variant(tmp_path, "53")

    sibling_id = payload["sibling"]["id"]
    assert sibling_id == "54"
    assert _read_overlap(tmp_path)["speaker_concept_survey_links"] == {
        "Anto02": {"53": {"klq": "4.1"}, "54": {"klq": "4.1"}},
        "Saha01": {"53": {"jbil": "169"}, "54": {"jbil": "169"}},
    }


def test_duplicate_restores_csv_if_speaker_override_copy_fails(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_concepts(tmp_path, [{"id": "53", "concept_en": "nose", "source_item": "169", "source_survey": "jbil", "custom_order": "53"}])
    prewrite = (tmp_path / "concepts.csv").read_bytes()
    _seed_overlap(tmp_path, {**_base_overlap(), "speaker_concept_survey_links": {"Saha01": {"53": {"jbil": "169"}}}})

    def fail_update(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("simulated survey-overlap write failure")

    monkeypatch.setattr(concepts_io, "update_survey_overlap_state", fail_update)

    with pytest.raises(concepts_io.ConceptDuplicateError):
        concepts_io.duplicate_concept_variant(tmp_path, "53")

    assert (tmp_path / "concepts.csv").read_bytes() == prewrite
    assert _read_concepts(tmp_path) == [
        {"id": "53", "concept_en": "nose", "source_item": "169", "source_survey": "jbil", "custom_order": "53"}
    ]
