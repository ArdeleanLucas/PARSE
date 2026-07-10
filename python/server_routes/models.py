"""PARSE server route-domain module: model registry (read + write).

Read routes (from #684, unchanged):

  * ``GET  /api/models``        → ``{"models": [ ...serialized records... ]}``
  * ``GET  /api/models/{id}``   → the record, or 404 when unknown.

Write routes (this module, Gate B §9.4):

  * ``POST   /api/models/install``  → 202 ``{"jobId": ...}`` (JOB-TRACKED). Two
    install modes: a multipart ``.zip``/``.parsemodel`` pack upload, or a JSON
    ``{hfRepoId, stage, format, name?}`` Hugging Face download. The long-running
    extract/download runs in the ``model_install`` compute runner
    (:func:`_compute_model_install`) registered at both dispatch sites in
    ``server_routes/jobs.py``.
  * ``DELETE /api/models/{id}``     → synchronous; USER models only (bundled are
    read-only and refused).
  * ``GET    /api/models/binding``  → the per-project stage→model binding map.
  * ``POST   /api/models/binding``  → set/clear one stage binding (validated).

The storage logic lives in :mod:`ai.model_install` and :mod:`ai.model_registry`;
this module is the thin HTTP seam (request parsing, job launch, JSON responses).
"""
from __future__ import annotations

import server as _server


# --------------------------------------------------------------------------- #
# Read routes (unchanged from #684)
# --------------------------------------------------------------------------- #

def _api_get_models(self) -> None:
    """GET /api/models — list all installed models (bundled + user)."""
    from ai.model_registry import list_models

    records = [record.to_dict() for record in list_models()]
    self._send_json(_server.HTTPStatus.OK, {"models": records})


def _api_get_model(self, model_id: str) -> None:
    """GET /api/models/{id} — a single record, or 404 when unknown."""
    from ai.model_registry import get_model

    record = get_model(model_id)
    if record is None:
        raise _server.ApiError(
            _server.HTTPStatus.NOT_FOUND, "Model not found: {0}".format(model_id)
        )
    self._send_json(_server.HTTPStatus.OK, record.to_dict())


# --------------------------------------------------------------------------- #
# Install (job-tracked)
# --------------------------------------------------------------------------- #

# Accepted pack file extensions on the upload field.
_PACK_UPLOAD_EXTENSIONS = (".zip", ".parsemodel")
# Guard the pack upload size the same way onboarding guards audio uploads.
_INSTALL_MAX_UPLOAD_BYTES = getattr(_server, "ONBOARD_MAX_UPLOAD_BYTES", 8 * 1024 * 1024 * 1024)


def _api_post_models_install(self) -> None:
    """POST /api/models/install — start a job-tracked model install.

    Detects the install mode from the request Content-Type:

    * ``multipart/form-data`` → pack upload. The uploaded ``.zip``/``.parsemodel``
      is read from the socket HERE (the background runner cannot touch the
      socket) and staged to a temp file; the runner extracts it.
    * JSON → ``{hfRepoId, stage, format, name?}`` Hugging Face download.

    Always returns ``202 {"jobId": ...}`` on the success path — never a null
    jobId (long-running-endpoint rule).
    """
    content_type = self.headers.get("Content-Type", "") or ""

    if "multipart/form-data" in content_type:
        payload = _stage_pack_upload(self, content_type)
        meta = {"computeType": "model_install", "mode": "pack"}
    else:
        payload = _build_hf_install_payload(self)
        meta = {"computeType": "model_install", "mode": "hf", "hfRepoId": payload.get("hfRepoId")}

    callback_url = _server._job_callback_url_from_mapping(payload)
    if callback_url:
        payload["callbackUrl"] = callback_url
    try:
        job_id = _server._create_job("compute:model_install", meta)
    except _server.JobResourceConflictError as exc:
        raise _server.ApiError(_server.HTTPStatus.CONFLICT, str(exc)) from exc
    _server._launch_compute_runner(job_id, "model_install", payload)
    self._send_json(_server.HTTPStatus.ACCEPTED, {"jobId": job_id})


def _stage_pack_upload(self, content_type: str) -> _server.Dict[str, _server.Any]:
    """Read a multipart pack upload to a temp file; return the runner payload.

    The temp path is passed to the runner (which extracts it) and removed by the
    runner when done. Validates the field extension and upload size here so a
    bad request fails fast with a 4xx before a job is created.
    """
    import tempfile

    raw_length = self.headers.get("Content-Length", "")
    try:
        content_length = int(raw_length)
    except (ValueError, TypeError):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "Content-Length header is required")
    if content_length > _INSTALL_MAX_UPLOAD_BYTES:
        raise _server.ApiError(
            _server.HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            "Upload exceeds {0} byte limit".format(_INSTALL_MAX_UPLOAD_BYTES),
        )
    environ = {"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type, "CONTENT_LENGTH": str(content_length)}
    form = _server.cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=environ, keep_blank_values=True)

    pack_item = form["pack"] if "pack" in form else None
    if pack_item is None or not getattr(pack_item, "filename", None):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "pack file is required")
    filename = _server.os.path.basename(pack_item.filename or "model.zip")
    suffix = _server.pathlib.Path(filename).suffix.lower()
    if suffix not in _PACK_UPLOAD_EXTENSIONS:
        raise _server.ApiError(
            _server.HTTPStatus.BAD_REQUEST,
            "Unsupported pack format: {0} (allowed: {1})".format(
                suffix, ", ".join(_PACK_UPLOAD_EXTENSIONS)
            ),
        )

    overwrite = _coerce_bool(form.getfirst("overwrite", ""))

    handle = tempfile.NamedTemporaryFile(prefix="parse-model-pack-", suffix=suffix, delete=False)
    try:
        handle.write(pack_item.file.read())
    finally:
        handle.close()
    return {"mode": "pack", "packPath": handle.name, "overwrite": overwrite}


def _build_hf_install_payload(self) -> _server.Dict[str, _server.Any]:
    """Parse + validate the JSON body for an HF install; return the runner payload."""
    body = self._expect_object(self._read_json_body(), "Request body")
    repo_id = str(body.get("hfRepoId") or body.get("hf_repo_id") or "").strip()
    if not repo_id:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "hfRepoId is required")
    stage = str(body.get("stage") or "").strip().lower()
    fmt = str(body.get("format") or body.get("fmt") or "").strip().lower()
    from ai.model_registry import VALID_FORMATS, VALID_STAGES

    if stage not in VALID_STAGES:
        raise _server.ApiError(
            _server.HTTPStatus.BAD_REQUEST,
            "invalid stage {0!r} (expected one of {1})".format(stage, sorted(VALID_STAGES)),
        )
    if fmt not in VALID_FORMATS:
        raise _server.ApiError(
            _server.HTTPStatus.BAD_REQUEST,
            "invalid format {0!r} (expected one of {1})".format(fmt, sorted(VALID_FORMATS)),
        )
    name = body.get("name")
    payload: _server.Dict[str, _server.Any] = {
        "mode": "hf",
        "hfRepoId": repo_id,
        "stage": stage,
        "format": fmt,
        "overwrite": bool(body.get("overwrite")),
    }
    if isinstance(name, str) and name.strip():
        payload["name"] = name.strip()
    # Preserve a caller callbackUrl for the generic job callback path.
    for key in ("callbackUrl", "callback_url"):
        if body.get(key):
            payload[key] = body.get(key)
    return payload


def _coerce_bool(value: _server.Any) -> bool:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _compute_model_install(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Runner for the ``model_install`` compute type (job-tracked).

    Emits ``_set_compute_progress`` at each logical step so the FE progress bar
    moves. Dispatches on ``payload["mode"]``: ``"pack"`` extracts the staged temp
    zip; ``"hf"`` runs ``snapshot_download`` + manifest synthesis. On failure the
    storage layer cleans up any partial dir; the temp pack file is always removed.

    Returns ``{installed, model, rescan}`` — the installed model id plus a
    re-scan confirmation (the registry record now visible to ``list_models``).
    """
    from ai import model_install
    from ai.model_registry import get_model

    def _progress(pct: float, message: str) -> None:
        _server._set_compute_progress(job_id, float(pct), message=message)

    # Mode is normally set by the dedicated /api/models/install route. When the
    # runner is reached via the generic /api/compute/model_install path (no
    # explicit mode), infer it: a staged pack path => pack, else an hfRepoId => hf.
    mode = str(payload.get("mode") or "").strip().lower()
    if not mode:
        if payload.get("packPath"):
            mode = "pack"
        elif payload.get("hfRepoId") or payload.get("hf_repo_id"):
            mode = "hf"
    _server._set_compute_progress(job_id, 1.0, message="Preparing model install ({0})".format(mode or "?"))

    try:
        if mode == "pack":
            pack_path = str(payload.get("packPath") or "")
            try:
                result = model_install.install_pack(
                    pack_path,
                    overwrite=bool(payload.get("overwrite")),
                    progress=_progress,
                )
            finally:
                # Always remove the staged upload, success or failure.
                try:
                    if pack_path:
                        _server.os.remove(pack_path)
                except OSError:
                    pass
        elif mode == "hf":
            result = model_install.install_hf(
                str(payload.get("hfRepoId") or payload.get("hf_repo_id") or ""),
                stage=str(payload.get("stage") or ""),
                fmt=str(payload.get("format") or ""),
                name=payload.get("name"),
                overwrite=bool(payload.get("overwrite")),
                progress=_progress,
            )
        else:
            raise model_install.ModelInstallError("unknown install mode: {0!r}".format(mode))
    except model_install.ModelInstallError as exc:
        # Surface as a structured job error (the compute runner sets job status).
        error = RuntimeError(str(exc))
        error.error_code = "model_install_failed"  # type: ignore[attr-defined]
        raise error from exc

    # Re-scan confirmation: the record the registry now resolves for this id.
    record = get_model(result["id"])
    rescan = record.to_dict() if record is not None else None
    _server._set_compute_progress(job_id, 100.0, message="Model {0} installed".format(result["id"]))
    return {"installed": result["id"], "model": rescan, "rescan": rescan is not None, "detail": result}


# --------------------------------------------------------------------------- #
# Delete (synchronous, user-root only)
# --------------------------------------------------------------------------- #

def _api_delete_model(self, model_id: str) -> None:
    """DELETE /api/models/{id} — remove a USER model (bundled models refused)."""
    from ai import model_install

    try:
        result = model_install.delete_model(model_id)
    except model_install.ModelInstallError as exc:
        raise _server.ApiError(_status_from_hint(exc), str(exc)) from exc
    self._send_json(_server.HTTPStatus.OK, result)


# --------------------------------------------------------------------------- #
# Per-project binding (synchronous)
# --------------------------------------------------------------------------- #

def _api_get_models_binding(self) -> None:
    """GET /api/models/binding — the per-project stage→model binding map."""
    from ai import model_install

    project_root = _resolve_binding_project_root(self)
    binding = model_install.read_binding(project_root)
    self._send_json(_server.HTTPStatus.OK, {"binding": binding, "project": str(project_root)})


def _api_post_models_binding(self) -> None:
    """POST /api/models/binding — set/clear one stage binding (validated)."""
    from ai import model_install

    body = self._expect_object(self._read_json_body(), "Request body")
    stage = str(body.get("stage") or "").strip().lower()
    if not stage:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "stage is required")
    # modelId null/absent clears the binding.
    raw_model_id = body.get("modelId")
    if raw_model_id is None:
        raw_model_id = body.get("model_id")
    project_root = _resolve_binding_project_root(self)
    try:
        binding = model_install.set_binding(project_root, stage, raw_model_id)
    except model_install.ModelInstallError as exc:
        raise _server.ApiError(_status_from_hint(exc), str(exc)) from exc
    self._send_json(_server.HTTPStatus.OK, {"binding": binding, "project": str(project_root)})


def _resolve_binding_project_root(self) -> _server.Any:
    """Resolve the project root for a binding request.

    Honors an explicit ``?project=`` query param (matching how ``GET /api/project``
    lets the desktop shell target a root), otherwise falls back to the server's
    default ``_project_root()``.
    """
    params = self._request_query_params()
    values = params.get("project") or []
    if values and str(values[0]).strip():
        return _server.pathlib.Path(str(values[0]).strip()).expanduser()
    return _server._project_root()


def _status_from_hint(exc) -> _server.Any:
    """Map a ModelInstallError.status_hint to an HTTPStatus for the HTTP layer."""
    hint = int(getattr(exc, "status_hint", 400) or 400)
    mapping = {
        400: _server.HTTPStatus.BAD_REQUEST,
        404: _server.HTTPStatus.NOT_FOUND,
        409: _server.HTTPStatus.CONFLICT,
        500: _server.HTTPStatus.INTERNAL_SERVER_ERROR,
    }
    return mapping.get(hint, _server.HTTPStatus.BAD_REQUEST)


__all__ = [
    "_api_get_models",
    "_api_get_model",
    "_api_post_models_install",
    "_compute_model_install",
    "_api_delete_model",
    "_api_get_models_binding",
    "_api_post_models_binding",
]
