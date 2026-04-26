import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.http.auth_handlers import (
    AuthHandlerError,
    build_auth_key_response,
    build_auth_logout_response,
    build_auth_poll_response,
    build_auth_start_response,
    build_auth_status_response,
)


def test_build_auth_key_response_saves_key_resets_runtime_and_refreshes_status() -> None:
    calls: list[tuple[str, object]] = []

    def fake_save_api_key(key: str, provider: str) -> None:
        calls.append(("save", (key, provider)))

    def fake_reset_chat_runtime() -> None:
        calls.append(("reset", None))

    def fake_get_auth_status() -> dict[str, object]:
        calls.append(("status", None))
        return {"authenticated": True, "method": "api_key", "provider": "xai"}

    response = build_auth_key_response(
        {"key": "  xai-key-123  ", "provider": "xai"},
        save_api_key=fake_save_api_key,
        reset_chat_runtime=fake_reset_chat_runtime,
        get_auth_status=fake_get_auth_status,
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {"authenticated": True, "method": "api_key", "provider": "xai"}
    assert calls == [
        ("save", ("xai-key-123", "xai")),
        ("reset", None),
        ("status", None),
    ]


def test_build_auth_key_response_uses_xai_as_default_provider() -> None:
    observed: dict[str, str] = {}

    def fake_save_api_key(key: str, provider: str) -> None:
        observed["key"] = key
        observed["provider"] = provider

    response = build_auth_key_response(
        {"key": "token-with-default-provider"},
        save_api_key=fake_save_api_key,
        reset_chat_runtime=lambda: None,
        get_auth_status=lambda: {"authenticated": True, "provider": "xai"},
    )

    assert response.status == HTTPStatus.OK
    assert observed == {"key": "token-with-default-provider", "provider": "xai"}


@pytest.mark.parametrize("payload", [{}, {"key": "   "}, {"key": None}])
def test_build_auth_key_response_requires_non_blank_key(payload: dict[str, object]) -> None:
    with pytest.raises(AuthHandlerError) as exc_info:
        build_auth_key_response(
            payload,
            save_api_key=lambda key, provider: None,
            reset_chat_runtime=lambda: None,
            get_auth_status=lambda: {},
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "key is required"


def test_build_auth_key_response_maps_unexpected_errors_to_500() -> None:
    def fake_save_api_key(key: str, provider: str) -> None:
        raise RuntimeError("disk write failed")

    with pytest.raises(AuthHandlerError) as exc_info:
        build_auth_key_response(
            {"key": "xai-key"},
            save_api_key=fake_save_api_key,
            reset_chat_runtime=lambda: None,
            get_auth_status=lambda: {},
        )

    assert exc_info.value.status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.message == "disk write failed"


def test_build_auth_status_response_returns_auth_status_payload() -> None:
    response = build_auth_status_response(
        get_auth_status=lambda: {"authenticated": False, "flow_active": False}
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {"authenticated": False, "flow_active": False}


def test_build_auth_start_response_returns_device_flow_payload() -> None:
    response = build_auth_start_response(
        start_device_auth=lambda: {
            "user_code": "ABCD-1234",
            "verification_uri": "https://auth.openai.com/codex/device",
            "interval": 5,
            "expires_in": 600,
        }
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "user_code": "ABCD-1234",
        "verification_uri": "https://auth.openai.com/codex/device",
        "interval": 5,
        "expires_in": 600,
    }


def test_build_auth_start_response_maps_runtime_errors_to_500() -> None:
    with pytest.raises(AuthHandlerError) as exc_info:
        build_auth_start_response(start_device_auth=lambda: (_ for _ in ()).throw(RuntimeError("device flow unavailable")))

    assert exc_info.value.status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert exc_info.value.message == "device flow unavailable"


def test_build_auth_poll_response_returns_poll_payload() -> None:
    response = build_auth_poll_response(
        poll_device_auth=lambda: {"status": "pending"}
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {"status": "pending"}


def test_build_auth_logout_response_clears_tokens_and_returns_success() -> None:
    calls: list[str] = []

    def fake_clear_tokens() -> None:
        calls.append("cleared")

    response = build_auth_logout_response(clear_tokens=fake_clear_tokens)

    assert response.status == HTTPStatus.OK
    assert response.payload == {"success": True}
    assert calls == ["cleared"]
