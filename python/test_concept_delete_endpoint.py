"""Tests for DELETE /api/concepts/{conceptId}."""

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
from storage import tags_store  # noqa: E402
from survey_overlap import SURVEY_OVERLAP_FILENAME  # noqa: E402

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


def _delete_concept(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, concept_id: str, *, query: str = "") -> tuple[int, dict]:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    server._install_route_bindings()
    handler = _FakeHandler(f"/api/concepts/{concept_id}{query}")
    assert handler._handle_api("DELETE") is True
    assert handler.status is not None
    return int(handler.status), handler.wfile.payload()


def test_delete_unannotated_concept_removes_row_and_writes_backup(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    prewrite = _write_concepts(
        concepts_path,
        [
            {"id": "12", "concept_en": "ash", "source_item": "12", "source_survey": "JBIL", "custom_order": "12"},
            {"id": "322", "concept_en": "leaf (B)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
            {"id": "617", "concept_en": "rain", "source_item": "150", "source_survey": "JBIL", "custom_order": "617"},
        ],
    )

    status, payload = _delete_concept(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    assert payload == {"ok": True, "deleted_id": "322"}
    assert _read_concepts(concepts_path) == [
        {"id": "12", "concept_en": "ash", "source_item": "12", "source_survey": "JBIL", "custom_order": "12"},
        {"id": "617", "concept_en": "rain", "source_item": "150", "source_survey": "JBIL", "custom_order": "617"},
    ]
    backups = sorted(tmp_path.glob("concepts.csv.bak-*-pre-delete-322"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == prewrite


def test_delete_returns_409_when_speaker_has_annotated_concept(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_concepts(tmp_path / "concepts.csv", [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    (annotations_dir / "Qasr01.json").write_text(
        json.dumps({"tiers": {"concept": {"intervals": [{"concept_id": "322"}]}}}),
        encoding="utf-8",
    )

    status, payload = _delete_concept(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.CONFLICT
    assert payload == {
        "error": "canonical concept row is annotated by one or more speakers; cannot delete",
        "blocking_speakers": ["Qasr01"],
    }
    assert len(list(tmp_path.glob("concepts.csv.bak-*-pre-delete-322"))) == 0


def test_delete_ignores_stale_legacy_json_when_parse_json_is_clean(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A speaker who still references the concept in the STALE legacy .json but
    has cleared it from the live .parse.json must NOT block deletion — the guard
    reads the same .parse.json view as Compare. Regression: globbing *.json kept
    garbage concepts undeletable after the user cleaned the live annotation."""
    _write_concepts(tmp_path / "concepts.csv", [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    # Live annotation: concept 322 already removed.
    (annotations_dir / "Qasr01.parse.json").write_text(
        json.dumps({"tiers": {"concept": {"intervals": [{"concept_id": "999"}]}}}),
        encoding="utf-8",
    )
    # Stale legacy file: still references 322. Must be ignored.
    (annotations_dir / "Qasr01.json").write_text(
        json.dumps({"tiers": {"concept": {"intervals": [{"concept_id": "322"}]}}}),
        encoding="utf-8",
    )

    status, payload = _delete_concept(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    assert payload == {"ok": True, "deleted_id": "322"}


def test_cascade_delete_purges_recordings_across_speakers_and_removes_row(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """?cascade=true removes the concept's recordings (and their sibling tier
    intervals) from every speaker, backs each file up, then deletes the row."""
    _write_concepts(tmp_path / "concepts.csv", [
        {"id": "322", "concept_en": "dry (A)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
        {"id": "323", "concept_en": "dry (B)", "source_item": "103", "source_survey": "JBIL", "custom_order": ""},
    ])
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    # Two speakers each have a garbage 322 recording plus an unrelated 323 one.
    for speaker in ("Fail01", "Qasr01"):
        (annotations_dir / f"{speaker}.parse.json").write_text(
            json.dumps({
                "speaker": speaker,
                "tiers": {
                    "concept": {"intervals": [
                        {"concept_id": "322", "start": 1.0, "end": 2.0},
                        {"concept_id": "323", "start": 3.0, "end": 4.0},
                    ]},
                    "ipa": {"intervals": [
                        {"text": "taːl", "start": 1.0, "end": 2.0},
                        {"text": "heʃɪk", "start": 3.0, "end": 4.0},
                    ]},
                },
            }),
            encoding="utf-8",
        )

    status, payload = _delete_concept(tmp_path, monkeypatch, "322", query="?cascade=true")

    assert status == HTTPStatus.OK
    assert payload["deleted_id"] == "322"
    assert payload["purged_intervals"] == 2
    assert payload["purged_speakers"] == ["Fail01", "Qasr01"]
    # Row removed.
    assert [r["id"] for r in _read_concepts(tmp_path / "concepts.csv")] == ["323"]
    # Each speaker keeps only the unrelated 323 recording (concept + sibling ipa).
    for speaker in ("Fail01", "Qasr01"):
        data = json.loads((annotations_dir / f"{speaker}.parse.json").read_text(encoding="utf-8"))
        assert [i["concept_id"] for i in data["tiers"]["concept"]["intervals"]] == ["323"]
        assert [i["text"] for i in data["tiers"]["ipa"]["intervals"]] == ["heʃɪk"]
        assert list(annotations_dir.glob(f"{speaker}.parse.json.bak-*-pre-purge-322"))


def test_cascade_only_touches_the_warning_speakers_and_leaves_others_intact(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cascade must purge exactly the speakers the block warning lists — the ones
    that actually annotated the concept — and leave every other speaker's file
    byte-identical with no backup. A speaker who never annotated the concept, or
    only annotated a sibling concept, must not be touched."""
    _write_concepts(tmp_path / "concepts.csv", [
        {"id": "322", "concept_en": "dry (A)", "source_item": "102", "source_survey": "JBIL", "custom_order": ""},
        {"id": "323", "concept_en": "dry (B)", "source_item": "103", "source_survey": "JBIL", "custom_order": ""},
    ])
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    # Two speakers annotated 322 (the warning set); one annotated only 323.
    for speaker in ("Fail01", "Qasr01"):
        (annotations_dir / f"{speaker}.parse.json").write_text(
            json.dumps({"speaker": speaker, "tiers": {"concept": {"intervals": [{"concept_id": "322", "start": 1.0, "end": 2.0}]}}}),
            encoding="utf-8",
        )
    saha_path = annotations_dir / "Saha01.parse.json"
    saha_path.write_text(
        json.dumps({"speaker": "Saha01", "tiers": {"concept": {"intervals": [{"concept_id": "323", "start": 5.0, "end": 6.0}]}}}),
        encoding="utf-8",
    )
    saha_before = saha_path.read_bytes()

    # The warning the user sees: deleting without cascade reports exactly Fail01 + Qasr01.
    blocked_status, blocked_payload = _delete_concept(tmp_path, monkeypatch, "322")
    assert blocked_status == HTTPStatus.CONFLICT
    assert blocked_payload["blocking_speakers"] == ["Fail01", "Qasr01"]

    status, payload = _delete_concept(tmp_path, monkeypatch, "322", query="?cascade=true")

    assert status == HTTPStatus.OK
    # Purge set equals the warning set — no more, no fewer.
    assert payload["purged_speakers"] == blocked_payload["blocking_speakers"]
    # The non-participating speaker is byte-identical and was never backed up.
    assert saha_path.read_bytes() == saha_before
    assert not list(annotations_dir.glob("Saha01.parse.json.bak-*"))


def test_cascade_delete_is_noop_purge_when_not_blocked(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """cascade on an unannotated row deletes normally and reports no purge."""
    _write_concepts(tmp_path / "concepts.csv", [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])
    status, payload = _delete_concept(tmp_path, monkeypatch, "322", query="?cascade=true")
    assert status == HTTPStatus.OK
    assert "purged_intervals" not in payload


def test_delete_blocks_when_live_parse_json_references_concept(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The live .parse.json is authoritative: a real reference there still blocks."""
    _write_concepts(tmp_path / "concepts.csv", [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    (annotations_dir / "Qasr01.parse.json").write_text(
        json.dumps({"speaker": "Qasr01", "tiers": {"concept": {"intervals": [{"concept_id": "322"}]}}}),
        encoding="utf-8",
    )

    status, payload = _delete_concept(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.CONFLICT
    assert payload["blocking_speakers"] == ["Qasr01"]


def test_delete_cleans_sidecar_state(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_TAGS_PATH", str(tmp_path / "tags.json"))
    concepts_path = tmp_path / "concepts.csv"
    _write_concepts(
        concepts_path,
        [
            {"id": "53", "concept_en": "big (A)", "source_item": "4.1", "source_survey": "KLQ", "custom_order": "53"},
            {"id": "54", "concept_en": "big (B)", "source_item": "4.1", "source_survey": "KLQ", "custom_order": ""},
        ],
    )
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir()
    annotation_path = annotations_dir / "Saha01.json"
    annotation_path.write_text(
        json.dumps({"speaker": "Saha01", "concept_tags": {"53": ["thesis"], "54": ["delete-me"]}}),
        encoding="utf-8",
    )
    tags_store.replace_all(
        [
            {"id": "t-thesis", "label": "Thesis", "color": "#000000", "concepts": ["53", "54"], "lexemeTargets": []},
            {"id": "t-other", "label": "Other", "color": "#111111", "concepts": ["999"], "lexemeTargets": []},
        ]
    )
    (tmp_path / SURVEY_OVERLAP_FILENAME).write_text(
        json.dumps(
            {
                "version": 1,
                "color_coding_enabled": False,
                "surveys": {},
                "concept_survey_links": {},
                "speaker_choices": {},
                "speaker_concept_survey_links": {"Saha01": {"54": {"jbil": "169"}, "53": {"jbil": "168"}}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "parse-enrichments.json").write_text(
        json.dumps(
            {
                "manual_overrides": {
                    "canonical_lexemes": {
                        "big": {
                            "Saha01": {"csv_row_id": "54", "source": "manual"},
                            "Khan01": {"csv_row_id": "53", "source": "manual"},
                        }
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    status, payload = _delete_concept(tmp_path, monkeypatch, "54")

    assert status == HTTPStatus.OK
    assert payload == {"ok": True, "deleted_id": "54"}
    assert "54" not in json.loads(annotation_path.read_text(encoding="utf-8"))["concept_tags"]
    tags = tags_store.fetch_all()["tags"]
    assert next(tag for tag in tags if tag["id"] == "t-thesis")["concepts"] == ["53"]
    overlap = json.loads((tmp_path / SURVEY_OVERLAP_FILENAME).read_text(encoding="utf-8"))
    assert overlap["speaker_concept_survey_links"] == {"Saha01": {"53": {"jbil": "168"}}}
    enrichments = json.loads((tmp_path / "parse-enrichments.json").read_text(encoding="utf-8"))
    canonical = enrichments["manual_overrides"]["canonical_lexemes"]["big"]
    assert canonical == {"Khan01": {"csv_row_id": "53", "source": "manual"}}


def test_delete_restores_from_backup_on_csv_write_failure(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    concepts_path = tmp_path / "concepts.csv"
    prewrite = _write_concepts(concepts_path, [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])

    def fail_after_torn_write(path, rows, *, atomic=False):  # type: ignore[no-untyped-def]
        path.write_text("torn write\n", encoding="utf-8")
        raise OSError("simulated replace failure")

    monkeypatch.setattr(concepts_io, "write_concepts_csv_rows", fail_after_torn_write)

    with pytest.raises(concepts_io.ConceptDeleteError) as excinfo:
        concepts_io.delete_concept_variant(tmp_path, "322")

    assert int(excinfo.value.status) == HTTPStatus.INTERNAL_SERVER_ERROR
    assert str(excinfo.value) == "failed to delete concept"
    assert concepts_path.read_bytes() == prewrite
    backups = sorted(tmp_path.glob("concepts.csv.bak-*-pre-delete-322"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == prewrite


def test_delete_returns_404_when_concept_id_missing(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_concepts(tmp_path / "concepts.csv", [{"id": "1", "concept_en": "ash", "source_item": "1", "source_survey": "JBIL", "custom_order": ""}])

    status, payload = _delete_concept(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.NOT_FOUND
    assert payload == {"error": "concept not found"}


def test_delete_idempotent_when_sidecars_partially_missing(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_TAGS_PATH", str(tmp_path / "tags.json"))
    _write_concepts(tmp_path / "concepts.csv", [{"id": "322", "concept_en": "leaf", "source_item": "102", "source_survey": "JBIL", "custom_order": ""}])
    tags_store.replace_all([{ "id": "t-other", "label": "Other", "color": "#111111", "concepts": ["999"], "lexemeTargets": [] }])

    status, payload = _delete_concept(tmp_path, monkeypatch, "322")

    assert status == HTTPStatus.OK
    assert payload == {"ok": True, "deleted_id": "322"}
    assert _read_concepts(tmp_path / "concepts.csv") == []
    assert tags_store.fetch_all()["tags"][0]["concepts"] == ["999"]
