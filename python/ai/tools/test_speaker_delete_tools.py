from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ChatToolValidationError, ParseChatTools
from ai.tools.speaker_delete_tools import tool_delete_speaker


def _write_json(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_workspace(root: pathlib.Path, speaker: str = "Saha01") -> None:
    _write_json(root / "annotations" / "{0}.parse.json".format(speaker), {"speaker": speaker})
    (root / "audio" / "original" / speaker).mkdir(parents=True, exist_ok=True)
    (root / "audio" / "original" / speaker / "source.wav").write_bytes(b"RIFF")
    _write_json(root / "project.json", {"speakers": {speaker: {}, "Other01": {}}})
    _write_json(root / "source_index.json", {"speakers": {speaker: {"source_wavs": []}}})


def test_delete_speaker_dry_run_lists_plan(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    envelope = ParseChatTools(project_root=tmp_path).execute(
        "delete_speaker", {"speaker": "Saha01", "dryRun": True}
    )
    assert envelope["tool"] == "delete_speaker"
    result = envelope["result"]
    assert result["dryRun"] is True
    assert "annotations/Saha01.parse.json" in result["plannedFiles"]
    # Nothing removed on dry-run.
    assert (tmp_path / "annotations" / "Saha01.parse.json").exists()


def test_delete_speaker_executes(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    result = tool_delete_speaker(
        ParseChatTools(project_root=tmp_path), {"speaker": "Saha01", "dryRun": False}
    )
    assert result["ok"] is True
    assert result["dryRun"] is False
    assert not (tmp_path / "annotations" / "Saha01.parse.json").exists()
    project = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert "Saha01" not in project["speakers"]


def test_delete_unknown_speaker_raises_validation(tmp_path: pathlib.Path) -> None:
    _make_workspace(tmp_path)
    with pytest.raises(ChatToolValidationError):
        tool_delete_speaker(
            ParseChatTools(project_root=tmp_path), {"speaker": "Ghost42", "dryRun": False}
        )
