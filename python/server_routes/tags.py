"""PARSE server route-domain module: global concept tags."""
from __future__ import annotations

import server as _server
from api import tags_router as _tags_router


def _raise_api_error(exc: _tags_router.TagsRouterError) -> None:
    raise _server.ApiError(exc.status, exc.message)


def _api_get_concept_tags(self) -> None:
    """GET /api/tags — return global concept tags and attachments."""
    try:
        _tags_router.get_tags(self)
    except _tags_router.TagsRouterError as exc:
        _raise_api_error(exc)


def _api_post_concept_tag(self) -> None:
    """POST /api/tags — create one global concept tag."""
    try:
        _tags_router.create_tag(self)
    except _tags_router.TagsRouterError as exc:
        _raise_api_error(exc)


def _api_delete_concept_tag(self, tag_id: str) -> None:
    """DELETE /api/tags/{tagId} — delete a tag and cascade detachments."""
    try:
        _tags_router.delete_tag(self, tag_id)
    except _tags_router.TagsRouterError as exc:
        _raise_api_error(exc)


def _api_post_concept_tag_attachment(self, concept_id: str, tag_id: str) -> None:
    """POST /api/concepts/{conceptId}/tags/{tagId} — attach a tag idempotently."""
    try:
        _tags_router.attach_tag(self, concept_id, tag_id)
    except _tags_router.TagsRouterError as exc:
        _raise_api_error(exc)


def _api_delete_concept_tag_attachment(self, concept_id: str, tag_id: str) -> None:
    """DELETE /api/concepts/{conceptId}/tags/{tagId} — detach a tag idempotently."""
    try:
        _tags_router.detach_tag(self, concept_id, tag_id)
    except _tags_router.TagsRouterError as exc:
        _raise_api_error(exc)


def _dispatch_api_delete(self, request_path: str) -> None:
    """DELETE router. Currently handles global concept-tag endpoints."""
    parts = self._path_parts(request_path)
    if len(parts) == 3 and parts[0] == "api" and parts[1] == "tags":
        self._api_delete_concept_tag(parts[2])
        return
    if len(parts) == 5 and parts[0] == "api" and parts[1] == "concepts" and parts[3] == "tags":
        self._api_delete_concept_tag_attachment(parts[2], parts[4])
        return
    raise _server.ApiError(_server.HTTPStatus.NOT_FOUND, "Unknown API endpoint")


__all__ = [
    "_api_get_concept_tags",
    "_api_post_concept_tag",
    "_api_delete_concept_tag",
    "_api_post_concept_tag_attachment",
    "_api_delete_concept_tag_attachment",
    "_dispatch_api_delete",
]
