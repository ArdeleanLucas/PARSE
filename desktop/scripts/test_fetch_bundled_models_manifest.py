"""test_fetch_bundled_models_manifest.py — validate the bundled-model manifest.

The fetch script's ``--manifest-only`` mode writes just ``manifest.json`` (no
download), which lets us prove — without huggingface_hub or any network — that
the manifest it generates satisfies the backend model registry's rules
(``python/ai/model_registry.py::parse_manifest``): schema_version 1, a valid
``stage`` and ``format`` enum, and every required key present.

Run from the repo root:
    PYTHONPATH=python python3 -m pytest desktop/scripts/test_fetch_bundled_models_manifest.py -q
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

# Import the registry the same way python/test_model_registry.py does: add the
# python/ dir to sys.path and import the `ai` package.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "python"))

from ai import model_registry  # noqa: E402

_FETCH_SCRIPT = pathlib.Path(__file__).resolve().parent / "fetch-bundled-models.py"


def _run_manifest_only(dest_root: pathlib.Path, *extra: str) -> pathlib.Path:
    """Invoke the fetch script in --manifest-only mode; return the manifest path."""
    subprocess.run(
        [sys.executable, str(_FETCH_SCRIPT), "--manifest-only", "--dest-root", str(dest_root), *extra],
        check=True,
        capture_output=True,
        text=True,
    )
    # Discover the single <id>/manifest.json the script wrote.
    manifests = list(dest_root.glob("*/manifest.json"))
    assert len(manifests) == 1, f"expected one manifest, found {manifests}"
    return manifests[0]


def test_default_manifest_validates_against_parse_manifest(tmp_path):
    manifest_path = _run_manifest_only(tmp_path)

    parsed = model_registry.parse_manifest(manifest_path)

    assert parsed.schema_version == model_registry.SCHEMA_VERSION
    assert parsed.stage in model_registry.VALID_STAGES
    assert parsed.format in model_registry.VALID_FORMATS
    # The bundled IPA core: an hf-transformers ipa pack whose entrypoint resolves
    # to the model directory itself (entrypoint ".").
    assert parsed.stage == "ipa"
    assert parsed.format == "hf-transformers"
    assert parsed.entrypoint_path == manifest_path.parent.resolve()
    # id matches the directory name (parse_manifest prefers the dir name).
    assert parsed.id == manifest_path.parent.name


def test_manifest_only_does_not_download(tmp_path):
    manifest_path = _run_manifest_only(tmp_path)
    # --manifest-only must write ONLY the manifest — no model payload files.
    siblings = [p.name for p in manifest_path.parent.iterdir()]
    assert siblings == ["manifest.json"], f"unexpected extra files: {siblings}"


def test_custom_stage_and_format_still_validate(tmp_path):
    # The script is parameterizable for other packs; a faster-whisper STT pack
    # must also validate (proves the enums line up, not just the IPA defaults).
    manifest_path = _run_manifest_only(
        tmp_path,
        "--id",
        "whisper-standard-stt",
        "--name",
        "Standard STT",
        "--stage",
        "stt",
        "--format",
        "faster-whisper-ct2",
        "--engine",
        "faster-whisper",
    )

    parsed = model_registry.parse_manifest(manifest_path)
    assert parsed.stage == "stt"
    assert parsed.format == "faster-whisper-ct2"


def test_invalid_stage_is_rejected_by_registry(tmp_path):
    # A bogus stage must make the generated manifest fail registry validation —
    # confirming the test is actually exercising parse_manifest's enum guard.
    manifest_path = _run_manifest_only(tmp_path, "--stage", "not-a-real-stage")
    with pytest.raises(model_registry.ManifestError):
        model_registry.parse_manifest(manifest_path)
