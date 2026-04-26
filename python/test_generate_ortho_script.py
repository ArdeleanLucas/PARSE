from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_ortho.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("generate_ortho_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_ortho_model_path_accepts_explicit_local_path(tmp_path: pathlib.Path):
    module = _load_script_module()
    model_dir = tmp_path / "razhan-ct2"
    model_dir.mkdir()

    resolved = module.resolve_ortho_model_path(str(model_dir), None)

    assert resolved == str(model_dir)


def test_resolve_ortho_model_path_rejects_hf_repo_id():
    module = _load_script_module()

    with pytest.raises(SystemExit, match="HuggingFace repo id"):
        module.resolve_ortho_model_path("razhan/whisper-base-sdh", None)


def test_resolve_ortho_model_path_reads_config_when_explicit_missing(tmp_path: pathlib.Path):
    module = _load_script_module()
    model_dir = tmp_path / "razhan-ct2"
    model_dir.mkdir()
    config_path = tmp_path / "ai_config.json"
    config_path.write_text(
        json.dumps({"ortho": {"model_path": str(model_dir)}}),
        encoding="utf-8",
    )

    resolved = module.resolve_ortho_model_path(None, config_path)

    assert resolved == str(model_dir)


def test_resolve_ortho_model_path_rejects_empty_config_value(tmp_path: pathlib.Path):
    module = _load_script_module()
    config_path = tmp_path / "ai_config.json"
    config_path.write_text(json.dumps({"ortho": {"model_path": ""}}), encoding="utf-8")

    with pytest.raises(SystemExit, match=r"ortho\.model_path is empty"):
        module.resolve_ortho_model_path(None, config_path)


def test_build_transcribe_kwargs_uses_ortho_guard_defaults():
    module = _load_script_module()

    kwargs = module.build_transcribe_kwargs(
        {
            "language": "sd",
            "beam_size": 5,
            "vad_filter": True,
            "vad_parameters": {
                "min_silence_duration_ms": 500,
                "threshold": 0.35,
            },
            "condition_on_previous_text": False,
            "compression_ratio_threshold": 1.8,
            "initial_prompt": "",
        }
    )

    assert kwargs["language"] == "sd"
    assert kwargs["beam_size"] == 5
    assert kwargs["vad_filter"] is True
    assert kwargs["vad_parameters"] == {
        "min_silence_duration_ms": 500,
        "threshold": 0.35,
    }
    assert kwargs["condition_on_previous_text"] is False
    assert kwargs["compression_ratio_threshold"] == 1.8
    assert "initial_prompt" not in kwargs


def test_build_transcribe_kwargs_respects_vad_disable_and_prompt_override():
    module = _load_script_module()

    kwargs = module.build_transcribe_kwargs(
        {
            "language": "sd",
            "beam_size": 7,
            "vad_filter": False,
            "vad_parameters": {"threshold": 0.99},
            "condition_on_previous_text": True,
            "compression_ratio_threshold": 2.4,
            "initial_prompt": "known word list",
        }
    )

    assert kwargs["beam_size"] == 7
    assert kwargs["vad_filter"] is False
    assert "vad_parameters" not in kwargs
    assert kwargs["condition_on_previous_text"] is True
    assert kwargs["compression_ratio_threshold"] == 2.4
    assert kwargs["initial_prompt"] == "known word list"
