import json

from compare.providers import grok_llm


def _write_tokens(tmp_path, payload):
    tokens_path = tmp_path / "auth_tokens.json"
    tokens_path.write_text(json.dumps(payload), encoding="utf-8")
    return tokens_path


def test_get_auth_token_reads_legacy_discrete_provider_key(tmp_path, monkeypatch):
    _write_tokens(tmp_path, {"xai": "xai-legacy123"})
    monkeypatch.setattr(grok_llm, "_CONFIG_DIR", tmp_path)

    assert grok_llm._get_auth_token("xai") == "xai-legacy123"


def test_get_auth_token_reads_polymorphic_direct_key_only_for_matching_provider(tmp_path, monkeypatch):
    _write_tokens(
        tmp_path,
        {
            "direct_api_key": "xai-direct123",
            "direct_api_key_provider": "xai",
        },
    )
    monkeypatch.setattr(grok_llm, "_CONFIG_DIR", tmp_path)

    assert grok_llm._get_auth_token("xai") == "xai-direct123"
    assert grok_llm._get_auth_token("openai") is None


def test_get_auth_token_returns_none_for_empty_or_missing_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(grok_llm, "_CONFIG_DIR", tmp_path)
    assert grok_llm._get_auth_token("xai") is None

    _write_tokens(tmp_path, {})
    assert grok_llm._get_auth_token("xai") is None
