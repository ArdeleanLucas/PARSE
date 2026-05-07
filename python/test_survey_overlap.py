from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from concept_source_item import read_concepts_csv_rows, write_concepts_csv_rows
from survey_overlap import (
    SURVEY_OVERLAP_FILENAME,
    load_survey_overlap_state,
    resolve_survey_for_speaker,
    save_survey_overlap_state,
    survey_sort_key_for_speaker,
    update_survey_overlap_state,
)


def test_missing_sidecar_loads_empty_backward_compatible_state(tmp_path: pathlib.Path) -> None:
    state = load_survey_overlap_state(tmp_path)

    assert state["version"] == 1
    assert state["color_coding_enabled"] is False
    assert state["surveys"] == {}
    assert state["concept_survey_links"] == {}
    assert state["speaker_choices"] == {}


def test_load_normalizes_surveys_links_and_speaker_choices(tmp_path: pathlib.Path) -> None:
    (tmp_path / SURVEY_OVERLAP_FILENAME).write_text(
        json.dumps(
            {
                "version": 1,
                "color_coding_enabled": True,
                "surveys": {
                    "KLQ": {"display_label": "Kurdish Linguistic Questionnaire", "display_color": "violet"},
                    "JBIL": {"display_label": "Bailey", "display_color": "amber"},
                },
                "concept_survey_links": {"101": {"KLQ": "3.14", "JBIL": "139"}},
                "speaker_choices": {"Saha01": {"101": "JBIL"}},
            }
        ),
        encoding="utf-8",
    )

    state = load_survey_overlap_state(tmp_path)

    assert state["color_coding_enabled"] is True
    assert state["surveys"] == {
        "klq": {"display_label": "Kurdish Linguistic Questionnaire", "display_color": "violet"},
        "jbil": {"display_label": "Bailey", "display_color": "amber"},
    }
    assert state["concept_survey_links"] == {"101": {"klq": "3.14", "jbil": "139"}}
    assert state["speaker_choices"] == {"Saha01": {"101": "jbil"}}


def test_update_and_save_preserve_canonical_survey_ids(tmp_path: pathlib.Path) -> None:
    state = update_survey_overlap_state(
        tmp_path,
        {
            "color_coding_enabled": True,
            "surveys": {"KLQ": {"display_label": "KLQ", "display_color": "indigo"}},
            "concept_survey_links": {"101": {"KLQ": "3.14", "JBIL": "139"}},
            "speaker_choices": {"Saha01": {"101": "JBIL"}},
        },
    )

    assert state["concept_survey_links"]["101"] == {"klq": "3.14", "jbil": "139"}
    assert state["speaker_choices"]["Saha01"] == {"101": "jbil"}

    reloaded = load_survey_overlap_state(tmp_path)
    assert reloaded == state

    payload = json.loads((tmp_path / SURVEY_OVERLAP_FILENAME).read_text(encoding="utf-8"))
    assert payload["speaker_choices"] == {"Saha01": {"101": "jbil"}}


def test_update_reset_surveys_flag_clears_existing_survey_settings(tmp_path: pathlib.Path) -> None:
    update_survey_overlap_state(
        tmp_path,
        {
            "surveys": {
                "KLQ": {"display_label": "Kurdish List", "display_color": "teal"},
                "JBIL": {"display_label": "Jbil", "display_color": "amber"},
            },
            "concept_survey_links": {"101": {"KLQ": "3.14"}},
            "speaker_choices": {"Saha01": {"101": "KLQ"}},
        },
    )

    state = update_survey_overlap_state(tmp_path, {"reset_surveys": True})

    assert state["surveys"] == {}
    assert state["concept_survey_links"] == {"101": {"klq": "3.14"}}
    assert state["speaker_choices"] == {"Saha01": {"101": "klq"}}
    payload = json.loads((tmp_path / SURVEY_OVERLAP_FILENAME).read_text(encoding="utf-8"))
    assert payload["surveys"] == {}


def test_update_reset_surveys_then_applies_incoming_survey_settings(tmp_path: pathlib.Path) -> None:
    update_survey_overlap_state(
        tmp_path,
        {
            "surveys": {
                "KLQ": {"display_label": "Kurdish List", "display_color": "teal"},
                "JBIL": {"display_label": "Jbil", "display_color": "amber"},
            },
        },
    )

    state = update_survey_overlap_state(
        tmp_path,
        {
            "reset_surveys": True,
            "surveys": {"WALS": {"display_label": "World Atlas", "display_color": "blue"}},
        },
    )

    assert state["surveys"] == {"wals": {"display_label": "World Atlas", "display_color": "blue"}}


def test_update_reset_speaker_choices_clears_independently_of_surveys(tmp_path: pathlib.Path) -> None:
    update_survey_overlap_state(
        tmp_path,
        {
            "surveys": {"KLQ": {"display_label": "Kurdish List", "display_color": "teal"}},
            "speaker_choices": {"Saha01": {"101": "KLQ"}},
        },
    )

    state = update_survey_overlap_state(tmp_path, {"reset_speaker_choices": True})

    assert state["speaker_choices"] == {}
    assert state["surveys"] == {"klq": {"display_label": "Kurdish List", "display_color": "teal"}}


def test_update_reset_concept_survey_links_clears_independently(tmp_path: pathlib.Path) -> None:
    update_survey_overlap_state(
        tmp_path,
        {
            "concept_survey_links": {"101": {"KLQ": "3.14"}},
            "speaker_choices": {"Saha01": {"101": "KLQ"}},
        },
    )

    state = update_survey_overlap_state(tmp_path, {"reset_concept_survey_links": True})

    assert state["concept_survey_links"] == {}
    assert state["speaker_choices"] == {"Saha01": {"101": "klq"}}


def test_update_reset_flags_compose_in_one_call(tmp_path: pathlib.Path) -> None:
    update_survey_overlap_state(
        tmp_path,
        {
            "color_coding_enabled": True,
            "surveys": {"KLQ": {"display_label": "Kurdish List", "display_color": "teal"}},
            "concept_survey_links": {"101": {"KLQ": "3.14"}},
            "speaker_choices": {"Saha01": {"101": "KLQ"}},
        },
    )

    state = update_survey_overlap_state(
        tmp_path,
        {
            "reset_surveys": True,
            "reset_speaker_choices": True,
            "reset_concept_survey_links": True,
            "color_coding_enabled": False,
        },
    )

    assert state == {
        "version": 1,
        "color_coding_enabled": False,
        "surveys": {},
        "concept_survey_links": {},
        "speaker_choices": {},
    }


def test_resolve_survey_for_speaker_uses_choice_then_legacy_default(tmp_path: pathlib.Path) -> None:
    state = update_survey_overlap_state(
        tmp_path,
        {
            "concept_survey_links": {"101": {"KLQ": "3.14", "JBIL": "139"}},
            "speaker_choices": {"Saha01": {"101": "JBIL"}},
        },
    )
    links = state["concept_survey_links"]["101"]

    assert resolve_survey_for_speaker("101", "Saha01", links, state, fallback_survey="KLQ") == ("jbil", "139")
    assert resolve_survey_for_speaker("101", "Khan01", links, state, fallback_survey="KLQ") == ("klq", "3.14")


def test_survey_sort_key_for_speaker_uses_resolved_source_item(tmp_path: pathlib.Path) -> None:
    state = update_survey_overlap_state(
        tmp_path,
        {
            "concept_survey_links": {
                "salt": {"KLQ": "3.14", "JBIL": "139"},
                "snow": {"KLQ": "3.13", "JBIL": "140"},
            },
            "speaker_choices": {"Speaker01": {"salt": "JBIL", "snow": "JBIL"}},
        },
    )

    salt_key = survey_sort_key_for_speaker("salt", "Speaker01", state["concept_survey_links"]["salt"], state, fallback_survey="KLQ")
    snow_key = survey_sort_key_for_speaker("snow", "Speaker01", state["concept_survey_links"]["snow"], state, fallback_survey="KLQ")

    assert salt_key < snow_key


def test_concepts_csv_round_trip_keeps_single_canonical_survey_id_not_display_label(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "concepts.csv"
    write_concepts_csv_rows(
        path,
        [
            {"id": "101", "concept_en": "salt", "source_item": "3.14", "source_survey": "KLQ", "custom_order": ""},
        ],
    )
    save_survey_overlap_state(
        tmp_path,
        update_survey_overlap_state(
            tmp_path,
            {"surveys": {"klq": {"display_label": "Bailey", "display_color": "amber"}}},
        ),
    )

    rows = read_concepts_csv_rows(path)
    assert rows == [{"id": "101", "concept_en": "salt", "source_item": "3.14", "source_survey": "KLQ", "custom_order": ""}]

    with path.open(newline="", encoding="utf-8") as handle:
        assert next(csv.DictReader(handle))["source_survey"] == "KLQ"
