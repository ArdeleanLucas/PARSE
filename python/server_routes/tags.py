"""PARSE server route-domain module: global concept tags."""
from __future__ import annotations

import server as _server
from api import tags_router as _tags_router


def _raise_api_error(exc: _tags_router.TagsRouterError) -> None:
    raise _server.ApiError(exc.status, exc.message)


def _api_get_concept_tags(self) -> None:
    """GET /api/tags — return global concept tags in useTagStore shape."""
    try:
        _tags_router.get_tags(self)
    except _tags_router.TagsRouterError as exc:
        _raise_api_error(exc)


def _api_put_concept_tags(self) -> None:
    """PUT /api/tags — atomically replace the full global tag list."""
    try:
        _tags_router.put_tags(self)
    except _tags_router.TagsRouterError as exc:
        _raise_api_error(exc)


__all__ = [
    "_api_get_concept_tags",
    "_api_put_concept_tags",
]
