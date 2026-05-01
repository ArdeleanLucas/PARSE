"""Custom HTTP router functions for global concept tags."""
from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Protocol

from storage import tags_store


@dataclass(frozen=True)
class TagsRouterError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


class TagsHandler(Protocol):
    def _read_json_body(self, required: bool = True) -> Any:
        ...

    def _expect_object(self, value: Any, label: str) -> dict[str, Any]:
        ...

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        ...

    def send_response(self, code: HTTPStatus) -> None:
        ...

    def send_header(self, key: str, value: str) -> None:
        ...

    def end_headers(self) -> None:
        ...


def _send_no_content(handler: TagsHandler) -> None:
    handler.send_response(HTTPStatus.NO_CONTENT)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _router_error_from_value_error(exc: ValueError) -> TagsRouterError:
    if isinstance(exc, tags_store.TagNameConflictError):
        return TagsRouterError(HTTPStatus.CONFLICT, str(exc))
    return TagsRouterError(HTTPStatus.BAD_REQUEST, str(exc))


def get_tags(handler: TagsHandler) -> None:
    data = tags_store.fetch_all()
    handler._send_json(
        HTTPStatus.OK,
        {"tags": data["tags"], "attachments": data["attachments"]},
    )


def create_tag(handler: TagsHandler) -> None:
    body = handler._expect_object(handler._read_json_body(required=True), "Request body")
    try:
        tag = tags_store.create_tag(body.get("name"), body.get("color"))
    except ValueError as exc:
        raise _router_error_from_value_error(exc) from exc
    handler._send_json(HTTPStatus.CREATED, tag)


def delete_tag(handler: TagsHandler, tag_id: str) -> None:
    try:
        tags_store.delete_tag(tag_id)
    except ValueError as exc:
        raise _router_error_from_value_error(exc) from exc
    _send_no_content(handler)


def attach_tag(handler: TagsHandler, concept_id: str, tag_id: str) -> None:
    try:
        tags_store.attach(concept_id, tag_id)
    except tags_store.UnknownTagError as exc:
        raise TagsRouterError(HTTPStatus.NOT_FOUND, f"Unknown tag '{exc.args[0]}'") from exc
    except ValueError as exc:
        raise _router_error_from_value_error(exc) from exc
    _send_no_content(handler)


def detach_tag(handler: TagsHandler, concept_id: str, tag_id: str) -> None:
    try:
        tags_store.detach(concept_id, tag_id)
    except ValueError as exc:
        raise _router_error_from_value_error(exc) from exc
    _send_no_content(handler)
