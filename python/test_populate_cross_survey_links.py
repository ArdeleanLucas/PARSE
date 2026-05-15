from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "test_fixtures" / "cross_survey_links_workspace"
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "populate_cross_survey_links.py"


def copy_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE, workspace)
    return workspace


def run_script(*args: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_populate_cross_survey_links_dry_run_prints_json_without_writing(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    before = (workspace / "survey-overlap.json").read_text(encoding="utf-8")

    payload = run_script("--workspace", str(workspace), "--reference", str(workspace / "reference.csv"))

    assert set(payload) == {"matched", "would_add", "conflicts", "skipped_multiword"}
    assert payload["would_add"] == [
        {"concept_id": "1", "concept_en": "nose", "links": {"klq": "1.5"}},
        {"concept_id": "5", "concept_en": "stone", "links": {"klq": "5.0"}},
    ]
    assert (workspace / "survey-overlap.json").read_text(encoding="utf-8") == before


def test_populate_cross_survey_links_apply_writes_sidecar_and_is_idempotent(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)

    first = run_script("--workspace", str(workspace), "--reference", str(workspace / "reference.csv"), "--apply")
    state = json.loads((workspace / "survey-overlap.json").read_text(encoding="utf-8"))

    assert first["sidecar_diff"]["added"] == {"1": {"klq": "1.5"}, "5": {"klq": "5.0"}}
    assert state["concept_survey_links"]["1"] == {"klq": "1.5"}
    assert state["concept_survey_links"]["4"] == {"klq": "5.5"}
    assert state["concept_survey_links"]["5"] == {"klq": "5.0"}

    second = run_script("--workspace", str(workspace), "--reference", str(workspace / "reference.csv"), "--apply")

    assert second["would_add"] == []
    assert second["sidecar_diff"]["added"] == {}


def test_populate_cross_survey_links_replace_apply_resets_stale_sidecar_entries(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    sidecar_path = workspace / "survey-overlap.json"
    state = json.loads(sidecar_path.read_text(encoding="utf-8"))
    state["concept_survey_links"]["99"] = {"jbil": "999"}
    state["speaker_choices"] = {"speaker-a": {"1": "jbil"}}
    state["speaker_concept_survey_links"] = {"speaker-a": {"1": {"jbil": "10"}}}
    sidecar_path.write_text(json.dumps(state), encoding="utf-8")

    payload = run_script(
        "--workspace",
        str(workspace),
        "--reference",
        str(workspace / "reference.csv"),
        "--apply",
        "--replace",
    )
    replaced = json.loads(sidecar_path.read_text(encoding="utf-8"))

    assert payload["sidecar_diff"]["replace_mode"] is True
    assert payload["sidecar_diff"]["added"] == {"1": {"klq": "1.5"}, "5": {"klq": "5.0"}}
    assert replaced["concept_survey_links"] == {"1": {"klq": "1.5"}, "5": {"klq": "5.0"}}
    assert replaced["speaker_choices"] == {"speaker-a": {"1": "jbil"}}
    assert replaced["speaker_concept_survey_links"] == {"speaker-a": {"1": {"jbil": "10"}}}
