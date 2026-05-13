"""Regression tests for the one-shot source-audio duration backfill."""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import soundfile as sf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tests.fixtures.audio_synth import build_synthetic_long_wav  # noqa: E402


def _write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_workspace(
    root: pathlib.Path,
    speaker: str,
    *,
    wav_name: str = "source.wav",
    actual_duration: float = 2.0,
    stored_duration: float = 120.0,
    write_wav: bool = True,
) -> pathlib.Path:
    annotation_path = root / "annotations" / f"{speaker}.parse.json"
    _write_json(
        annotation_path,
        {
            "speaker": speaker,
            "source_audio": wav_name,
            "source_audio_duration_sec": stored_duration,
            "tiers": {},
        },
    )
    source_index_path = root / "source_index.json"
    if source_index_path.is_file():
        source_index = _read_json(source_index_path)
    else:
        source_index = {"speakers": {}}
    source_index.setdefault("speakers", {})[speaker] = {
        "source_wavs": [
            {"filename": wav_name, "is_primary": True},
        ],
    }
    _write_json(source_index_path, source_index)
    if write_wav:
        build_synthetic_long_wav(
            actual_duration,
            speech_pattern="tile",
            output_path=root / "audio" / "working" / speaker / wav_name,
        )
    return annotation_path


def _run_backfill(capsys, *args: str) -> tuple[int, list[dict[str, Any]]]:
    from scripts import backfill_source_audio_duration

    exit_code = backfill_source_audio_duration.main(list(args))
    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.out.splitlines() if line.strip()]
    return exit_code, records


class Test_backfill_duration:
    def test_dry_run_reports_drift_but_does_not_write(self, tmp_path: pathlib.Path, capsys) -> None:
        annotation_path = _build_workspace(tmp_path, "Fail01", actual_duration=2.0, stored_duration=120.0)
        before = annotation_path.read_text(encoding="utf-8")

        exit_code, records = _run_backfill(capsys, "--workspace", str(tmp_path), "--dry-run")

        assert exit_code == 0
        assert records == [
            {
                "speaker": "Fail01",
                "status": "ok",
                "old_duration": 120.0,
                "new_duration": 2.0,
                "drift_sec": 118.0,
                "would_write": True,
            }
        ]
        assert annotation_path.read_text(encoding="utf-8") == before


    def test_writes_corrected_value_when_drift_exceeds_tolerance(self, tmp_path: pathlib.Path, capsys) -> None:
        annotation_path = _build_workspace(tmp_path, "Fail01", actual_duration=2.0, stored_duration=120.0)

        exit_code, records = _run_backfill(capsys, "--workspace", str(tmp_path))

        assert exit_code == 0
        assert records[0]["speaker"] == "Fail01"
        assert records[0]["status"] == "ok"
        assert records[0]["would_write"] is False
        actual_duration = float(sf.info(str(tmp_path / "audio" / "working" / "Fail01" / "source.wav")).duration)
        stored = float(_read_json(annotation_path)["source_audio_duration_sec"])
        assert abs(stored - actual_duration) < 0.01


    def test_no_op_when_within_tolerance(self, tmp_path: pathlib.Path, capsys) -> None:
        annotation_path = _build_workspace(tmp_path, "Fail01", actual_duration=2.0, stored_duration=2.5)
        before = annotation_path.read_text(encoding="utf-8")

        exit_code, records = _run_backfill(capsys, "--workspace", str(tmp_path))

        assert exit_code == 0
        assert records[0]["status"] == "skipped"
        assert records[0]["would_write"] is False
        assert annotation_path.read_text(encoding="utf-8") == before


    def test_idempotent_second_run(self, tmp_path: pathlib.Path, capsys) -> None:
        _build_workspace(tmp_path, "Fail01", actual_duration=2.0, stored_duration=120.0)

        first_exit, first_records = _run_backfill(capsys, "--workspace", str(tmp_path))
        second_exit, second_records = _run_backfill(capsys, "--workspace", str(tmp_path))

        assert first_exit == 0
        assert first_records[0]["status"] == "ok"
        assert second_exit == 0
        assert second_records[0]["status"] == "skipped"
        assert not any(record["would_write"] for record in second_records)


    def test_missing_wav_reports_but_does_not_error(self, tmp_path: pathlib.Path, capsys) -> None:
        _build_workspace(tmp_path, "Fail01", stored_duration=120.0, write_wav=False)

        exit_code, records = _run_backfill(capsys, "--workspace", str(tmp_path))

        assert exit_code == 0
        assert records == [
            {
                "speaker": "Fail01",
                "status": "missing_wav",
                "old_duration": 120.0,
                "new_duration": None,
                "drift_sec": None,
                "would_write": False,
            }
        ]


    def test_speaker_filter_limits_scope(self, tmp_path: pathlib.Path, capsys) -> None:
        fail01_annotation = _build_workspace(tmp_path, "Fail01", actual_duration=2.0, stored_duration=120.0)
        fail02_annotation = _build_workspace(tmp_path, "Fail02", actual_duration=3.0, stored_duration=300.0)
        fail02_before = fail02_annotation.read_text(encoding="utf-8")

        exit_code, records = _run_backfill(capsys, "--workspace", str(tmp_path), "--speaker", "Fail01")

        assert exit_code == 0
        assert [record["speaker"] for record in records] == ["Fail01"]
        assert float(_read_json(fail01_annotation)["source_audio_duration_sec"]) == 2.0
        assert fail02_annotation.read_text(encoding="utf-8") == fail02_before
