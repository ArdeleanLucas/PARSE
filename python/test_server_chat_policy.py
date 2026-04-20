import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
import ai.openai_auth as openai_auth
import ai.provider as provider_module


def test_chat_runtime_policy_uses_saved_xai_provider_defaults(monkeypatch) -> None:
    stub_config = {"chat": {"provider": "openai", "model": "gpt54"}}
    monkeypatch.setattr(server, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: "xai-test-key")
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "xai")

    policy = server._chat_runtime_policy()

    assert policy["provider"] == "xai"
    assert policy["model"] == "grok-3-mini"
    assert policy["apiKeyEnv"] == "XAI_API_KEY"


def test_chat_runtime_policy_preserves_explicit_openai_model(monkeypatch) -> None:
    stub_config = {"chat": {"provider": "openai", "model": "o3"}}
    monkeypatch.setattr(server, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: None)
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "openai")

    policy = server._chat_runtime_policy()

    assert policy["provider"] == "openai"
    assert policy["model"] == "o3"
    assert policy["apiKeyEnv"] == "OPENAI_API_KEY"
