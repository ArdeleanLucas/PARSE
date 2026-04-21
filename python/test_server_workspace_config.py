import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


def test_workspace_frontend_config_merges_project_speakers_and_concepts(tmp_path, monkeypatch) -> None:
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

    monkeypatch.setattr(server, "_project_root", lambda: project)

    result = server._workspace_frontend_config({"chat": {"enabled": True}})

    assert result["project_name"] == "Southern Kurdish Dialect Comparison"
    assert result["language_code"] == "sdh"
    assert result["speakers"] == ["Fail02", "Kalh01"]
    assert result["audio_dir"] == "audio"
    assert result["annotations_dir"] == "annotations"
    assert result["concepts"] == [
        {"id": "1", "label": "ash"},
        {"id": "2", "label": "bark"},
    ]
