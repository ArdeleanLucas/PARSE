import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.services.workspace_config import build_workspace_frontend_config


def test_build_workspace_frontend_config_merges_project_speakers_and_concepts(tmp_path: pathlib.Path) -> None:
    project = tmp_path
    (project / "project.json").write_text(
        json.dumps(
            {
                "project_id": "southern-kurdish-dialect-comparison",
                "name": "Southern Kurdish Dialect Comparison",
                "language": {"code": "sdh"},
                "speakers": {"Fail02": {}},
            }
        ),
        encoding="utf-8",
    )
    (project / "source_index.json").write_text(
        json.dumps({"speakers": {"Fail02": {}, "Kalh01": {}}}),
        encoding="utf-8",
    )
    with open(project / "concepts.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "ash"})
        writer.writerow({"id": "2", "concept_en": "bark"})

    result = build_workspace_frontend_config(project, {"chat": {"enabled": True}}, schema_version=7)

    assert result["project_name"] == "Southern Kurdish Dialect Comparison"
    assert result["language_code"] == "sdh"
    assert result["speakers"] == ["Fail02", "Kalh01"]
    assert result["audio_dir"] == "audio"
    assert result["annotations_dir"] == "annotations"
    assert result["schema_version"] == 7
    assert result["concepts"] == [
        {"id": "1", "label": "ash"},
        {"id": "2", "label": "bark"},
    ]


def test_build_workspace_frontend_config_preserves_config_defaults_when_project_fields_missing(tmp_path: pathlib.Path) -> None:
    (tmp_path / "project.json").write_text(json.dumps({}), encoding="utf-8")

    result = build_workspace_frontend_config(
        tmp_path,
        {
            "project_name": "Fallback Project",
            "language_code": "ckb",
            "audio_dir": "custom-audio",
            "annotations_dir": "custom-annotations",
        },
        schema_version=3,
    )

    assert result["project_name"] == "Fallback Project"
    assert result["language_code"] == "ckb"
    assert result["audio_dir"] == "custom-audio"
    assert result["annotations_dir"] == "custom-annotations"
    assert result["speakers"] == []
    assert result["concepts"] == []
    assert result["schema_version"] == 3


def test_build_workspace_frontend_config_projects_survey_overlap_sidecar(tmp_path: pathlib.Path) -> None:
    (tmp_path / "project.json").write_text(json.dumps({"speakers": ["Saha01", "Khan01"]}), encoding="utf-8")
    with open(tmp_path / "concepts.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"])
        writer.writeheader()
        writer.writerow({"id": "101", "concept_en": "salt", "source_item": "3.14", "source_survey": "KLQ", "custom_order": ""})
        writer.writerow({"id": "102", "concept_en": "water", "source_item": "3.15", "source_survey": "KLQ", "custom_order": ""})
    (tmp_path / "survey-overlap.json").write_text(
        json.dumps(
            {
                "color_coding_enabled": True,
                "surveys": {
                    "klq": {"display_label": "KLQ", "display_color": "indigo"},
                    "jbil": {"display_label": "Bailey", "display_color": "amber"},
                },
                "concept_survey_links": {"101": {"klq": "3.14", "jbil": "139"}},
                "speaker_choices": {"Saha01": {"101": "jbil"}},
            }
        ),
        encoding="utf-8",
    )

    result = build_workspace_frontend_config(tmp_path, {}, schema_version=8)

    assert result["survey_color_coding_enabled"] is True
    assert result["survey_settings"] == {
        "klq": {"display_label": "KLQ", "display_color": "indigo"},
        "jbil": {"display_label": "Bailey", "display_color": "amber"},
    }
    assert result["speaker_survey_choices"] == {"Saha01": {"101": "jbil"}}
    assert result["concepts"][0] == {
        "id": "101",
        "label": "salt",
        "source_item": "3.14",
        "source_survey": "KLQ",
        "surveys": {"klq": "3.14", "jbil": "139"},
    }
    assert result["concepts"][1] == {
        "id": "102",
        "label": "water",
        "source_item": "3.15",
        "source_survey": "KLQ",
        "surveys": {"klq": "3.15"},
    }
