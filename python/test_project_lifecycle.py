"""Unit tests for app.services.project_lifecycle.

Dependency-free: imports only the lifecycle helper and uses pytest's tmp_path.
No server.py, no torch/faster-whisper, so these run locally on any machine.
"""
from __future__ import annotations

import json
import os

import pytest

from app.services.project_lifecycle import (
    STANDARD_SUBDIRS,
    bootstrap_project,
    describe_project,
)


def _read_project_json(project_root):
    return json.loads((project_root / "project.json").read_text(encoding="utf-8"))


def test_bootstrap_on_empty_dir_creates_valid_project_json(tmp_path):
    project_root = tmp_path / "MyProject"
    project_root.mkdir()

    summary = bootstrap_project(project_root)

    assert summary["created"] is True
    assert summary["name"] == "MyProject"
    assert summary["project_json_path"] == str(project_root / "project.json")

    payload = _read_project_json(project_root)
    # Minimal valid schema: name + version + a speakers block.
    assert payload["name"] == "MyProject"
    assert payload["version"] == 1
    assert payload["speakers"] == {}


def test_bootstrap_creates_all_standard_subdirs(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()

    bootstrap_project(project_root)

    for subdir in STANDARD_SUBDIRS:
        assert (project_root / subdir).is_dir(), f"missing subdir {subdir}"
    # Spot-check the nested audio layout explicitly.
    assert (project_root / "audio" / "original").is_dir()
    assert (project_root / "audio" / "working").is_dir()


def test_bootstrap_creates_root_when_missing(tmp_path):
    # A non-existent directory is materialized (idempotent mkdir parents=True).
    project_root = tmp_path / "brand-new"
    assert not project_root.exists()

    summary = bootstrap_project(project_root)

    assert summary["created"] is True
    assert project_root.is_dir()
    assert (project_root / "project.json").exists()


def test_bootstrap_is_idempotent_and_does_not_overwrite(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()

    # First bootstrap, then inject a sentinel key into the existing file.
    bootstrap_project(project_root)
    existing = _read_project_json(project_root)
    existing["sentinel"] = "keep-me"
    existing["speakers"] = {"Spk01": {"marker": True}}
    (project_root / "project.json").write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Re-running must NOT overwrite the existing project.json.
    summary = bootstrap_project(project_root)

    assert summary["created"] is False
    preserved = _read_project_json(project_root)
    assert preserved["sentinel"] == "keep-me"
    assert preserved["speakers"] == {"Spk01": {"marker": True}}


def test_bootstrap_heals_missing_subdirs_without_touching_project_json(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    bootstrap_project(project_root)

    # Remove a subdir to simulate a partially-created project.
    (project_root / "exports").rmdir()
    assert not (project_root / "exports").exists()

    summary = bootstrap_project(project_root)

    assert summary["created"] is False
    assert (project_root / "exports").is_dir()


def test_describe_project_with_project_json(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "project.json").write_text(
        json.dumps({"name": "Named In File", "speakers": {}}) + "\n",
        encoding="utf-8",
    )

    desc = describe_project(project_root)

    assert desc["root"] == str(project_root)
    assert desc["name"] == "Named In File"  # read from project.json, not dir name
    assert desc["hasProjectJson"] is True
    assert desc["valid"] is True


def test_describe_project_empty_dir_without_project_json(tmp_path):
    project_root = tmp_path / "EmptyPick"
    project_root.mkdir()

    desc = describe_project(project_root)

    assert desc["name"] == "EmptyPick"  # falls back to dir name
    assert desc["hasProjectJson"] is False
    # An empty dir the app can initialize counts as valid.
    assert desc["valid"] is True


def test_describe_project_nonempty_dir_without_project_json_is_invalid(tmp_path):
    project_root = tmp_path / "NotAProject"
    project_root.mkdir()
    (project_root / "random.txt").write_text("hello", encoding="utf-8")

    desc = describe_project(project_root)

    assert desc["hasProjectJson"] is False
    assert desc["valid"] is False


def test_describe_project_nonexistent_dir_is_invalid(tmp_path):
    project_root = tmp_path / "does-not-exist"

    desc = describe_project(project_root)

    assert desc["hasProjectJson"] is False
    assert desc["valid"] is False
    assert desc["name"] == "does-not-exist"


def test_describe_project_falls_back_to_dir_name_when_json_name_blank(tmp_path):
    project_root = tmp_path / "FallbackName"
    project_root.mkdir()
    (project_root / "project.json").write_text(
        json.dumps({"name": "", "speakers": {}}) + "\n",
        encoding="utf-8",
    )

    desc = describe_project(project_root)

    assert desc["name"] == "FallbackName"


def test_describe_after_bootstrap_is_valid(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    bootstrap_project(project_root)

    desc = describe_project(project_root)

    assert desc["hasProjectJson"] is True
    assert desc["valid"] is True
    assert desc["name"] == "proj"
    assert desc["corrupt"] is False


def test_describe_corrupt_project_json_is_invalid_and_flagged(tmp_path):
    project_root = tmp_path / "Corrupt"
    project_root.mkdir()
    (project_root / "project.json").write_text("{ not json", encoding="utf-8")

    desc = describe_project(project_root)

    assert desc["hasProjectJson"] is True
    assert desc["valid"] is False
    assert desc["corrupt"] is True
    # Name resolution tolerates the failed parse and falls back to the dir name.
    assert desc["name"] == "Corrupt"


def test_bootstrap_leaves_corrupt_project_json_untouched(tmp_path):
    # A corrupt file may be manually recoverable; bootstrap must not overwrite it.
    project_root = tmp_path / "Corrupt"
    project_root.mkdir()
    corrupt_text = "{ not json"
    (project_root / "project.json").write_text(corrupt_text, encoding="utf-8")

    summary = bootstrap_project(project_root)

    assert summary["created"] is False
    assert summary["error"] is None
    assert (project_root / "project.json").read_text(encoding="utf-8") == corrupt_text


def test_bootstrap_atomic_write_result_and_no_leftover_temp(tmp_path):
    project_root = tmp_path / "Atomic"
    project_root.mkdir()

    summary = bootstrap_project(project_root)

    assert summary["created"] is True
    assert summary["error"] is None
    # The written file parses to the expected minimal dict.
    payload = _read_project_json(project_root)
    assert payload == {"name": "Atomic", "version": 1, "speakers": {}}
    # No leftover atomic-write temp file.
    assert not (project_root / "project.json.tmp").exists()
    leftovers = [p.name for p in project_root.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_describe_hidden_file_only_dir_is_valid(tmp_path):
    # A freshly-picked macOS folder containing only .DS_Store is still valid.
    project_root = tmp_path / "FreshPick"
    project_root.mkdir()
    (project_root / ".DS_Store").write_text("cruft", encoding="utf-8")

    desc = describe_project(project_root)

    assert desc["hasProjectJson"] is False
    assert desc["valid"] is True
    assert desc["corrupt"] is False


def test_bootstrap_whitespace_only_name_falls_back_to_dir_name(tmp_path):
    project_root = tmp_path / "WhitespaceName"
    project_root.mkdir()
    (project_root / "project.json").write_text(
        json.dumps({"name": "   ", "speakers": {}}) + "\n",
        encoding="utf-8",
    )

    summary = bootstrap_project(project_root)
    assert summary["name"] == "WhitespaceName"

    desc = describe_project(project_root)
    assert desc["name"] == "WhitespaceName"


@pytest.mark.skipif(
    os.geteuid() == 0 if hasattr(os, "geteuid") else True,
    reason="chmod-based permission denial is ineffective as root / on non-POSIX",
)
def test_bootstrap_on_unwritable_dir_returns_error_and_does_not_raise(tmp_path):
    parent = tmp_path / "readonly"
    parent.mkdir()
    os.chmod(parent, 0o500)  # r-x: cannot create children
    try:
        target = parent / "child-project"
        summary = bootstrap_project(target)
    finally:
        os.chmod(parent, 0o700)  # restore so tmp_path cleanup succeeds

    assert summary["created"] is False
    assert summary["error"] is not None
    assert not target.exists()
