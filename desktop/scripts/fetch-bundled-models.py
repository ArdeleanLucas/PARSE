#!/usr/bin/env python3
"""fetch-bundled-models.py — stage the read-only bundled IPA model for packaging.

Downloads the wav2vec2 IPA acoustic model from the Hugging Face Hub into a
build-staging directory and writes a `manifest.json` so the result is a valid
model-pack that the backend registry (python/ai/model_registry.py) discovers.

This runs at BUILD time (in CI, before electron-builder assembles the DMG). The
output directory `dist/bundled-models/<id>/` is NOT committed to the repo;
electron-builder copies its CONTENTS into the app's `Resources/models/`.

Layout produced:
    <dest-root>/<id>/            (default dest-root: dist/bundled-models)
        manifest.json           (written here)
        <model files...>        (downloaded via snapshot_download)

The manifest schema is kept EXACTLY in sync with
python/ai/model_registry.py::parse_manifest — schema_version 1, stage in
{stt,ipa,ortho}, format in {faster-whisper-ct2,hf-transformers}, required keys
{schema_version,id,name,stage,format,entrypoint}. `format: hf-transformers` is
what wav2vec2 / from_pretrained consumes.

Everything is parameterizable so the script is reusable for other bundled packs:
    --repo-id      HF repo (default: facebook/wav2vec2-xlsr-53-espeak-cv-ft)
    --id           model-pack slug / directory name (default: wav2vec2-xlsr-53-espeak-ipa)
    --dest-root    staging root (default: dist/bundled-models; also PARSE_BUNDLED_MODELS_STAGE)
    --stage        pipeline stage (default: ipa)
    --format       model format (default: hf-transformers)
    --name         human-readable name
    --version      manifest version (default: 1.0.0)
    --manifest-only  write ONLY the manifest (no download) — used by tests to
                     validate the generated manifest against the registry rules.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


# Defaults for the one model we bundle today (hybrid-delivery decision §9.4).
DEFAULT_REPO_ID = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
DEFAULT_ID = "wav2vec2-xlsr-53-espeak-ipa"
DEFAULT_NAME = "wav2vec2 XLSR-53 espeak (IPA)"
DEFAULT_STAGE = "ipa"
DEFAULT_FORMAT = "hf-transformers"
DEFAULT_ENGINE = "wav2vec2"
DEFAULT_VERSION = "1.0.0"
DEFAULT_DEST_ROOT = "dist/bundled-models"


def build_manifest(args: argparse.Namespace) -> dict:
    """Assemble the manifest dict. Kept in sync with model_registry.parse_manifest.

    `entrypoint: "."` means the model directory itself is the from_pretrained
    source (the registry resolves it to an absolute path under the model dir).
    `languages: ["*"]` marks the IPA acoustic model as language-agnostic.
    """
    return {
        "schema_version": 1,
        "id": args.id,
        "name": args.name,
        "stage": args.stage,
        "format": args.format,
        "engine": args.engine,
        "languages": ["*"],
        "entrypoint": ".",
        "version": args.version,
        "source": {"type": "bundled", "ref": args.repo_id},
    }


def write_manifest(model_dir: Path, manifest: dict) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = model_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest_path


def download_model(repo_id: str, model_dir: Path) -> None:
    """snapshot_download the HF repo into the model directory.

    Imported lazily so `--manifest-only` (and this module's import in tests) does
    not require huggingface_hub to be installed.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit(
            "huggingface_hub is required to download the bundled model. "
            "Install it (pip install huggingface_hub) or pass --manifest-only."
        ) from exc

    model_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo_id, local_dir=str(model_dir))


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=os.environ.get("PARSE_BUNDLED_MODEL_REPO", DEFAULT_REPO_ID))
    parser.add_argument("--id", default=os.environ.get("PARSE_BUNDLED_MODEL_ID", DEFAULT_ID))
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--stage", default=DEFAULT_STAGE)
    parser.add_argument("--format", default=DEFAULT_FORMAT, dest="format")
    parser.add_argument("--engine", default=DEFAULT_ENGINE)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--dest-root",
        default=os.environ.get("PARSE_BUNDLED_MODELS_STAGE", DEFAULT_DEST_ROOT),
        help="staging root; the model lands at <dest-root>/<id>/",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="write only manifest.json (skip the download) — for tests / dry runs",
    )
    return parser.parse_args(argv)


def main(argv: list) -> int:
    args = parse_args(argv)

    dest_root = Path(args.dest_root)
    model_dir = dest_root / args.id

    manifest = build_manifest(args)

    if not args.manifest_only:
        print(f"[fetch-bundled-models] downloading {args.repo_id} -> {model_dir}", flush=True)
        download_model(args.repo_id, model_dir)

    manifest_path = write_manifest(model_dir, manifest)
    print(f"[fetch-bundled-models] wrote manifest {manifest_path}", flush=True)
    print(f"[fetch-bundled-models] staged model id={args.id} stage={args.stage} at {model_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
