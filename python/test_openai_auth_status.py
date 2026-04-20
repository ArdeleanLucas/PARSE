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
