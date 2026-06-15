from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402


def test_write_json_file_round_trips_and_leaves_no_tmp(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "nested" / "out.json"
    payload = {"a": 1, "b": ["x", "y"], "unicode": "ɫ"}

    server._write_json_file(target, payload)

    assert json.loads(target.read_text(encoding="utf-8")) == payload
    # trailing newline preserved (unchanged from prior behavior)
    assert target.read_text(encoding="utf-8").endswith("\n")
    # the .tmp sidecar must not survive a successful write
    assert not (target.parent / "out.json.tmp").exists()
    assert sorted(p.name for p in target.parent.iterdir()) == ["out.json"]


def test_write_json_file_overwrites_existing_without_residue(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "out.json"

    server._write_json_file(target, {"v": 1})
    server._write_json_file(target, {"v": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}
    assert not (tmp_path / "out.json.tmp").exists()
