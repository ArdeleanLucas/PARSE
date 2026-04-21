import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ai.openai_auth as openai_auth


def test_get_auth_status_prefers_pending_device_flow_over_saved_api_key(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "auth_tokens.json"
    token_path.write_text(
        json.dumps({"direct_api_key": "xai-test-key", "direct_api_key_provider": "xai"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(openai_auth, "_token_path", lambda: token_path)

    with openai_auth._auth_lock:
        openai_auth._auth_state.clear()
        openai_auth._auth_state.update(
            {
                "status": "pending",
                "user_code": "ABCD-1234",
                "verification_uri": "https://auth.openai.com/codex/device",
                "expires_at": time.time() + 600,
            }
        )

    status = openai_auth.get_auth_status()

    assert status == {
        "authenticated": False,
        "flow_active": True,
        "user_code": "ABCD-1234",
        "verification_uri": "https://auth.openai.com/codex/device",
    }



def test_get_auth_status_returns_saved_api_key_when_no_flow_is_active(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "auth_tokens.json"
    token_path.write_text(
        json.dumps({"direct_api_key": "xai-test-key", "direct_api_key_provider": "xai"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(openai_auth, "_token_path", lambda: token_path)

    with openai_auth._auth_lock:
        openai_auth._auth_state.clear()

    status = openai_auth.get_auth_status()

    assert status == {
        "authenticated": True,
        "method": "api_key",
        "provider": "xai",
    }


def test_save_api_key_round_trips_xai_provider(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "auth_tokens.json"
    monkeypatch.setattr(openai_auth, "_token_path", lambda: token_path)
    with openai_auth._auth_lock:
        openai_auth._auth_state.clear()

    openai_auth.save_api_key("xai-key-123", "xai")
    status = openai_auth.get_auth_status()

    assert status["authenticated"] is True
    assert status["method"] == "api_key"
    assert status["provider"] == "xai"
    assert openai_auth.get_api_key() == "xai-key-123"
    assert openai_auth.get_api_key_provider() == "xai"


def test_save_api_key_round_trips_openai_provider(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "auth_tokens.json"
    monkeypatch.setattr(openai_auth, "_token_path", lambda: token_path)
    with openai_auth._auth_lock:
        openai_auth._auth_state.clear()

    openai_auth.save_api_key("sk-openai-key-456", "openai")
    status = openai_auth.get_auth_status()

    assert status["authenticated"] is True
    assert status["method"] == "api_key"
    assert status["provider"] == "openai"
    assert openai_auth.get_api_key() == "sk-openai-key-456"
    assert openai_auth.get_api_key_provider() == "openai"


def test_save_tokens_preserves_existing_direct_api_key(tmp_path, monkeypatch) -> None:
    """Regression: completing OAuth used to overwrite auth_tokens.json with
    just the OAuth fields, silently dropping any API key the user had saved
    previously. save_tokens must merge on top of existing content so both
    auth methods can coexist in the same file."""
    token_path = tmp_path / "auth_tokens.json"
    token_path.write_text(
        json.dumps({"direct_api_key": "xai-key", "direct_api_key_provider": "xai"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(openai_auth, "_token_path", lambda: token_path)

    openai_auth.save_tokens(
        {
            "access_token": "oauth-access",
            "refresh_token": "oauth-refresh",
            "expires_in": 3600,
            "expires": time.time() + 3600,
            "token_type": "Bearer",
        }
    )

    merged = json.loads(token_path.read_text(encoding="utf-8"))
    assert merged["direct_api_key"] == "xai-key"
    assert merged["direct_api_key_provider"] == "xai"
    assert merged["access_token"] == "oauth-access"
    assert merged["refresh_token"] == "oauth-refresh"


def test_save_api_key_preserves_existing_oauth_tokens(tmp_path, monkeypatch) -> None:
    """Symmetric case: saving an API key must not drop OAuth tokens already
    on disk."""
    token_path = tmp_path / "auth_tokens.json"
    token_path.write_text(
        json.dumps(
            {
                "access_token": "oauth-access",
                "refresh_token": "oauth-refresh",
                "expires": time.time() + 3600,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(openai_auth, "_token_path", lambda: token_path)

    openai_auth.save_api_key("xai-key", "xai")

    merged = json.loads(token_path.read_text(encoding="utf-8"))
    assert merged["direct_api_key"] == "xai-key"
    assert merged["direct_api_key_provider"] == "xai"
    assert merged["access_token"] == "oauth-access"
    assert merged["refresh_token"] == "oauth-refresh"
