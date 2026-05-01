from __future__ import annotations

import copy
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ORTH_DEFAULT_INITIAL_PROMPT = (
    "کوڕ و کچ. مال و باخ. ئاو و خاک. هاتن و چوون. ئەم زمانە کوردیە."
)

_DEFAULT_AI_CONFIG: Dict[str, Any] = {
    "stt": {
        "provider": "faster-whisper",
        "model_path": "",
        # Empty string = let Whisper auto-detect the language. We used to
        # default to "sd" (Sindhi), but the project's Southern Kurdish audio
        # isn't in Whisper's supported language list and forcing Sindhi made
        # the decoder hallucinate (produced 'ايقIt is not legal'-style
        # garbage). Auto-detect lands on Persian (fa) — a close relative —
        # and produces coherent Kurdish-script output.
        "language": "",
        "device": "cuda",
        "compute_type": "float16",
        "beam_size": 5,
        # "transcribe" preserves the detected language. Set to "translate"
        # if you want an English gloss of the speech.
        "task": "transcribe",
        # VAD gates silence out of the audio before decoding. Keep it on —
        # vad_filter=False produces hallucination loops in long silences
        # (e.g. repeating 'شوال' 5x during a 10s pause). Parameters below
        # are tunable; leave as {} to use faster-whisper's Silero defaults.
        "vad_filter": True,
        "vad_parameters": {},
    },
    # Tier 3 acoustic alignment: wav2vec2 is the ONLY IPA engine. Text-based
    # paths (Epitran, LLM prompts, Arabic-to-IPA rules) have been removed.
    # The ``engine`` key is informational — the code path is hard-wired to
    # facebook/wav2vec2-xlsr-53-espeak-cv-ft via ai.forced_align.Aligner.
    "ipa": {
        "engine": "wav2vec2",
        "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
    },
    "ortho": {
        "backend": "hf",
        # ORTH defaults to the original HF Transformers Razhan SDH model. The
        # legacy CT2/faster-whisper backend remains selectable via
        # ortho.backend="faster-whisper" with a CT2 directory model_path.
        "model_path": "razhan/whisper-base-sdh",
        "language": "sd",
        "device": "cuda",
        # The following keys are accepted for legacy faster-whisper/CT2 ORTH
        # configs but are intentionally not applied by the HF FP32 backend.
        "compute_type": "float16",
        "vad_filter": True,
        "vad_parameters": {
            "min_silence_duration_ms": 500,
            "threshold": 0.35,
        },
        "condition_on_previous_text": False,
        "compression_ratio_threshold": 1.8,
        "initial_prompt": _ORTH_DEFAULT_INITIAL_PROMPT,
        # When True the ORTH compute runner will also do a short-clip
        # Whisper pass per concept after Tier-2 forced alignment. Off by
        # default — opt in per speaker via the compute payload or per
        # machine via ai_config.json.
        "refine_lexemes": False,
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-5.4",
        "api_key_env": "OPENAI_API_KEY",
    },
    "chat": {
        "enabled": True,
        "read_only": False,
        "attachments_supported": False,
        "provider": "openai",
        "model": "gpt-5.4",
        "api_key_env": "OPENAI_API_KEY",
        "reasoning_effort": "high",
        "temperature": 0.1,
        "max_tool_rounds": 4,
        "max_history_messages": 24,
        "max_output_tokens": 1400,
        "max_tool_result_chars": 24000,
        "max_user_message_chars": 8000,
        "max_session_messages": 200,
    },
    "specialized_layers": [],
}
_CHAT_PROVIDER_BASE_URLS: Dict[str, str] = {
    "xai": "https://api.x.ai/v1",
    "grok": "https://api.x.ai/v1",
    "x.ai": "https://api.x.ai/v1",
}
_CHAT_PROVIDER_DEFAULT_MODELS: Dict[str, str] = {
    "xai": "grok-4.20-0309-reasoning",
    "grok": "grok-4.20-0309-reasoning",
    "x.ai": "grok-4.20-0309-reasoning",
    "openai": "gpt-5.4",
}
_LEGACY_OPENAI_MODEL_NAMES = {
    "gpt54": "gpt-5.4",
}
_CHAT_OPENAI_ONLY_MODELS = {
    "gpt54",
    "gpt-4o",
    "gpt-5.4",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
}
_CHAT_SUPPORTED_PROVIDERS = {"openai", "xai", "grok", "x.ai"}
_CHAT_MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    "gpt-5.4": 128000,
    "gpt-4o": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16384,
    "o1": 200000,
    "o1-mini": 128000,
    "o1-preview": 128000,
    "o3": 200000,
    "o3-mini": 200000,
    "grok-4.20-0309-reasoning": 131072,
}
_CHAT_CONTEXT_WINDOW_DEFAULT = 32000
_CUDA_RUNTIME_FAILURE_MARKERS = (
    "cublas",
    "cudnn",
    "cuda",
    "is not found or cannot be loaded",
    "could not load library",
    "no cuda-capable device",
    "no cuda gpus are available",
    "cuda driver version is insufficient",
    "cublasstatus",
)
_HF_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")

def resolve_context_window(model_name: Any) -> int:
    """Return the approximate context window (in tokens) for a chat model."""
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return _CHAT_CONTEXT_WINDOW_DEFAULT
    if normalized in _CHAT_MODEL_CONTEXT_WINDOWS:
        return _CHAT_MODEL_CONTEXT_WINDOWS[normalized]
    for prefix, window in _CHAT_MODEL_CONTEXT_WINDOWS.items():
        if normalized.startswith(prefix):
            return window
    return _CHAT_CONTEXT_WINDOW_DEFAULT
def _extract_total_tokens(response: Any) -> Optional[int]:
    """Pull usage.total_tokens from an SDK response, tolerating object or dict shapes."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    if total is None and isinstance(usage, dict):
        total = usage.get("total_tokens")
    if total is None:
        return None
    try:
        total_int = int(total)
    except (TypeError, ValueError):
        return None
    return total_int if total_int >= 0 else None
def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dictionaries without mutating inputs."""
    merged: Dict[str, Any] = copy.deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)

    return merged
def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerce loose boolean-like values with a safe default."""
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "disabled"}:
            return False

    return bool(default)
def _normalize_openai_model_name(model_name: Any, default: str = "gpt-5.4") -> str:
    """Rewrite legacy OpenAI placeholder model names to the canonical default."""
    normalized = str(model_name or "").strip()
    if not normalized:
        return default
    return _LEGACY_OPENAI_MODEL_NAMES.get(normalized, normalized)
def _chat_supports_reasoning_effort(provider_name: Any, model_name: Any) -> bool:
    """Return True when the resolved chat provider/model should receive reasoning hints."""
    provider = str(provider_name or "").strip().lower()
    model = str(model_name or "").strip().lower()
    if provider in _CHAT_PROVIDER_BASE_URLS:
        return False
    if model.startswith("grok"):
        return False
    return True
def _coerce_int(
    value: Any,
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Coerce integer values with optional clamping."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)

    if minimum is not None and number < minimum:
        number = minimum

    if maximum is not None and number > maximum:
        number = maximum

    return number
def _coerce_float(
    value: Any,
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """Coerce float values with optional clamping."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)

    if minimum is not None and number < minimum:
        number = minimum

    if maximum is not None and number > maximum:
        number = maximum

    return number
def resolve_ai_config_path(config_path: Optional[Path] = None) -> Path:
    """Resolve ai_config.json path.

    Search order (first match wins):
      1. ``config_path`` arg, if provided.
      2. ``PARSE_AI_CONFIG`` env var (escape hatch for operators).
      3. ``<cwd>/config/ai_config.json`` — matches server.py's ``_config_path()``
         which reads from cwd. The server runs with cwd set to the
         project workspace (e.g. ``/home/lucas/parse-workspace``), so
         this is where the user's real config lives.
      4. ``<repo>/config/ai_config.json`` — the historical location,
         relative to this module's path. Kept as a fallback for
         scripts/tests that import ``load_ai_config`` without a
         meaningful cwd.

    Returns the *first existing* path, else the repo path (so the
    "missing" WARN in ``load_ai_config`` surfaces a coherent message).

    Fixes a silent bug where the server reported
    ``stt.model_path: C:\\...razhan-whisper-ct2`` via ``/api/config``
    (which reads from cwd) while ``get_stt_provider()`` fell back to
    defaults — because this function was only checking the repo path,
    which is empty on a fresh deploy. ORTH in particular needs razhan
    configured; defaults hand it the HF repo id which faster-whisper
    can't load, and every ORTH run silently errored.
    """
    if config_path is not None:
        return Path(config_path).expanduser().resolve()

    env_override = os.environ.get("PARSE_AI_CONFIG", "").strip()
    if env_override:
        return Path(env_override).expanduser().resolve()

    cwd_candidate = Path.cwd() / "config" / "ai_config.json"
    if cwd_candidate.exists():
        return cwd_candidate.resolve()

    return Path(__file__).resolve().parents[2] / "config" / "ai_config.json"
def load_ai_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load AI config with schema defaults applied."""
    resolved_path = resolve_ai_config_path(config_path)
    defaults = copy.deepcopy(_DEFAULT_AI_CONFIG)

    if not resolved_path.exists():
        print(
            "[WARN] AI config not found at {0}; using defaults".format(resolved_path),
            file=sys.stderr,
        )
        return defaults

    try:
        raw_data = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            "[WARN] Failed to read AI config {0}: {1}; using defaults".format(
                resolved_path, exc
            ),
            file=sys.stderr,
        )
        return defaults

    if not isinstance(raw_data, dict):
        print(
            "[WARN] Invalid AI config root (expected object); using defaults",
            file=sys.stderr,
        )
        return defaults

    return _deep_merge_dicts(defaults, raw_data)
def _build_chat_config(merged_config: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve chat config from merged defaults/user config.

    Chat is OpenAI-compatible (OpenAI or xAI). ``read_only`` is honored from
    config (env ``PARSE_CHAT_READ_ONLY`` also overrides it at orchestrator
    construction). Attachments remain unsupported.
    """
    llm_config = merged_config.get("llm", {})
    if not isinstance(llm_config, dict):
        llm_config = {}

    chat_config = merged_config.get("chat", {})
    if not isinstance(chat_config, dict):
        chat_config = {}

    defaults = {
        "enabled": True,
        "read_only": False,
        "attachments_supported": False,
        "provider": "openai",
        "model": str(chat_config.get("model") or llm_config.get("model") or "gpt-5.4").strip() or "gpt-5.4",
        "api_key_env": str(chat_config.get("api_key_env") or llm_config.get("api_key_env") or "OPENAI_API_KEY").strip()
        or "OPENAI_API_KEY",
        "reasoning_effort": str(chat_config.get("reasoning_effort") or "high").strip() or "high",
        "temperature": chat_config.get("temperature", 0.1),
        "max_tool_rounds": chat_config.get("max_tool_rounds", 4),
        "max_history_messages": chat_config.get("max_history_messages", 24),
        "max_output_tokens": chat_config.get("max_output_tokens", 1400),
        "max_tool_result_chars": chat_config.get("max_tool_result_chars", 24000),
        "max_user_message_chars": chat_config.get("max_user_message_chars", 8000),
        "max_session_messages": chat_config.get("max_session_messages", 200),
    }

    resolved = _deep_merge_dicts(defaults, chat_config)

    stored_provider = ""
    try:
        from ..openai_auth import get_api_key as _get_direct_key, get_api_key_provider as _get_provider

        if (_get_direct_key() or "").strip():
            stored_provider = str(_get_provider() or "").strip().lower()
    except Exception:
        stored_provider = ""

    provider_name = str(resolved.get("provider") or "openai").strip().lower()
    if stored_provider in _CHAT_SUPPORTED_PROVIDERS:
        provider_name = stored_provider
    if provider_name not in _CHAT_SUPPORTED_PROVIDERS:
        print(
            "[WARN] chat.provider={0!r} is unsupported; forcing 'openai'".format(provider_name),
            file=sys.stderr,
        )
        provider_name = "openai"
    resolved["provider"] = provider_name

    model_name = _normalize_openai_model_name(resolved.get("model"), default="")
    if provider_name in _CHAT_PROVIDER_BASE_URLS and model_name in _CHAT_OPENAI_ONLY_MODELS:
        model_name = _CHAT_PROVIDER_DEFAULT_MODELS[provider_name]
    resolved["model"] = model_name or _CHAT_PROVIDER_DEFAULT_MODELS.get(provider_name, "gpt-5.4")

    api_key_env = str(resolved.get("api_key_env") or "").strip()
    if provider_name in _CHAT_PROVIDER_BASE_URLS and (not api_key_env or api_key_env == "OPENAI_API_KEY"):
        api_key_env = "XAI_API_KEY"
    resolved["api_key_env"] = api_key_env or "OPENAI_API_KEY"

    base_url = str(resolved.get("base_url") or "").strip()
    if not base_url and provider_name in _CHAT_PROVIDER_BASE_URLS:
        base_url = _CHAT_PROVIDER_BASE_URLS[provider_name]
    resolved["base_url"] = base_url

    reasoning_effort = str(resolved.get("reasoning_effort") or "").strip().lower()
    if _chat_supports_reasoning_effort(provider_name, resolved.get("model")):
        if reasoning_effort not in {"minimal", "low", "medium", "high"}:
            reasoning_effort = "high"
    else:
        reasoning_effort = ""
    resolved["reasoning_effort"] = reasoning_effort

    resolved["enabled"] = _coerce_bool(resolved.get("enabled"), True)
    resolved["temperature"] = _coerce_float(resolved.get("temperature"), 0.1, minimum=0.0, maximum=2.0)
    resolved["max_tool_rounds"] = _coerce_int(resolved.get("max_tool_rounds"), 4, minimum=1, maximum=8)
    resolved["max_history_messages"] = _coerce_int(resolved.get("max_history_messages"), 24, minimum=1, maximum=64)
    resolved["max_output_tokens"] = _coerce_int(resolved.get("max_output_tokens"), 1400, minimum=128, maximum=8192)
    resolved["max_tool_result_chars"] = _coerce_int(
        resolved.get("max_tool_result_chars"),
        24000,
        minimum=2000,
        maximum=200000,
    )
    resolved["max_user_message_chars"] = _coerce_int(
        resolved.get("max_user_message_chars"),
        8000,
        minimum=500,
        maximum=50000,
    )
    resolved["max_session_messages"] = _coerce_int(
        resolved.get("max_session_messages"),
        200,
        minimum=10,
        maximum=1000,
    )

    resolved["read_only"] = _coerce_bool(resolved.get("read_only"), False)

    attachments_supported = _coerce_bool(resolved.get("attachments_supported"), False)
    if attachments_supported:
        print(
            "[WARN] chat.attachments_supported=true is unsupported in MVP; forcing false",
            file=sys.stderr,
        )
    resolved["attachments_supported"] = False

    return resolved
def _coerce_confidence(value: float) -> float:
    """Clamp confidence score to [0, 1]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
def _confidence_from_logprob(avg_logprob: Any) -> float:
    """Convert avg_logprob to a bounded confidence score."""
    if avg_logprob is None:
        return 0.0

    try:
        numeric = float(avg_logprob)
    except (TypeError, ValueError):
        return 0.0

    if numeric <= 0.0:
        return _coerce_confidence(math.exp(numeric))

    return _coerce_confidence(numeric)
def _dict_or_attr(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from dict-like or object-like values."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)
def _extract_word_spans(segment: Any) -> List[Dict[str, Any]]:
    """Pull per-word spans from a faster-whisper Segment when available.

    Returns an empty list for providers/modes that don't produce word-level
    timestamps so SegmentWithWords.words can be omitted cleanly.
    """
    raw_words = _dict_or_attr(segment, "words", None)
    if not raw_words:
        return []
    out: List[Dict[str, Any]] = []
    for w in raw_words:
        text = str(_dict_or_attr(w, "word", "") or "").strip()
        if not text:
            continue
        try:
            start = float(_dict_or_attr(w, "start", 0.0) or 0.0)
            end = float(_dict_or_attr(w, "end", start) or start)
        except (TypeError, ValueError):
            continue
        prob_raw = _dict_or_attr(w, "probability", None)
        entry: Dict[str, Any] = {"word": text, "start": start, "end": end}
        if prob_raw is not None:
            try:
                entry["prob"] = _coerce_confidence(float(prob_raw))
            except (TypeError, ValueError):
                pass
        out.append(entry)
    return out
def _looks_like_cuda_runtime_failure(message: str) -> bool:
    """Heuristic — the GPU init failed because of a missing/broken CUDA runtime."""
    text = (message or "").lower()
    return any(marker in text for marker in _CUDA_RUNTIME_FAILURE_MARKERS)
def _stt_force_cpu_env() -> bool:
    """Respect PARSE_STT_FORCE_CPU as an emergency escape hatch."""
    value = os.environ.get("PARSE_STT_FORCE_CPU", "").strip().lower()
    return value in {"1", "true", "yes", "on"}
def _looks_like_hf_repo_id(value: str) -> bool:
    """Distinguish a HuggingFace repo id (``org/name``) from a filesystem path.

    HF ids are two simple segments with a forward slash. Local paths can
    contain forward slashes too (POSIX absolute paths, WSL paths with
    forward slashes) so we check for disqualifying markers first:
    drive letters, leading slashes, backslashes, or more than one slash.
    """
    text = str(value or "").strip()
    if not text:
        return False
    if "\\" in text:
        return False
    if text.startswith(("/", ".")) or (len(text) >= 2 and text[1] == ":"):
        return False
    return bool(_HF_REPO_ID_RE.match(text))
def _collect_nvidia_wheel_bin_dirs() -> List[Path]:
    """Return ``<site-packages>/nvidia/<subpkg>/bin`` dirs for every
    installed NVIDIA wheel (cublas, cudnn, cuda-runtime, …).

    ``nvidia`` is a PEP-420 *namespace* package — there is no
    ``nvidia/__init__.py``, so ``nvidia.__file__`` is ``None``. We
    must iterate ``nvidia.__path__`` (a list of directories that
    contribute to the namespace) to find the subpackage roots.

    A prior revision used ``Path(nvidia.__file__).resolve().parent``
    which raises ``TypeError`` when ``__file__`` is ``None``. The
    enclosing ``except Exception: pass`` swallowed it, so no DLL
    directories ever got registered — faster-whisper silently fell
    back to CPU at the first cuBLAS call. This helper is the fix;
    the bottom of ``test_ortho_provider_fallback.py`` locks the
    behaviour in.
    """
    results: List[Path] = []
    try:
        import nvidia  # type: ignore[import-not-found]
    except ImportError:
        return results

    # __path__ can be a list of str OR a _NamespacePath — iterate uniformly.
    roots: List[str] = []
    try:
        roots = list(nvidia.__path__)  # type: ignore[attr-defined]
    except TypeError:
        return results

    for root_str in roots:
        try:
            nvidia_root = Path(root_str)
        except Exception:
            continue
        if not nvidia_root.is_dir():
            continue
        for entry in nvidia_root.iterdir():
            bin_dir = entry / "bin"
            if bin_dir.is_dir():
                results.append(bin_dir)
    return results
def _audio_duration_seconds(audio_path: Path) -> float:
    """Read audio duration using soundfile."""
    try:
        import soundfile as sf
    except ImportError:
        return 0.0

    try:
        info = sf.info(str(audio_path))
    except Exception:
        return 0.0

    duration = float(getattr(info, "duration", 0.0) or 0.0)
    if duration < 0.0:
        return 0.0
    return duration

__all__ = [
    "_DEFAULT_AI_CONFIG",
    "_ORTH_DEFAULT_INITIAL_PROMPT",
    "_CHAT_PROVIDER_BASE_URLS",
    "_CHAT_PROVIDER_DEFAULT_MODELS",
    "_LEGACY_OPENAI_MODEL_NAMES",
    "_CHAT_OPENAI_ONLY_MODELS",
    "_CHAT_SUPPORTED_PROVIDERS",
    "_CHAT_MODEL_CONTEXT_WINDOWS",
    "_CHAT_CONTEXT_WINDOW_DEFAULT",
    "_CUDA_RUNTIME_FAILURE_MARKERS",
    "_HF_REPO_ID_RE",
    "resolve_context_window",
    "_extract_total_tokens",
    "_deep_merge_dicts",
    "_coerce_bool",
    "_normalize_openai_model_name",
    "_chat_supports_reasoning_effort",
    "_coerce_int",
    "_coerce_float",
    "resolve_ai_config_path",
    "load_ai_config",
    "_build_chat_config",
    "_coerce_confidence",
    "_confidence_from_logprob",
    "_dict_or_attr",
    "_extract_word_spans",
    "_looks_like_cuda_runtime_failure",
    "_stt_force_cpu_env",
    "_looks_like_hf_repo_id",
    "_collect_nvidia_wheel_bin_dirs",
    "_audio_duration_seconds",
]
