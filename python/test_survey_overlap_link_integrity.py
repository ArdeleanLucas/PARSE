from __future__ import annotations

import io
import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402
from concept_source_item import write_concepts_csv_rows  # noqa: E402
from survey_overlap import SURVEY_OVERLAP_FILENAME, update_survey_overlap_state  # noqa: E402
from survey_overlap_integrity import (  # noqa: E402
    apply_survey_overlap_link_fixes,
    audit_survey_overlap_links,
    survey_overlap_link_warnings,
)
from scripts.audit_survey_overlap_links import main as audit_cli_main  # noqa: E402


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
    def __init__(self, body: dict) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.rfile = io.BytesIO(encoded)
        self.wfile = _FakeWfile()
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(encoded))}
        self.status: int | None = None

    def send_response(self, code):  # type: ignore[no-untyped-def]
        self.status = code

    def send_header(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        pass

    def end_headers(self) -> None:
        pass


def _seed_concepts(root: pathlib.Path) -> None:
    write_concepts_csv_rows(
        root / "concepts.csv",
        [
            {"id": "42", "concept_en": "rain", "source_item": "3.1", "source_survey": "klq"},
            {"id": "616", "concept_en": "rain", "source_item": "126", "source_survey": "jbil"},
            {"id": "142", "concept_en": "rain", "source_item": "125", "source_survey": "jbil"},
            {"id": "148", "concept_en": "fog", "source_item": "124", "source_survey": "jbil"},
            {"id": "537", "concept_en": "fog", "source_item": "3.9", "source_survey": "klq"},
            {"id": "44", "concept_en": "snow", "source_item": "3.3", "source_survey": "klq"},
            {"id": "45", "concept_en": "ice", "source_item": "123", "source_survey": "jbil"},
            {"id": "144", "concept_en": "snow", "source_item": "123", "source_survey": "jbil"},
            {"id": "200", "concept_en": "salt", "source_item": "8.1", "source_survey": "klq"},
            {"id": "201", "concept_en": "salt (eating)", "source_item": "210", "source_survey": "jbil"},
            {"id": "217", "concept_en": "one", "source_item": "13.1", "source_survey": "ext"},
            {"id": "194", "concept_en": "the day after tomorrow", "source_item": "9.1", "source_survey": "klq"},
            {"id": "553", "concept_en": "the day after tomorrow", "source_item": "300", "source_survey": "jbil"},
        ],
    )


def _write_overlap(root: pathlib.Path, links: dict[str, dict[str, str]]) -> None:
    update_survey_overlap_state(root, {"concept_survey_links": links})


def test_link_integrity_classifies_mismatch_dangling_nonreciprocal_and_clarifiers(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path)
    _write_overlap(
        tmp_path,
        {
            "42": {"jbil": "126"},
            "616": {"klq": "3.1"},
            "537": {"jbil": "125"},
            "200": {"jbil": "210"},
            "217": {"klq": "13.1"},
        },
    )

    report = audit_survey_overlap_links(tmp_path)

    assert {entry["source_id"] for entry in report["gloss_mismatch"]} == {"537"}
    mismatch = report["gloss_mismatch"][0]
    assert mismatch["source_gloss"] == "fog"
    assert mismatch["target_id"] == "142"
    assert mismatch["target_gloss"] == "rain"
    assert report["dangling"] == [{"source_id": "217", "link": {"survey": "klq", "item": "13.1"}}]
    assert {entry["source_id"] for entry in report["non_reciprocal"]} == {"537", "200"}
    assert all(entry["source_id"] != "200" for entry in report["gloss_mismatch"])


def test_survey_overlap_write_response_surfaces_advisory_link_warnings(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)

    handler = _Handler({"concept_survey_links": {"537": {"JBIL": "125"}}})
    handler._api_post_survey_overlap()

    payload = handler.wfile.payload()
    assert handler.status == HTTPStatus.OK
    assert payload["concept_survey_links"] == {"537": {"jbil": "125"}}
    assert "link_warnings" in payload
    assert any("gloss-mismatch" in warning and "537" in warning and "142" in warning for warning in payload["link_warnings"])


def test_concept_survey_link_post_response_surfaces_link_warnings(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    _seed_concepts(tmp_path)

    handler = _Handler({"survey_id": "jbil", "source_item": "125"})
    handler._api_post_concept_survey_link("537")

    payload = handler.wfile.payload()
    assert handler.status == HTTPStatus.OK
    assert payload["surveys"]["jbil"] == "125"
    assert any("gloss-mismatch" in warning and "fog" in warning and "rain" in warning for warning in payload["link_warnings"])


def test_audit_cli_writes_report_and_apply_fixes_is_dry_run_until_execute(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    _seed_concepts(tmp_path)
    _write_overlap(tmp_path, {"537": {"jbil": "125"}, "217": {"klq": "13.1"}})
    report_path = tmp_path / "audit.json"

    assert audit_cli_main(["--workspace", str(tmp_path), "--report", str(report_path)]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["gloss_mismatch"][0]["source_id"] == "537"
    assert report["dangling"][0]["source_id"] == "217"
    assert any(cluster["stem"] == "the day after tomorrow" for cluster in report["same_stem_unlinked"])

    fixes_path = tmp_path / "fixes.json"
    fixes_path.write_text(json.dumps({"537": {"jbil": "124"}, "217": {"klq": None}}), encoding="utf-8")

    dry_run = apply_survey_overlap_link_fixes(tmp_path, fixes_path, execute=False)
    assert dry_run["applied"] is False
    assert dry_run["would_change"] == {
        "217": {"before": {"klq": "13.1"}, "after": {}},
        "537": {"before": {"jbil": "125"}, "after": {"jbil": "124"}},
    }
    assert json.loads((tmp_path / SURVEY_OVERLAP_FILENAME).read_text(encoding="utf-8"))["concept_survey_links"]["537"] == {"jbil": "125"}

    executed = apply_survey_overlap_link_fixes(tmp_path, fixes_path, execute=True)
    assert executed["applied"] is True
    assert executed["backup_path"]
    assert pathlib.Path(executed["backup_path"]).exists()
    post_execute = json.loads((tmp_path / SURVEY_OVERLAP_FILENAME).read_text(encoding="utf-8"))
    assert post_execute["concept_survey_links"] == {"537": {"jbil": "124"}}

    second = apply_survey_overlap_link_fixes(tmp_path, fixes_path, execute=True)
    assert second["applied"] is True
    assert second["would_change"] == {}
    assert "" == capsys.readouterr().err


def test_survey_overlap_link_warnings_are_stable_strings(tmp_path: pathlib.Path) -> None:
    _seed_concepts(tmp_path)
    _write_overlap(tmp_path, {"537": {"jbil": "125"}, "217": {"klq": "13.1"}})

    warnings = survey_overlap_link_warnings(tmp_path)

    assert any(warning.startswith("gloss-mismatch: concept 537") for warning in warnings)
    assert any(warning == "dangling: concept 217 links to klq:13.1 but no concepts.csv row owns that survey item" for warning in warnings)
