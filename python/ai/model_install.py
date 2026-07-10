"""model_install.py - Write side of PARSE's desktop model registry (Gate B §9.4).

The read/resolve core is :mod:`ai.model_registry`. This module adds the WRITE
operations a survey linguist needs to "plug in" a model without a terminal:

  * :func:`install_pack`   - install a ``.zip`` / ``.parsemodel`` model pack from
    a local temp path (offline field use). Validates the embedded
    ``manifest.json`` with the SAME rules as :func:`ai.model_registry.parse_manifest`,
    guards against zip-slip, and extracts into ``PARSE_USER_DATA/models/<id>/``.
  * :func:`install_hf`     - download a model from the Hugging Face Hub via
    ``huggingface_hub.snapshot_download`` (imported LAZILY inside the function so
    this module stays importable without ``huggingface_hub`` / ``torch``), then
    synthesize a ``manifest.json`` in the downloaded dir.
  * :func:`delete_model`   - remove a USER model directory. Bundled (read-only)
    models are refused.

Design constraints mirror :mod:`ai.model_registry`:

  * **Dependency-light / importable without torch.** Only stdlib at module top
    level. ``huggingface_hub`` is imported lazily inside :func:`install_hf`.
  * **User-root only writes.** Every write targets ``PARSE_USER_DATA/models/``.
    When that root is unavailable (the web product default), install/delete raise
    :class:`ModelInstallError` rather than guessing a location.

Progress is reported through an optional ``progress`` callback ``(pct, message)``
so the job-tracked HTTP runner can drive the FE progress bar; when omitted the
functions run silently (unit tests call them directly).
"""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai.model_registry import (
    SCHEMA_VERSION,
    USER_DATA_ENV,
    VALID_FORMATS,
    VALID_STAGES,
    ManifestError,
    get_model,
    parse_manifest,
    user_models_root,
)

# Accepted pack container extensions for local file install.
PACK_EXTENSIONS = frozenset({".zip", ".parsemodel"})

# Map a manifest ``format`` to the runtime engine we record when synthesizing a
# manifest for an HF download. The pack path trusts the embedded manifest's
# engine; this table only backs the generated-manifest (HF) path.
_FORMAT_ENGINE = {
    "faster-whisper-ct2": "faster-whisper",
    "hf-transformers": "hf-transformers",
}

# Progress callback: (percent 0..100, human message) -> None.
ProgressCallback = Optional[Callable[[float, str], None]]


class ModelInstallError(ValueError):
    """Raised for any install/delete failure (bad input, collision, IO)."""

    def __init__(self, message: str, *, status_hint: int = 400) -> None:
        super().__init__(message)
        # A 4xx-vs-5xx hint the HTTP layer can use; storage logic itself is
        # transport-agnostic. 400 = caller error, 409 = collision, 404 = unknown.
        self.status_hint = status_hint


def _require_user_root() -> Path:
    """Return the writable user models root, creating it if the parent exists.

    ``user_models_root()`` returns ``None`` until the directory exists, so for a
    fresh install we create ``PARSE_USER_DATA/models`` here. Raises when
    ``PARSE_USER_DATA`` itself is unset (no writable location to target).
    """
    raw = os.environ.get(USER_DATA_ENV, "").strip()
    if not raw:
        raise ModelInstallError(
            "no writable model location: {0} is not set".format(USER_DATA_ENV),
            status_hint=400,
        )
    root = Path(raw).expanduser() / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _report(progress: ProgressCallback, pct: float, message: str) -> None:
    if progress is not None:
        try:
            progress(pct, message)
        except Exception:
            # Progress is observability-only; never let it break the install.
            pass


def _dir_size_bytes(directory: Path) -> int:
    total = 0
    for entry in directory.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def _slug_from_repo_id(repo_id: str) -> str:
    """Derive a filesystem-safe slug id from an HF repo id.

    ``razhan/whisper-base-sdh`` -> ``razhan-whisper-base-sdh``. Any character
    outside ``[A-Za-z0-9._-]`` collapses to ``-``; runs of ``-`` are squeezed and
    trimmed so the slug is a clean single directory name.
    """
    cleaned = []
    for ch in repo_id.strip():
        cleaned.append(ch if (ch.isalnum() or ch in "._-") else "-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    if not slug:
        raise ModelInstallError("cannot derive a model id from repo id {0!r}".format(repo_id))
    return slug


# --------------------------------------------------------------------------- #
# Zip-slip-safe extraction
# --------------------------------------------------------------------------- #

def _read_pack_manifest(zip_file: zipfile.ZipFile) -> Dict[str, Any]:
    """Read and JSON-parse the root ``manifest.json`` from an open pack zip."""
    try:
        raw = zip_file.read("manifest.json")
    except KeyError as exc:
        raise ModelInstallError("pack is missing a root manifest.json") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ModelInstallError("pack manifest.json is not valid JSON: {0}".format(exc)) from exc
    if not isinstance(data, dict):
        raise ModelInstallError("pack manifest.json is not a JSON object")
    return data


def _safe_extract(zip_file: zipfile.ZipFile, target_dir: Path) -> None:
    """Extract every member of ``zip_file`` into ``target_dir``, rejecting zip-slip.

    Any archive member whose resolved destination escapes ``target_dir`` (via
    ``..`` or an absolute path) aborts the whole extraction. Directory entries
    are created; symlinks are refused outright (a symlink member could point the
    loader outside the model dir even without a traversal name).
    """
    target_root = target_dir.resolve()
    for member in zip_file.infolist():
        # Refuse symlinks (external attr high bits carry the unix mode).
        mode = (member.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise ModelInstallError(
                "pack contains a symlink member ({0}); refused".format(member.filename)
            )
        dest = (target_dir / member.filename).resolve()
        try:
            dest.relative_to(target_root)
        except ValueError as exc:
            raise ModelInstallError(
                "pack member {0!r} escapes the model directory (zip-slip); refused".format(
                    member.filename
                )
            ) from exc
        if member.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)


def _validate_extracted_manifest(model_dir: Path) -> None:
    """Re-validate the ON-DISK manifest with the registry's own parser.

    This is belt-and-suspenders: the pack manifest was validated pre-extract,
    but re-parsing the extracted copy guarantees the record the registry will
    later read is valid (entrypoint resolves under the dir, stage/format legal).
    """
    try:
        parse_manifest(model_dir / "manifest.json")
    except ManifestError as exc:
        raise ModelInstallError("installed manifest failed validation: {0}".format(exc)) from exc


# --------------------------------------------------------------------------- #
# Manifest validation (shared subset of registry rules, pre-extract)
# --------------------------------------------------------------------------- #

def _validate_pack_manifest_fields(data: Dict[str, Any]) -> str:
    """Validate a pack manifest dict pre-extract; return its cleaned id.

    Applies the same core rules as :func:`ai.model_registry.parse_manifest`:
    required fields present, ``schema_version == 1``, ``stage`` and ``format`` in
    the allowed enums, and an ``entrypoint`` that does not traverse out of the
    model directory once extracted. Returns the model id.
    """
    required = ("schema_version", "id", "name", "stage", "format", "entrypoint")
    missing = [key for key in required if data.get(key) in (None, "")]
    if missing:
        raise ModelInstallError(
            "pack manifest missing required field(s): {0}".format(", ".join(missing))
        )
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ModelInstallError(
            "pack manifest has unsupported schema_version {0!r} (expected {1})".format(
                data.get("schema_version"), SCHEMA_VERSION
            )
        )
    stage = str(data.get("stage") or "").strip().lower()
    if stage not in VALID_STAGES:
        raise ModelInstallError(
            "pack manifest has invalid stage {0!r} (expected one of {1})".format(
                data.get("stage"), sorted(VALID_STAGES)
            )
        )
    fmt = str(data.get("format") or "").strip().lower()
    if fmt not in VALID_FORMATS:
        raise ModelInstallError(
            "pack manifest has invalid format {0!r} (expected one of {1})".format(
                data.get("format"), sorted(VALID_FORMATS)
            )
        )
    model_id = str(data.get("id") or "").strip()
    if not model_id:
        raise ModelInstallError("pack manifest has an empty id")
    if "/" in model_id or "\\" in model_id or model_id in (".", ".."):
        raise ModelInstallError("pack manifest id {0!r} is not a valid directory name".format(model_id))
    # Entrypoint traversal guard (mirrors parse_manifest; checked here against a
    # notional model dir so a malicious pack is rejected before extraction).
    entrypoint = str(data.get("entrypoint") or ".").strip() or "."
    if os.path.isabs(entrypoint):
        raise ModelInstallError("pack manifest entrypoint {0!r} must be relative".format(entrypoint))
    notional = Path("/__parse_model__")
    resolved = (notional / entrypoint).resolve()
    try:
        resolved.relative_to(notional.resolve())
    except ValueError as exc:
        raise ModelInstallError(
            "pack manifest entrypoint {0!r} escapes the model directory".format(entrypoint)
        ) from exc
    return model_id


# --------------------------------------------------------------------------- #
# Public install / delete API
# --------------------------------------------------------------------------- #

def install_pack(
    pack_path: str,
    *,
    overwrite: bool = False,
    progress: ProgressCallback = None,
) -> Dict[str, Any]:
    """Install a local ``.zip`` / ``.parsemodel`` model pack.

    Steps (each reported via ``progress``): validate container → read + validate
    manifest → collision check → zip-slip-safe extract → re-validate on disk →
    finalize. Extracts into ``PARSE_USER_DATA/models/<id>/`` where ``<id>`` comes
    from the manifest.

    ``overwrite`` must be true to replace an existing USER model of the same id
    (a bundled model of that id may always be shadowed — the user root overrides
    it by design in :func:`ai.model_registry.list_models`).

    Returns ``{"id", "root": "user", "size_bytes", "reinstalled": bool}``.
    """
    _report(progress, 2.0, "Validating model pack")
    src = Path(pack_path)
    if not src.is_file():
        raise ModelInstallError("pack file not found: {0}".format(pack_path))
    if src.suffix.lower() not in PACK_EXTENSIONS:
        raise ModelInstallError(
            "unsupported pack extension {0!r} (expected one of {1})".format(
                src.suffix, sorted(PACK_EXTENSIONS)
            )
        )
    if not zipfile.is_zipfile(src):
        raise ModelInstallError("pack is not a valid zip archive")

    with zipfile.ZipFile(src) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ModelInstallError("pack archive is corrupt (member {0})".format(bad))
        _report(progress, 12.0, "Reading pack manifest")
        manifest = _read_pack_manifest(zf)
        model_id = _validate_pack_manifest_fields(manifest)

        # Collision check against USER models only (bundled may be shadowed).
        existing = get_model(model_id)
        reinstalling = False
        if existing is not None and existing.root == "user":
            if not overwrite:
                raise ModelInstallError(
                    "a user model with id {0!r} already exists; pass overwrite to replace it".format(
                        model_id
                    ),
                    status_hint=409,
                )
            reinstalling = True

        user_root = _require_user_root()
        target_dir = user_root / model_id
        staging_dir = user_root / (".staging-" + model_id)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        try:
            _report(progress, 30.0, "Extracting model files")
            _safe_extract(zf, staging_dir)
            _report(progress, 70.0, "Validating installed manifest")
            _validate_extracted_manifest(staging_dir)
            # Atomic-ish swap: remove any existing target, then move staging in.
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            _report(progress, 88.0, "Finalizing install")
            os.replace(staging_dir, target_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    size = _dir_size_bytes(target_dir)
    _report(progress, 100.0, "Installed model {0}".format(model_id))
    return {
        "id": model_id,
        "root": "user",
        "size_bytes": size,
        "reinstalled": reinstalling,
    }


def install_hf(
    hf_repo_id: str,
    *,
    stage: str,
    fmt: str,
    name: Optional[str] = None,
    overwrite: bool = False,
    progress: ProgressCallback = None,
    snapshot_download: Optional[Callable[..., str]] = None,
) -> Dict[str, Any]:
    """Download a model from the Hugging Face Hub and register a manifest for it.

    ``stage`` and ``fmt`` are validated against the registry enums (bad input is
    a caller error). The download goes to ``PARSE_USER_DATA/models/<slug>/`` where
    ``<slug>`` is derived from ``hf_repo_id`` (``razhan/whisper-base-sdh`` →
    ``razhan-whisper-base-sdh``). A ``manifest.json`` is synthesized in that dir.

    ``snapshot_download`` is injectable for tests; in production it defaults to
    ``huggingface_hub.snapshot_download`` (imported lazily so this module is
    importable without huggingface_hub installed).

    Returns ``{"id", "root": "user", "size_bytes", "reinstalled": bool}``.
    """
    _report(progress, 2.0, "Validating request")
    repo_id = str(hf_repo_id or "").strip()
    if not repo_id:
        raise ModelInstallError("hfRepoId is required")
    stage_norm = str(stage or "").strip().lower()
    if stage_norm not in VALID_STAGES:
        raise ModelInstallError(
            "invalid stage {0!r} (expected one of {1})".format(stage, sorted(VALID_STAGES))
        )
    fmt_norm = str(fmt or "").strip().lower()
    if fmt_norm not in VALID_FORMATS:
        raise ModelInstallError(
            "invalid format {0!r} (expected one of {1})".format(fmt, sorted(VALID_FORMATS))
        )

    model_id = _slug_from_repo_id(repo_id)
    existing = get_model(model_id)
    reinstalling = False
    if existing is not None and existing.root == "user":
        if not overwrite:
            raise ModelInstallError(
                "a user model with id {0!r} already exists; pass overwrite to replace it".format(
                    model_id
                ),
                status_hint=409,
            )
        reinstalling = True

    user_root = _require_user_root()
    target_dir = user_root / model_id

    if snapshot_download is None:
        try:
            from huggingface_hub import snapshot_download as _hf_snapshot  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - exercised only without the dep
            raise ModelInstallError(
                "huggingface_hub is not available for HF model download: {0}".format(exc),
                status_hint=500,
            ) from exc
        snapshot_download = _hf_snapshot

    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        _report(progress, 20.0, "Downloading {0} from Hugging Face".format(repo_id))
        snapshot_download(repo_id=repo_id, local_dir=str(target_dir))
        _report(progress, 80.0, "Writing manifest")
        size = _dir_size_bytes(target_dir)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "id": model_id,
            "name": (str(name).strip() if name and str(name).strip() else repo_id),
            "stage": stage_norm,
            "format": fmt_norm,
            "engine": _FORMAT_ENGINE.get(fmt_norm, ""),
            "languages": ["*"],
            "entrypoint": ".",
            "version": "1.0.0",
            "source": {"type": "hf", "ref": repo_id},
            "size_bytes": size,
        }
        (target_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _validate_extracted_manifest(target_dir)
    except Exception:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise

    _report(progress, 100.0, "Installed model {0}".format(model_id))
    return {
        "id": model_id,
        "root": "user",
        "size_bytes": _dir_size_bytes(target_dir),
        "reinstalled": reinstalling,
    }


def delete_model(model_id: str) -> Dict[str, Any]:
    """Delete a USER model directory.

    Refuses to delete a bundled (read-only) model. Returns
    ``{"id", "deleted": True}`` on success. Raises :class:`ModelInstallError`
    with ``status_hint`` 404 (unknown) or 400 (bundled/read-only).
    """
    target = str(model_id or "").strip()
    if not target:
        raise ModelInstallError("model id is required")
    record = get_model(target)
    if record is None:
        raise ModelInstallError("model not found: {0}".format(target), status_hint=404)
    if not record.removable or record.root != "user":
        raise ModelInstallError(
            "model {0!r} is bundled/read-only and cannot be deleted".format(target),
            status_hint=400,
        )
    user_root = user_models_root()
    if user_root is None:
        raise ModelInstallError("no user model root available", status_hint=500)
    model_dir = user_root / target
    if not model_dir.is_dir():
        raise ModelInstallError("model not found: {0}".format(target), status_hint=404)
    shutil.rmtree(model_dir)
    return {"id": target, "deleted": True}


# --------------------------------------------------------------------------- #
# Per-project stage -> model binding
# --------------------------------------------------------------------------- #

BINDING_STAGES: Tuple[str, ...] = ("stt", "ipa", "ortho")


def empty_binding() -> Dict[str, Optional[str]]:
    """A binding map with every stage cleared to ``None``."""
    return {stage: None for stage in BINDING_STAGES}


def read_binding(project_root) -> Dict[str, Optional[str]]:
    """Read the per-project stage→model binding from ``project.json``.

    Missing stages default to ``None``. Delegates to the project-lifecycle
    parser so a corrupt/missing ``project.json`` degrades to an all-``None``
    binding rather than raising.
    """
    from app.services.project_lifecycle import _parse_project_json

    payload, _corrupt = _parse_project_json(Path(project_root))
    result = empty_binding()
    if isinstance(payload, dict):
        models = payload.get("models")
        if isinstance(models, dict):
            for stage in BINDING_STAGES:
                value = models.get(stage)
                result[stage] = value if isinstance(value, str) and value.strip() else None
    return result


def set_binding(project_root, stage: str, model_id: Optional[str]) -> Dict[str, Optional[str]]:
    """Set (or clear) one stage→model binding and persist it atomically.

    ``model_id`` ``None``/empty clears the binding. A non-empty id is VALIDATED:
    it must exist in the registry AND its record.stage must match ``stage``
    (otherwise a caller error). Persists via the project-lifecycle atomic writer
    (reused, not hand-rolled). Returns the full updated binding map.
    """
    from app.services import project_lifecycle

    stage_norm = str(stage or "").strip().lower()
    if stage_norm not in BINDING_STAGES:
        raise ModelInstallError(
            "invalid stage {0!r} (expected one of {1})".format(stage, list(BINDING_STAGES))
        )

    normalized_id: Optional[str] = None
    if model_id is not None and str(model_id).strip():
        normalized_id = str(model_id).strip()
        record = get_model(normalized_id)
        if record is None:
            raise ModelInstallError(
                "model not found: {0}".format(normalized_id), status_hint=404
            )
        if record.stage != stage_norm:
            raise ModelInstallError(
                "model {0!r} is a {1} model and cannot bind to stage {2!r}".format(
                    normalized_id, record.stage, stage_norm
                )
            )

    root = Path(project_root)
    path = root / "project.json"
    payload, corrupt = project_lifecycle._parse_project_json(root)
    if corrupt:
        raise ModelInstallError(
            "project.json is corrupt; cannot update model binding", status_hint=400
        )
    if not isinstance(payload, dict):
        # No project.json yet — start a minimal one so the binding persists.
        payload = {"name": root.name, "version": project_lifecycle.PROJECT_JSON_VERSION, "speakers": {}}

    models = payload.get("models")
    if not isinstance(models, dict):
        models = {}
    # Normalize all stages so the persisted map is complete + well-typed.
    merged = empty_binding()
    for existing_stage in BINDING_STAGES:
        value = models.get(existing_stage)
        merged[existing_stage] = value if isinstance(value, str) and value.strip() else None
    merged[stage_norm] = normalized_id

    payload["models"] = merged
    project_lifecycle._atomic_write_json(path, payload)
    return merged


__all__ = [
    "PACK_EXTENSIONS",
    "BINDING_STAGES",
    "ModelInstallError",
    "install_pack",
    "install_hf",
    "delete_model",
    "empty_binding",
    "read_binding",
    "set_binding",
]
