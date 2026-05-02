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


def get_tags(handler: TagsHandler) -> None:
    data = tags_store.fetch_all()
    handler._send_json(HTTPStatus.OK, {"tags": data["tags"]})


def put_tags(handler: TagsHandler) -> None:
    body = handler._expect_object(handler._read_json_body(required=True), "Request body")
    incoming = body.get("tags")
    if not isinstance(incoming, list):
        raise TagsRouterError(HTTPStatus.BAD_REQUEST, "Body must be { tags: Tag[] }")
    try:
        result = tags_store.replace_all(incoming)
    except tags_store.TagValidationError as exc:
        raise TagsRouterError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    handler._send_json(HTTPStatus.OK, {"tags": result["tags"]})
