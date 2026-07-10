"""model_registry.py - Read/resolve core for PARSE's desktop model registry.

This module scans two model roots, parses/validates per-model manifests, lists
installed models, and resolves a pipeline stage (stt/ipa/ortho) to a concrete
local model directory that the existing loaders consume.

Design constraints (Gate B, §9.4):

  * **Dependency-light and importable without torch.** This Mac's python lacks
    torch; the frozen desktop backend loads this module during route dispatch.
    Keep it stdlib-only and keep any heavy imports out of the module top level.
  * **Additive, web-unchanged.** When neither root is present (the web product's
    default: no ``PARSE_BUNDLED_MODELS``, no ``PARSE_USER_DATA``), every function
    here short-circuits to an empty scan / ``None`` resolution, so the loaders it
    wires into behave EXACTLY as before this module existed.

Two model roots (mirrors the ``PARSE_BUNDLED_BIN`` pattern in
``python/shared/ffmpeg_discovery.py``):

  * Bundled (read-only): env ``PARSE_BUNDLED_MODELS`` → a directory. In the
    frozen app this is ``<resourcesPath>/models``. Unset / absent → skipped.
  * User (writable): ``PARSE_USER_DATA/models/`` (env ``PARSE_USER_DATA`` is set
    by the Electron shell). Unset / absent → skipped.

Each installed model is a subdirectory ``<id>/`` containing ``manifest.json`` +
model files. See ``ModelManifest`` / ``parse_manifest`` for the schema.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# Env var names, exported so callers and docs share one source of truth. These
# intentionally mirror the ``PARSE_BUNDLED_BIN`` / ``PARSE_USER_DATA`` style.
BUNDLED_MODELS_ENV = "PARSE_BUNDLED_MODELS"
USER_DATA_ENV = "PARSE_USER_DATA"

# Manifest constraints.
SCHEMA_VERSION = 1
VALID_STAGES = frozenset({"stt", "ipa", "ortho"})
VALID_FORMATS = frozenset({"faster-whisper-ct2", "hf-transformers"})

# Required manifest keys (before defaulting/coercion).
_REQUIRED_KEYS = ("schema_version", "id", "name", "stage", "format", "entrypoint")


class ManifestError(ValueError):
    """Raised by :func:`parse_manifest` when a manifest is malformed.

    :func:`list_models` catches this per-directory so one bad manifest logs a
    warning and is skipped rather than crashing the whole scan.
    """


def _warn(message: str) -> None:
    """Emit a non-fatal warning to stderr (stdlib-only; no logging config)."""
    print("[model_registry] {0}".format(message), file=sys.stderr, flush=True)


@dataclass
class ModelManifest:
    """Validated, resolved view of a single ``manifest.json``.

    ``entrypoint_path`` is resolved to an ABSOLUTE directory (or file) under the
    model directory — this is what the loaders consume as a local model source.
    """

    schema_version: int
    id: str
    name: str
    stage: str
    format: str
    entrypoint: str
    entrypoint_path: Path
    model_dir: Path
    engine: str = ""
    languages: List[str] = field(default_factory=list)
    version: str = ""
    source: Dict[str, Any] = field(default_factory=dict)
    size_bytes: Optional[int] = None


@dataclass
class ModelRecord:
    """A single resolved, listable model record (one installed model)."""

    id: str
    name: str
    stage: str
    format: str
    engine: str
    languages: List[str]
    entrypoint_path: str  # absolute path, str for JSON serializability
    source: Dict[str, Any]
    size_bytes: int
    removable: bool
    root: str  # "bundled" | "user"
    version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable dict for the HTTP read routes."""
        return {
            "id": self.id,
            "name": self.name,
            "stage": self.stage,
            "format": self.format,
            "engine": self.engine,
            "languages": list(self.languages),
            "entrypoint_path": self.entrypoint_path,
            "source": dict(self.source),
            "size_bytes": self.size_bytes,
            "removable": self.removable,
            "root": self.root,
            "version": self.version,
        }


def _root_dir_from_env(env_var: str, *, subdir: Optional[str] = None) -> Optional[Path]:
    """Resolve a model root from an env var; ``None`` when unset or absent.

    Small tested helper: ``env → path`` (optionally joined with ``subdir``).
    Returns ``None`` if the env var is unset/blank or the resolved directory
    does not exist, so callers can treat "no root" uniformly.
    """
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    if subdir:
        root = root / subdir
    if not root.is_dir():
        return None
    return root


def bundled_models_root() -> Optional[Path]:
    """Read-only bundled models root (``PARSE_BUNDLED_MODELS``) or ``None``."""
    return _root_dir_from_env(BUNDLED_MODELS_ENV)


def user_models_root() -> Optional[Path]:
    """Writable user models root (``PARSE_USER_DATA/models``) or ``None``."""
    return _root_dir_from_env(USER_DATA_ENV, subdir="models")


def _coerce_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coerce_languages(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _dir_size_bytes(directory: Path) -> int:
    """Sum file sizes under ``directory`` (best-effort; skips unreadable files)."""
    total = 0
    try:
        for entry in directory.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return 0
    return total


def parse_manifest(path: Path) -> ModelManifest:
    """Parse and validate a single ``manifest.json``.

    Validates required fields, coerces/validates ``stage`` and ``format``,
    resolves ``entrypoint`` to an absolute path under the model directory, and
    warns (preferring the directory name) when ``id`` disagrees with the parent
    directory name.

    Raises:
        ManifestError: for missing/invalid JSON or any failed constraint. The
            scan in :func:`list_models` catches this and skips the directory.
    """
    manifest_path = Path(path)
    model_dir = manifest_path.parent

    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError("cannot read {0}: {1}".format(manifest_path, exc)) from exc

    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ManifestError("invalid JSON in {0}: {1}".format(manifest_path, exc)) from exc

    if not isinstance(data, dict):
        raise ManifestError("manifest {0} is not a JSON object".format(manifest_path))

    missing = [key for key in _REQUIRED_KEYS if data.get(key) in (None, "")]
    if missing:
        raise ManifestError(
            "manifest {0} missing required field(s): {1}".format(
                manifest_path, ", ".join(missing)
            )
        )

    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ManifestError(
            "manifest {0} has unsupported schema_version {1!r} (expected {2})".format(
                manifest_path, schema_version, SCHEMA_VERSION
            )
        )

    stage = _coerce_str(data.get("stage")).lower()
    if stage not in VALID_STAGES:
        raise ManifestError(
            "manifest {0} has invalid stage {1!r} (expected one of {2})".format(
                manifest_path, data.get("stage"), sorted(VALID_STAGES)
            )
        )

    fmt = _coerce_str(data.get("format")).lower()
    if fmt not in VALID_FORMATS:
        raise ManifestError(
            "manifest {0} has invalid format {1!r} (expected one of {2})".format(
                manifest_path, data.get("format"), sorted(VALID_FORMATS)
            )
        )

    manifest_id = _coerce_str(data.get("id"))
    dir_name = model_dir.name
    if manifest_id != dir_name:
        # The directory name is authoritative (it's what a caller de-dupes and
        # binds by). Warn and prefer it so a copy/rename can't desync the id.
        _warn(
            "manifest id {0!r} != directory name {1!r} in {2}; using directory name".format(
                manifest_id, dir_name, manifest_path
            )
        )
        manifest_id = dir_name

    entrypoint = _coerce_str(data.get("entrypoint")) or "."
    # Resolve to an absolute path under the model dir. Reject traversal that
    # escapes the model directory — a malformed manifest must not point the
    # loader at an arbitrary filesystem location.
    entrypoint_path = (model_dir / entrypoint).resolve()
    try:
        entrypoint_path.relative_to(model_dir.resolve())
    except ValueError as exc:
        raise ManifestError(
            "manifest {0} entrypoint {1!r} escapes the model directory".format(
                manifest_path, entrypoint
            )
        ) from exc

    size_bytes = data.get("size_bytes")
    if not isinstance(size_bytes, int) or size_bytes < 0:
        size_bytes = None

    source = data.get("source")
    if not isinstance(source, dict):
        source = {}

    return ModelManifest(
        schema_version=SCHEMA_VERSION,
        id=manifest_id,
        name=_coerce_str(data.get("name")),
        stage=stage,
        format=fmt,
        entrypoint=entrypoint,
        entrypoint_path=entrypoint_path,
        model_dir=model_dir,
        engine=_coerce_str(data.get("engine")),
        languages=_coerce_languages(data.get("languages")),
        version=_coerce_str(data.get("version")),
        source=source,
        size_bytes=size_bytes,
    )


def _scan_root(root: Path, *, root_tag: str, removable: bool) -> List[ModelRecord]:
    """Scan one model root; return records for each valid ``<id>/manifest.json``.

    A malformed manifest logs a warning and is skipped — it never aborts the
    scan of sibling models.
    """
    records: List[ModelRecord] = []
    try:
        subdirs = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError as exc:
        _warn("cannot list model root {0}: {1}".format(root, exc))
        return records

    for model_dir in subdirs:
        manifest_path = model_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = parse_manifest(manifest_path)
        except ManifestError as exc:
            _warn("skipping {0}: {1}".format(model_dir.name, exc))
            continue

        size = manifest.size_bytes
        if size is None:
            size = _dir_size_bytes(model_dir)

        # Infer source.type from the root when the manifest doesn't say.
        source = dict(manifest.source)
        if not _coerce_str(source.get("type")):
            source["type"] = root_tag

        records.append(
            ModelRecord(
                id=manifest.id,
                name=manifest.name,
                stage=manifest.stage,
                format=manifest.format,
                engine=manifest.engine,
                languages=manifest.languages,
                entrypoint_path=str(manifest.entrypoint_path),
                source=source,
                size_bytes=int(size),
                removable=removable,
                root=root_tag,
                version=manifest.version,
            )
        )
    return records


def list_models() -> List[ModelRecord]:
    """Scan the bundled root then the user root; return resolved records.

    De-dupe by id: a user model with the same id OVERRIDES the bundled model of
    that id (the user copy is the removable, locally-installed one, and it is
    the one a caller can manage). When neither root is present, returns ``[]``.
    """
    by_id: Dict[str, ModelRecord] = {}

    bundled = bundled_models_root()
    if bundled is not None:
        for record in _scan_root(bundled, root_tag="bundled", removable=False):
            by_id[record.id] = record

    user = user_models_root()
    if user is not None:
        for record in _scan_root(user, root_tag="user", removable=True):
            # User overrides bundled for the same id.
            by_id[record.id] = record

    return list(by_id.values())


def get_model(model_id: str) -> Optional[ModelRecord]:
    """Return the single record whose id matches ``model_id``, or ``None``."""
    target = _coerce_str(model_id)
    if not target:
        return None
    for record in list_models():
        if record.id == target:
            return record
    return None


def resolve_stage_model(
    stage: str, *, binding_id: Optional[str] = None
) -> Optional[ModelRecord]:
    """Resolve a pipeline stage to a concrete installed model record.

    Precedence:
      1. ``binding_id`` — if given AND it exists AND its stage matches ``stage``.
      2. Else if EXACTLY ONE installed model has that stage, use it.
      3. Else ``None`` (ambiguous / absent) — the caller falls back to config.

    Returns the record (carrying an absolute ``entrypoint_path`` + ``format``)
    or ``None``. Logs the decision. When no roots are present ``list_models()``
    is empty, so this returns ``None`` and the caller's behavior is unchanged.
    """
    target_stage = _coerce_str(stage).lower()
    if target_stage not in VALID_STAGES:
        return None

    models = list_models()

    if binding_id:
        wanted = _coerce_str(binding_id)
        for record in models:
            if record.id == wanted and record.stage == target_stage:
                _warn(
                    "resolve_stage_model({0}): using binding {1!r}".format(
                        target_stage, wanted
                    )
                )
                return record
        _warn(
            "resolve_stage_model({0}): binding {1!r} not found or stage mismatch; "
            "falling back to single-model resolution".format(target_stage, wanted)
        )

    stage_models = [record for record in models if record.stage == target_stage]
    if len(stage_models) == 1:
        chosen = stage_models[0]
        _warn(
            "resolve_stage_model({0}): single installed model {1!r} selected".format(
                target_stage, chosen.id
            )
        )
        return chosen

    if len(stage_models) == 0:
        _warn(
            "resolve_stage_model({0}): no installed model for stage; "
            "caller falls back to config".format(target_stage)
        )
    else:
        _warn(
            "resolve_stage_model({0}): {1} models for stage (ambiguous); "
            "caller falls back to config".format(target_stage, len(stage_models))
        )
    return None


__all__ = [
    "BUNDLED_MODELS_ENV",
    "USER_DATA_ENV",
    "SCHEMA_VERSION",
    "VALID_STAGES",
    "VALID_FORMATS",
    "ManifestError",
    "ModelManifest",
    "ModelRecord",
    "bundled_models_root",
    "user_models_root",
    "parse_manifest",
    "list_models",
    "get_model",
    "resolve_stage_model",
]
