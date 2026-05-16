from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools import migrate_ai_config_ortho


LEGACY_ORTHO = {
    "backend": "hf",
    "model_path": "razhan/whisper-base-sdh",
    "language": "sd",
    "device": "cuda",
    "compute_type": "float16",
    "vad_filter": True,
    "vad_parameters": {"min_silence_duration_ms": 500, "threshold": 0.35},
    "condition_on_previous_text": False,
    "compression_ratio_threshold": 1.8,
    "no_repeat_ngram_size": 3,
    "repetition_penalty": 1.2,
    "initial_prompt": "هەڵۆ",
    "refine_lexemes": False,
    "provider": "faster-whisper",
}

EXPECTED_ORTHO = {
    "backend": "hf",
    "model": {
        "repo_id": "razhan/whisper-base-sdh",
        "device": "cuda",
    },
    "generation": {
        "language": "sd",
        "condition_on_prev_tokens": False,
        "compression_ratio_threshold": 1.8,
        "no_repeat_ngram_size": 3,
        "repetition_penalty": 1.2,
    },
    "decoding": {
        "initial_prompt": "هەڵۆ",
        "refine_lexemes": False,
    },
}


def _write_config(workspace: Path, ortho: dict) -> Path:
    config_dir = workspace / "config"
    config_dir.mkdir(parents=True)
    path = config_dir / "ai_config.json"
    path.write_text(
        json.dumps({"ortho": ortho, "llm": {"provider": "openai"}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_migrator_dry_run_does_not_modify_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_config(tmp_path, copy.deepcopy(LEGACY_ORTHO))
    before = path.read_text(encoding="utf-8")

    code = migrate_ai_config_ortho.main(["--workspace", str(tmp_path)])

    assert code == 0
    assert path.read_text(encoding="utf-8") == before
    assert "DRY-RUN" in capsys.readouterr().out
    assert not list(path.parent.glob("ai_config.json.bak-*"))


def test_migrator_rewrites_flat_schema_to_sectioned(tmp_path: Path) -> None:
    path = _write_config(tmp_path, copy.deepcopy(LEGACY_ORTHO))

    code = migrate_ai_config_ortho.main(["--workspace", str(tmp_path), "--apply"])

    assert code == 0
    migrated = _read(path)
    assert migrated["ortho"] == EXPECTED_ORTHO
    assert migrated["llm"] == {"provider": "openai"}


def test_migrator_drops_vad_keys_and_logs_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_config(tmp_path, copy.deepcopy(LEGACY_ORTHO))

    code = migrate_ai_config_ortho.main(["--workspace", str(tmp_path), "--apply"])

    assert code == 0
    out = capsys.readouterr().out
    assert "vad_filter: removed; VAD lives upstream in interval pipeline" in out
    assert "vad_parameters: removed; VAD lives upstream in interval pipeline" in out
    assert "vad_filter" not in _read(path)["ortho"]
    assert "vad_parameters" not in _read(path)["ortho"]


def test_migrator_drops_provider_key_and_logs_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_config(tmp_path, copy.deepcopy(LEGACY_ORTHO))

    code = migrate_ai_config_ortho.main(["--workspace", str(tmp_path), "--apply"])

    assert code == 0
    assert "provider: removed; redundant with `backend`" in capsys.readouterr().out
    assert "provider" not in _read(path)["ortho"]


def test_migrator_drops_compute_type_and_logs_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_config(tmp_path, copy.deepcopy(LEGACY_ORTHO))

    code = migrate_ai_config_ortho.main(["--workspace", str(tmp_path), "--apply"])

    assert code == 0
    migrated_ortho = _read(path)["ortho"]
    assert "compute_type" not in json.dumps(migrated_ortho)
    assert "dtype" not in json.dumps(migrated_ortho)
    assert "compute_type: removed; HF backend never honored it" in capsys.readouterr().out


def test_migrator_creates_backup_before_apply(tmp_path: Path) -> None:
    path = _write_config(tmp_path, copy.deepcopy(LEGACY_ORTHO))
    before = path.read_bytes()

    code = migrate_ai_config_ortho.main(["--workspace", str(tmp_path), "--apply"])

    assert code == 0
    backups = list(path.parent.glob("ai_config.json.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before


def test_migrator_idempotent_on_already_migrated_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_config(tmp_path, copy.deepcopy(EXPECTED_ORTHO))
    before = path.read_text(encoding="utf-8")

    code = migrate_ai_config_ortho.main(["--workspace", str(tmp_path), "--apply"])

    assert code == 0
    assert path.read_text(encoding="utf-8") == before
    assert "already uses the sectioned ORTH schema" in capsys.readouterr().out
    assert not list(path.parent.glob("ai_config.json.bak-*"))


def test_migrator_refuses_unknown_legacy_keys(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    legacy = copy.deepcopy(LEGACY_ORTHO)
    legacy["mystery_knob"] = True
    path = _write_config(tmp_path, legacy)
    before = path.read_text(encoding="utf-8")

    code = migrate_ai_config_ortho.main(["--workspace", str(tmp_path), "--apply"])

    assert code == 2
    assert path.read_text(encoding="utf-8") == before
    assert "mystery_knob" in capsys.readouterr().err
    assert not list(path.parent.glob("ai_config.json.bak-*"))
