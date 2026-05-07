from __future__ import annotations

import json
import pathlib
import sys
from http import HTTPStatus

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server
from survey_overlap import SURVEY_OVERLAP_FILENAME


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, body=None):
        self._body = {} if body is None else body
        self.sent = []
        self.headers = {}
        self.rfile = None

    def _read_json_body(self, required: bool = True):
        return self._body

    def _expect_object(self, value, label: str):
        if not isinstance(value, dict):
            raise server.ApiError(HTTPStatus.BAD_REQUEST, f"{label} must be an object")
        return value

    def _send_json(self, status, payload):
        self.sent.append((status, payload))


def test_api_get_survey_overlap_returns_backward_compatible_default_state(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    handler = _HandlerHarness()

    handler._api_get_survey_overlap()

    assert handler.sent == [
        (
            HTTPStatus.OK,
            {
                "survey_overlap": {
                    "version": 1,
                    "color_coding_enabled": False,
                    "surveys": {},
                    "concept_survey_links": {},
                    "speaker_choices": {},
                }
            },
        )
    ]


def test_api_post_survey_overlap_persists_labels_toggle_and_speaker_choices(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    handler = _HandlerHarness(
        {
            "color_coding_enabled": True,
            "surveys": {"KLQ": {"display_label": "Kurdish Linguistic Questionnaire", "display_color": "violet"}},
            "concept_survey_links": {"salt": {"KLQ": "3.14", "JBIL": "139"}},
            "speaker_choices": {"Saha01": {"salt": "JBIL"}},
        }
    )

    handler._api_post_survey_overlap()

    assert handler.sent == [
        (
            HTTPStatus.OK,
            {
                "success": True,
                "survey_overlap": {
                    "version": 1,
                    "color_coding_enabled": True,
                    "surveys": {"klq": {"display_label": "Kurdish Linguistic Questionnaire", "display_color": "violet"}},
                    "concept_survey_links": {"salt": {"klq": "3.14", "jbil": "139"}},
                    "speaker_choices": {"Saha01": {"salt": "jbil"}},
                },
            },
        )
    ]
    payload = json.loads((tmp_path / SURVEY_OVERLAP_FILENAME).read_text(encoding="utf-8"))
    assert payload["color_coding_enabled"] is True
    assert payload["speaker_choices"] == {"Saha01": {"salt": "jbil"}}


def test_api_post_survey_overlap_accepts_nested_patch_payload(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    handler = _HandlerHarness({"survey_overlap": {"surveys": {"JBIL": {"display_label": "Bailey", "display_color": "amber"}}}})

    handler._api_post_survey_overlap()

    assert handler.sent[0][0] == HTTPStatus.OK
    assert handler.sent[0][1]["survey_overlap"]["surveys"] == {"jbil": {"display_label": "Bailey", "display_color": "amber"}}


def test_survey_overlap_dispatch_routes_get_and_post(monkeypatch) -> None:
    calls: list[str] = []
    handler = _HandlerHarness()
    monkeypatch.setattr(handler, "_api_get_survey_overlap", lambda: calls.append("get"), raising=False)
    monkeypatch.setattr(handler, "_api_post_survey_overlap", lambda: calls.append("post"), raising=False)

    handler._dispatch_api_get("/api/survey-overlap")
    handler._dispatch_api_post("/api/survey-overlap")

    assert calls == ["get", "post"]
