import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
import ai.openai_auth as openai_auth
import ai.provider as provider_module


def test_chat_runtime_policy_uses_saved_xai_provider_defaults(monkeypatch) -> None:
    stub_config = {"chat": {"provider": "openai", "model": "gpt-5.4"}}
    monkeypatch.setattr(server, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: "xai-test-key")
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "xai")

    policy = server._chat_runtime_policy()

    assert policy["provider"] == "xai"
    assert policy["model"] == "grok-4.20-0309-reasoning"
    assert policy["apiKeyEnv"] == "XAI_API_KEY"


def test_chat_runtime_policy_defaults_openai_to_gpt_5_4(monkeypatch) -> None:
    stub_config = {"chat": {"provider": "openai"}}
    monkeypatch.setattr(server, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: None)
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "openai")

    policy = server._chat_runtime_policy()

    assert policy["provider"] == "openai"
    assert policy["model"] == "gpt-5.4"
    assert policy["apiKeyEnv"] == "OPENAI_API_KEY"
    assert policy["reasoningEffort"] == "high"


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


def test_chat_runtime_policy_rewrites_legacy_gpt54_placeholder(monkeypatch) -> None:
    stub_config = {"chat": {"provider": "openai", "model": "gpt54"}}
    monkeypatch.setattr(server, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: None)
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "openai")

    policy = server._chat_runtime_policy()

    assert policy["provider"] == "openai"
    assert policy["model"] == "gpt-5.4"


def test_openai_provider_defaults_to_gpt_5_4(monkeypatch) -> None:
    stub_config = {"llm": {"provider": "openai"}}
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)

    provider = provider_module.OpenAIProvider(config={"llm": {"provider": "openai"}})

    assert provider.llm_model == "gpt-5.4"


def test_openai_provider_rewrites_legacy_gpt54_placeholder(monkeypatch) -> None:
    stub_config = {"llm": {"provider": "openai", "model": "gpt54"}}
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)

    provider = provider_module.OpenAIProvider(config={"llm": {"provider": "openai", "model": "gpt54"}})

    assert provider.llm_model == "gpt-5.4"


def test_xai_provider_rewrites_gpt_5_4_placeholder_model(monkeypatch) -> None:
    stub_config = {"llm": {"provider": "xai", "model": "gpt-5.4"}}
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)

    provider = provider_module.XAIProvider(config={"llm": {"provider": "xai", "model": "gpt-5.4"}})

    assert provider.llm_model == "grok-4.20-0309-reasoning"


def test_xai_provider_rewrites_legacy_gpt54_placeholder_model(monkeypatch) -> None:
    stub_config = {"llm": {"provider": "xai", "model": "gpt54"}}
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)

    provider = provider_module.XAIProvider(config={"llm": {"provider": "xai", "model": "gpt54"}})

    assert provider.llm_model == "grok-4.20-0309-reasoning"


def test_chat_runtime_policy_omits_reasoning_effort_for_xai_grok(monkeypatch) -> None:
    stub_config = {
        "chat": {
            "provider": "xai",
            "model": "grok-4.20-0309-reasoning",
            "reasoning_effort": "high",
        }
    }
    monkeypatch.setattr(server, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: None)
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "xai")

    policy = server._chat_runtime_policy()

    assert policy["provider"] == "xai"
    assert policy["model"] == "grok-4.20-0309-reasoning"
    assert policy["reasoningEffort"] == ""


class _FakeCompletionsClient:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


class _FakeChatClient:
    def __init__(self) -> None:
        self.chat = type("ChatAPI", (), {"completions": _FakeCompletionsClient()})()


def test_openai_chat_runtime_skips_reasoning_params_for_xai_grok(monkeypatch) -> None:
    stub_config = {
        "chat": {
            "provider": "xai",
            "model": "grok-4.20-0309-reasoning",
            "reasoning_effort": "high",
        }
    }
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: None)
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "xai")

    runtime = provider_module.OpenAIChatRuntime(config=stub_config)
    fake_client = _FakeChatClient()
    monkeypatch.setattr(runtime, "_load_client", lambda: fake_client)

    _response, meta = runtime.complete([{"role": "user", "content": "hello"}])
    sent = fake_client.chat.completions.calls[-1]

    assert runtime.reasoning_effort == ""
    assert "reasoning" not in sent
    assert "reasoning_effort" not in sent
    assert meta["reasoningApplied"] is False
    assert meta["reasoningAttempt"] == "none"
    assert meta["reasoningConfigured"] == ""


def test_openai_chat_runtime_keeps_reasoning_params_for_openai(monkeypatch) -> None:
    stub_config = {
        "chat": {
            "provider": "openai",
            "model": "gpt-5.4",
            "reasoning_effort": "high",
        }
    }
    monkeypatch.setattr(provider_module, "load_ai_config", lambda config_path=None: stub_config)
    monkeypatch.setattr(openai_auth, "get_api_key", lambda: None)
    monkeypatch.setattr(openai_auth, "get_api_key_provider", lambda: "openai")

    runtime = provider_module.OpenAIChatRuntime(config=stub_config)
    fake_client = _FakeChatClient()
    monkeypatch.setattr(runtime, "_load_client", lambda: fake_client)

    _response, meta = runtime.complete([{"role": "user", "content": "hello"}])
    sent = fake_client.chat.completions.calls[-1]

    assert runtime.reasoning_effort == "high"
    assert sent["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in sent
    assert meta["reasoningApplied"] is True
    assert meta["reasoningAttempt"] == "reasoning"
    assert meta["reasoningConfigured"] == "high"
