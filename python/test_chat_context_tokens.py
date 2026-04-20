"""Context-window tracking: tokens_used flows from runtime → session → API payload."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
import ai.provider as provider_module


def test_extract_total_tokens_from_object_response() -> None:
    class FakeUsage:
        total_tokens = 1234

    class FakeResponse:
        usage = FakeUsage()

    assert provider_module._extract_total_tokens(FakeResponse()) == 1234


def test_extract_total_tokens_from_dict_response() -> None:
    response = {"usage": {"total_tokens": 4096}}
    assert provider_module._extract_total_tokens(response) == 4096


def test_extract_total_tokens_handles_missing_usage() -> None:
    assert provider_module._extract_total_tokens(object()) is None
    assert provider_module._extract_total_tokens({"choices": []}) is None
    assert provider_module._extract_total_tokens({"usage": {}}) is None
    assert provider_module._extract_total_tokens({"usage": {"total_tokens": "nope"}}) is None


def test_resolve_context_window_known_models() -> None:
    assert provider_module.resolve_context_window("gpt-5.4") == 128000
    assert provider_module.resolve_context_window("grok-4.20-0309-reasoning") == 131072
    assert provider_module.resolve_context_window("o3") == 200000


def test_resolve_context_window_unknown_returns_default() -> None:
    assert provider_module.resolve_context_window("mystery-model") == provider_module._CHAT_CONTEXT_WINDOW_DEFAULT
    assert provider_module.resolve_context_window(None) == provider_module._CHAT_CONTEXT_WINDOW_DEFAULT


def test_chat_session_payload_surfaces_tokens_used_and_limit(monkeypatch) -> None:
    stub_config = {"chat": {"provider": "openai", "model": "gpt-5.4"}}
    monkeypatch.setattr(server, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    import ai.openai_auth as openai_auth
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: None)
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "openai")

    session = {
        "sessionId": "chat_xyz",
        "created_at": "2026-04-20T22:00:00Z",
        "updated_at": "2026-04-20T22:01:00Z",
        "messages": [
            {"role": "user", "content": "hi", "created_at": "2026-04-20T22:00:30Z"},
            {
                "role": "assistant",
                "content": "hello",
                "created_at": "2026-04-20T22:00:45Z",
                "meta": {"tokensUsed": 3200, "model": "gpt-5.4"},
            },
        ],
    }
    payload = server._chat_session_public_payload(session)

    assert payload["tokensUsed"] == 3200
    assert payload["tokensLimit"] == 128000
    assert len(payload["messages"]) == 2


def test_chat_session_payload_tokens_used_null_without_meta(monkeypatch) -> None:
    stub_config = {"chat": {"provider": "openai", "model": "gpt-5.4"}}
    monkeypatch.setattr(server, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    import ai.openai_auth as openai_auth
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: None)
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "openai")

    session = {
        "sessionId": "chat_xyz",
        "created_at": "2026-04-20T22:00:00Z",
        "updated_at": "2026-04-20T22:00:00Z",
        "messages": [],
    }
    payload = server._chat_session_public_payload(session)

    assert payload["tokensUsed"] is None
    assert payload["tokensLimit"] == 128000
