"""PARSE server route-domain module: model registry (read-only).

Two fast, synchronous, read-only routes over the desktop model registry:

  * ``GET /api/models``       → ``{"models": [ ...serialized records... ]}``
  * ``GET /api/models/{id}``  → the record, or 404 when unknown.

These never install, download, delete, or bind models — that surface is a
separate follow-up. Both are plain synchronous JSON (NOT job-tracked).
"""
from __future__ import annotations

import server as _server


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


__all__ = ["_api_get_models", "_api_get_model"]
