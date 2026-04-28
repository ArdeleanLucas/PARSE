"""Grok LLM provider — LLM-backed IPA lookup via xAI/Grok or OpenAI fallback."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests

from .base import BaseProvider, FetchResult

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

SYSTEM_PROMPT = (
    "You are a linguistics database. For each English concept in the list, "
    "provide the IPA broad transcription(s) for the specified language. "
    "Return ONLY a JSON object mapping each concept to a list of IPA strings. "
    "If a concept has no native word, map it to an empty list. "
    "No prose, no script characters outside IPA, no romanization."
)

_BATCH_SIZE = 15


def _get_ai_config() -> Dict:
    config_path = _CONFIG_DIR / "ai_config.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _get_auth_token(key_provider: str) -> Optional[str]:
    """Look up a saved API key for a given provider.

    Recognizes both auth-token shapes PARSE has written:
    1. Legacy discrete keys: ``{"xai": "...", "openai": "..."}``
    2. Chat-side direct key shape from ``ai.openai_auth.save_api_key``:
       ``{"direct_api_key": "...", "direct_api_key_provider": "xai"}``
    """
    tokens_path = _CONFIG_DIR / "auth_tokens.json"
    if not tokens_path.exists():
        return None
    try:
        with open(tokens_path) as f:
            tokens = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(tokens, dict):
        return None

    legacy = tokens.get(key_provider)
    if isinstance(legacy, str) and legacy.strip():
        return legacy

    direct_provider = str(tokens.get("direct_api_key_provider", "")).strip().lower()
    if direct_provider == key_provider.lower():
        direct_key = tokens.get("direct_api_key")
        if isinstance(direct_key, str) and direct_key.strip():
            return direct_key
    return None


class GrokLlmProvider(BaseProvider):
    name = "grok_llm"

    def __init__(self, ai_config: Dict = None):
        self._ai_config = ai_config or _get_ai_config()

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        for lang_code in language_codes:
            lang_name = language_meta.get(lang_code, {}).get("name", lang_code)
            # Process in batches
            for i in range(0, len(concepts), _BATCH_SIZE):
                batch = concepts[i : i + _BATCH_SIZE]
                result_map = self._fetch_batch(batch, lang_code, lang_name)
                for concept_en in batch:
                    forms = result_map.get(concept_en, [])
                    yield FetchResult(
                        concept_en=concept_en,
                        language_code=lang_code,
                        forms=forms,
                        source="grok_llm",
                    )

    def _fetch_batch(self, concepts: List[str], lang_code: str, lang_name: str) -> Dict[str, List[str]]:
        empty = {c: [] for c in concepts}
        user_msg = (
            "Language: {} (ISO 639: {})\n"
            "Concepts: {}\n"
            "Return JSON mapping each concept to a list of IPA strings."
        ).format(lang_name, lang_code, json.dumps(concepts))

        # Try xAI first, then OpenAI
        for attempt in range(2):
            response_text = self._call_llm(user_msg, attempt_retry=(attempt == 1))
            if response_text is None:
                continue
            try:
                parsed = json.loads(response_text)
                if isinstance(parsed, dict):
                    result = {}
                    for c in concepts:
                        val = parsed.get(c, [])
                        if isinstance(val, list):
                            result[c] = [str(v) for v in val if v]
                        elif isinstance(val, str) and val:
                            result[c] = [val]
                        else:
                            result[c] = []
                    return result
            except (json.JSONDecodeError, TypeError):
                if attempt == 0:
                    continue
        return empty

    def _call_llm(self, user_msg: str, attempt_retry: bool = False) -> Optional[str]:
        # Try xAI / Grok
        xai_key = _get_auth_token("xai") or self._ai_config.get("xai_api_key")
        if xai_key:
            result = self._call_api(
                url="https://api.x.ai/v1/chat/completions",
                api_key=xai_key,
                model=self._ai_config.get("xai_model", "grok-beta"),
                user_msg=user_msg,
                retry_msg="Return ONLY valid JSON." if attempt_retry else None,
            )
            if result is not None:
                return result

        # Fall back to OpenAI
        openai_key = _get_auth_token("openai") or self._ai_config.get("openai_api_key")
        if openai_key:
            result = self._call_api(
                url="https://api.openai.com/v1/chat/completions",
                api_key=openai_key,
                model=self._ai_config.get("openai_model", "gpt-4o-mini"),
                user_msg=user_msg,
                retry_msg="Return ONLY valid JSON." if attempt_retry else None,
            )
            if result is not None:
                return result

        return None

    def _call_api(
        self,
        url: str,
        api_key: str,
        model: str,
        user_msg: str,
        retry_msg: Optional[str] = None,
    ) -> Optional[str]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        if retry_msg:
            messages.append({"role": "user", "content": retry_msg})

        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.1,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            print("[grok_llm] API call failed: {}".format(exc), file=sys.stderr)
            return None
