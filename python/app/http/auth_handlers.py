"""Helpers for PARSE auth HTTP endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Dict

from .job_observability_handlers import JsonResponseSpec


@dataclass(frozen=True)
class AuthHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


AuthStatusGetter = Callable[[], Dict[str, Any]]
AuthStarter = Callable[[], Dict[str, Any]]
AuthPoller = Callable[[], Dict[str, Any]]
AuthTokenClearer = Callable[[], None]
ApiKeySaver = Callable[[str, str], None]
RuntimeResetter = Callable[[], None]



def build_auth_key_response(
    data: Any,
    *,
    save_api_key: ApiKeySaver,
    reset_chat_runtime: RuntimeResetter,
    get_auth_status: AuthStatusGetter,
) -> JsonResponseSpec:
    try:
        key = str(data.get("key") or "").strip()
        provider = str(data.get("provider") or "xai").strip()
        if not key:
            raise AuthHandlerError(HTTPStatus.BAD_REQUEST, "key is required")
        save_api_key(key, provider)
        reset_chat_runtime()
        return JsonResponseSpec(
            status=HTTPStatus.OK,
            payload=get_auth_status(),
        )
    except AuthHandlerError:
        raise
    except Exception as exc:
        raise AuthHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc



def build_auth_status_response(
    *,
    get_auth_status: AuthStatusGetter,
) -> JsonResponseSpec:
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload=get_auth_status(),
    )



def build_auth_start_response(
    *,
    start_device_auth: AuthStarter,
) -> JsonResponseSpec:
    try:
        return JsonResponseSpec(
            status=HTTPStatus.OK,
            payload=start_device_auth(),
        )
    except RuntimeError as exc:
        raise AuthHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc



def build_auth_poll_response(
    *,
    poll_device_auth: AuthPoller,
) -> JsonResponseSpec:
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload=poll_device_auth(),
    )



def build_auth_logout_response(
    *,
    clear_tokens: AuthTokenClearer,
) -> JsonResponseSpec:
    clear_tokens()
    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={"success": True},
    )
