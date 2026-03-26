#!/usr/bin/env python3
"""AI provider abstraction for PARSE.

This module defines a shared provider interface plus concrete providers for:
- local faster-whisper (STT + local IPA fallback)
- OpenAI API
- Ollama local LLM
"""

import abc
import copy
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict


class Segment(TypedDict):
    """Timestamped STT segment."""

    start: float
    end: float
    text: str
    confidence: float


_DEFAULT_AI_CONFIG: Dict[str, Any] = {
    "stt": {
        "provider": "faster-whisper",
        "model_path": "",
        "language": "sd",
        "device": "cuda",
        "compute_type": "float16",
    },
    "ipa": {
        "provider": "local",
        "model": "epitran",
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
    },
    "specialized_layers": [],
}


def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dictionaries without mutating inputs."""
    merged: Dict[str, Any] = copy.deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)

    return merged


def resolve_ai_config_path(config_path: Optional[Path] = None) -> Path:
    """Resolve ai_config.json path, defaulting to parse/config/ai_config.json."""
    if config_path is not None:
        return Path(config_path).expanduser().resolve()

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


def _strip_ipa_wrappers(text: str) -> str:
    """Remove common IPA wrappers (/.../, [...], leading labels)."""
    value = str(text).strip()
    value = re.sub(r"^\s*ipa\s*:\s*", "", value, flags=re.IGNORECASE)

    if value.startswith("/") and value.endswith("/") and len(value) > 1:
        value = value[1:-1].strip()
    if value.startswith("[") and value.endswith("]") and len(value) > 1:
        value = value[1:-1].strip()

    return value


def _dict_or_attr(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from dict-like or object-like values."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


_ARABIC_DIACRITICS = {
    "\u064b",  # tanwin fatha
    "\u064c",  # tanwin damma
    "\u064d",  # tanwin kasra
    "\u064e",  # fatha
    "\u064f",  # damma
    "\u0650",  # kasra
    "\u0651",  # shadda
    "\u0652",  # sukun
    "\u0670",  # superscript alef
    "\u0653",  # maddah
    "\u0654",  # hamza above
    "\u0655",  # hamza below
}

_SOUTHERN_KURDISH_CHAR_MAP: Dict[str, str] = {
    "ا": "a",
    "أ": "a",
    "إ": "a",
    "آ": "a",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ث": "s",
    "ج": "dʒ",
    "چ": "tʃ",
    "ح": "h",
    "خ": "x",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ڕ": "r",
    "ز": "z",
    "ژ": "ʒ",
    "س": "s",
    "ش": "ʃ",
    "ع": "ʕ",
    "غ": "ɣ",
    "ف": "f",
    "ڤ": "v",
    "ق": "q",
    "ک": "k",
    "ك": "k",
    "گ": "g",
    "ل": "l",
    "ڵ": "ɫ",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "ھ": "h",
    "ة": "e",
    "ە": "e",
    "ێ": "e",
    "ۆ": "o",
    "ئ": "ʔ",
    "ء": "ʔ",
}

_SOUTHERN_KURDISH_DIGRAPHS = {
    "وو": "u",
}


def _is_probably_arabic_script(text: str) -> bool:
    """Return True if text appears to use Arabic-script code points."""
    for char in text:
        code = ord(char)
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
            return True
    return False


def southern_kurdish_arabic_to_ipa(text: str) -> str:
    """Best-effort Arabic-script Southern Kurdish -> IPA fallback.

    This is intentionally lightweight and dependency-free, used when local IPA
    backends are unavailable. It is not a full phonological model.
    """
    normalized = str(text)
    normalized = normalized.replace("\u200c", "")
    normalized = normalized.replace("\u200d", "")

    for source, target in _SOUTHERN_KURDISH_DIGRAPHS.items():
        normalized = normalized.replace(source, target)

    output: List[str] = []
    for index, char in enumerate(normalized):
        if char in _ARABIC_DIACRITICS:
            continue

        if char in {"\n", "\r", "\t"}:
            output.append(" ")
            continue

        if char.isspace():
            output.append(" ")
            continue

        if char in {"ی", "ي", "ى"}:
            prev_is_space = index == 0 or normalized[index - 1].isspace()
            output.append("j" if prev_is_space else "i")
            continue

        if char == "و":
            prev_is_space = index == 0 or normalized[index - 1].isspace()
            output.append("w" if prev_is_space else "u")
            continue

        mapped = _SOUTHERN_KURDISH_CHAR_MAP.get(char)
        if mapped is not None:
            output.append(mapped)
            continue

        if char.isascii() and (char.isalnum() or char in "-_'"):
            output.append(char.lower())
            continue

    ipa = "".join(output)
    ipa = re.sub(r"\s+", " ", ipa).strip()
    return ipa


def _epitran_code_for_language(language: Optional[str]) -> Optional[str]:
    """Resolve best-effort Epitran code from a language code."""
    if not language:
        return "kur-Arab"

    normalized = str(language).strip().lower()
    if not normalized:
        return "kur-Arab"

    mapping = {
        "sdh": "kur-Arab",
        "ckb": "kur-Arab",
        "ku": "kur-Arab",
        "kur": "kur-Arab",
        "sd": "snd-Arab",
        "fa": "fas-Arab",
        "fas": "fas-Arab",
        "ar": "ara-Arab",
        "ara": "ara-Arab",
    }

    if normalized in mapping:
        return mapping[normalized]

    if "-" in normalized:
        return normalized

    return None


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


class AIProvider(abc.ABC):
    """Abstract AI provider interface used throughout PARSE."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.config_path = resolve_ai_config_path(config_path)
        file_config = load_ai_config(self.config_path)
        self.config = _deep_merge_dicts(file_config, config or {})

    @abc.abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> List[Segment]:
        """Transcribe an audio file into timestamped segments."""
        raise NotImplementedError

    @abc.abstractmethod
    def to_ipa(self, text: str, language: str) -> str:
        """Convert orthographic text to IPA."""
        raise NotImplementedError


class LocalWhisperProvider(AIProvider):
    """Local provider backed by faster-whisper for STT."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
        language: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ) -> None:
        super().__init__(config=config, config_path=config_path)

        stt_config = self.config.get("stt", {})
        self.model_path = str(stt_config.get("model_path", "")).strip()
        self.language = str(language or stt_config.get("language", "")).strip() or None
        self.device = str(device or stt_config.get("device", "cpu")).strip() or "cpu"
        self.compute_type = (
            str(compute_type or stt_config.get("compute_type", "int8")).strip() or "int8"
        )

        self._whisper_model: Optional[Any] = None
        self._epitran_instances: Dict[str, Any] = {}

    def _load_whisper_model(self) -> Any:
        """Lazy-load faster-whisper model."""
        if self._whisper_model is not None:
            return self._whisper_model

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            print(
                "[ERROR] faster-whisper is not installed. Install it to use LocalWhisperProvider.",
                file=sys.stderr,
            )
            raise RuntimeError("faster-whisper dependency missing") from exc

        model_source = self.model_path
        if not model_source:
            model_source = "base"
            print(
                "[WARN] stt.model_path is empty in ai_config.json; falling back to model 'base'",
                file=sys.stderr,
            )

        try:
            self._whisper_model = WhisperModel(
                model_source,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as exc:
            print(
                "[ERROR] Failed to load faster-whisper model '{0}': {1}".format(
                    model_source, exc
                ),
                file=sys.stderr,
            )
            raise

        return self._whisper_model

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> List[Segment]:
        """Run full-file STT with faster-whisper."""
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError("Audio file not found: {0}".format(path))

        model = self._load_whisper_model()
        selected_language = language or self.language

        segments_out: List[Segment] = []
        segments_iter, info = model.transcribe(
            str(path),
            language=selected_language,
            beam_size=5,
            vad_filter=True,
        )

        total_duration = float(getattr(info, "duration", 0.0) or 0.0)

        for segment in segments_iter:
            start = float(_dict_or_attr(segment, "start", 0.0) or 0.0)
            end = float(_dict_or_attr(segment, "end", start) or start)
            text = str(_dict_or_attr(segment, "text", "") or "").strip()
            avg_logprob = _dict_or_attr(segment, "avg_logprob", None)

            segment_out: Segment = {
                "start": start,
                "end": end,
                "text": text,
                "confidence": _confidence_from_logprob(avg_logprob),
            }
            segments_out.append(segment_out)

            if progress_callback is not None and total_duration > 0.0:
                progress = _coerce_confidence(end / total_duration) * 100.0
                progress_callback(progress, len(segments_out))

        if progress_callback is not None:
            progress_callback(100.0, len(segments_out))

        return segments_out

    def _epitran_transliterate(self, text: str, language: Optional[str]) -> Optional[str]:
        """Try transliteration with Epitran; return None when unavailable."""
        code = _epitran_code_for_language(language)
        if not code:
            return None

        try:
            import epitran
        except ImportError:
            return None

        instance = self._epitran_instances.get(code)
        if instance is None:
            try:
                instance = epitran.Epitran(code)
            except Exception as exc:
                print(
                    "[WARN] Could not initialize Epitran with code '{0}': {1}".format(
                        code, exc
                    ),
                    file=sys.stderr,
                )
                return None
            self._epitran_instances[code] = instance

        try:
            transliterated = str(instance.transliterate(text)).strip()
        except Exception as exc:
            print(
                "[WARN] Epitran transliteration failed: {0}".format(exc),
                file=sys.stderr,
            )
            return None

        if not transliterated:
            return None

        return transliterated

    def to_ipa(self, text: str, language: str) -> str:
        """Convert orthography to IPA using local tooling with Kurdish fallback."""
        value = str(text or "").strip()
        if not value:
            return ""

        transliterated = self._epitran_transliterate(value, language)
        if transliterated:
            return _strip_ipa_wrappers(transliterated)

        if _is_probably_arabic_script(value):
            return southern_kurdish_arabic_to_ipa(value)

        return value


class OpenAIProvider(AIProvider):
    """OpenAI-backed provider for STT and IPA conversion."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__(config=config, config_path=config_path)

        stt_config = self.config.get("stt", {})
        llm_config = self.config.get("llm", {})

        self.stt_model = str(stt_config.get("model", "whisper-1")).strip() or "whisper-1"
        self.language = str(stt_config.get("language", "")).strip() or None
        self.llm_model = str(llm_config.get("model", "gpt-4o")).strip() or "gpt-4o"
        self.api_key_env = (
            str(llm_config.get("api_key_env", "OPENAI_API_KEY")).strip()
            or "OPENAI_API_KEY"
        )

        self._client: Optional[Any] = None

    def _load_client(self) -> Any:
        """Lazy-load OpenAI client."""
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                "OpenAI API key environment variable is missing: {0}".format(
                    self.api_key_env
                )
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            print(
                "[ERROR] openai package is not installed.",
                file=sys.stderr,
            )
            raise RuntimeError("openai dependency missing") from exc

        self._client = OpenAI(api_key=api_key)
        return self._client

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> List[Segment]:
        """Transcribe audio with OpenAI STT endpoint."""
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError("Audio file not found: {0}".format(path))

        client = self._load_client()
        selected_language = language or self.language

        request_kwargs: Dict[str, Any] = {
            "model": self.stt_model,
            "file": None,
            "response_format": "verbose_json",
        }
        if selected_language:
            request_kwargs["language"] = selected_language

        segments_out: List[Segment] = []

        with path.open("rb") as audio_handle:
            request_kwargs["file"] = audio_handle
            try:
                request_kwargs["timestamp_granularities"] = ["segment"]
                response = client.audio.transcriptions.create(**request_kwargs)
            except TypeError:
                request_kwargs.pop("timestamp_granularities", None)
                response = client.audio.transcriptions.create(**request_kwargs)

        raw_segments = _dict_or_attr(response, "segments", None)
        if raw_segments:
            for index, segment in enumerate(raw_segments, start=1):
                start = float(_dict_or_attr(segment, "start", 0.0) or 0.0)
                end = float(_dict_or_attr(segment, "end", start) or start)
                text = str(_dict_or_attr(segment, "text", "") or "").strip()

                avg_logprob = _dict_or_attr(segment, "avg_logprob", None)
                confidence = _confidence_from_logprob(avg_logprob)
                if confidence == 0.0:
                    confidence = _coerce_confidence(
                        float(_dict_or_attr(segment, "confidence", 0.0) or 0.0)
                    )

                segments_out.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text,
                        "confidence": confidence,
                    }
                )

                if progress_callback is not None:
                    progress_callback(100.0, index)
        else:
            text = str(_dict_or_attr(response, "text", "") or "").strip()
            duration = _audio_duration_seconds(path)
            segments_out.append(
                {
                    "start": 0.0,
                    "end": duration,
                    "text": text,
                    "confidence": 0.0,
                }
            )
            if progress_callback is not None:
                progress_callback(100.0, 1)

        return segments_out

    def to_ipa(self, text: str, language: str) -> str:
        """Convert text to IPA using an OpenAI chat model."""
        value = str(text or "").strip()
        if not value:
            return ""

        client = self._load_client()
        prompt = (
            "Convert the following text to IPA. "
            "Return only IPA characters with no explanation.\n"
            "Language code: {0}\n"
            "Text: {1}"
        ).format(language, value)

        response = client.chat.completions.create(
            model=self.llm_model,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a linguistics transcription assistant. "
                        "Output IPA only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        if not response.choices:
            raise RuntimeError("OpenAI returned no choices for IPA conversion")

        message = response.choices[0].message
        content = str(getattr(message, "content", "") or "").strip()
        if not content:
            return value

        return _strip_ipa_wrappers(content)


class XAIProvider(OpenAIProvider):
    """xAI (Grok) provider. Uses OpenAI-compatible API at api.x.ai."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__(config=config, config_path=config_path)

        stt_config = self.config.get("stt", {})
        llm_config = self.config.get("llm", {})

        self.base_url = "https://api.x.ai/v1"

        configured_api_key_env = str(llm_config.get("api_key_env", "")).strip()
        if not configured_api_key_env or configured_api_key_env == "OPENAI_API_KEY":
            configured_api_key_env = "XAI_API_KEY"
        self.api_key_env = configured_api_key_env

        configured_llm_model = str(llm_config.get("model", "")).strip()
        if not configured_llm_model or configured_llm_model == "gpt-4o":
            configured_llm_model = "grok-4-0201"
        self.llm_model = configured_llm_model

        self.stt_model = (
            str(stt_config.get("model", "whisper-large-v3")).strip()
            or "whisper-large-v3"
        )

        self._stt_fallback = LocalWhisperProvider(
            config=self.config,
            config_path=self.config_path,
        )

    def _load_client(self) -> Any:
        """Lazy-load xAI client via OpenAI-compatible SDK."""
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                "xAI API key environment variable is missing: {0}".format(
                    self.api_key_env
                )
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            print(
                "[ERROR] openai package is not installed.",
                file=sys.stderr,
            )
            raise RuntimeError("openai dependency missing") from exc

        self._client = OpenAI(api_key=api_key, base_url=self.base_url)
        return self._client

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> List[Segment]:
        """Use local faster-whisper fallback for STT."""
        return self._stt_fallback.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=progress_callback,
        )


class OllamaProvider(AIProvider):
    """Ollama-backed local LLM provider."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__(config=config, config_path=config_path)

        llm_config = self.config.get("llm", {})
        self.model = str(llm_config.get("model", "llama3.1")).strip() or "llama3.1"
        self.host = str(os.environ.get("OLLAMA_HOST", "http://localhost:11434")).strip()
        self.host = self.host.rstrip("/")

        self._stt_fallback = LocalWhisperProvider(
            config=self.config,
            config_path=self.config_path,
        )

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> List[Segment]:
        """Use local faster-whisper fallback for STT."""
        return self._stt_fallback.transcribe(
            audio_path=audio_path,
            language=language,
            progress_callback=progress_callback,
        )

    def _generate(self, prompt: str) -> str:
        """Call Ollama /api/generate."""
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            "{0}/api/generate".format(self.host),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError("Failed to contact Ollama at {0}: {1}".format(self.host, exc))

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Invalid JSON response from Ollama: {0}".format(exc))

        return str(body.get("response", "") or "").strip()

    def to_ipa(self, text: str, language: str) -> str:
        """Convert text to IPA using an Ollama LLM prompt."""
        value = str(text or "").strip()
        if not value:
            return ""

        prompt = (
            "Convert this text to IPA and output only IPA symbols. "
            "Language code: {0}. Text: {1}"
        ).format(language, value)
        response = self._generate(prompt)

        if not response:
            return value

        return _strip_ipa_wrappers(response)


def _build_provider(provider_name: str, merged_config: Dict[str, Any]) -> AIProvider:
    """Instantiate a provider implementation from a provider name."""
    normalized = str(provider_name or "").strip().lower()

    if normalized in {"faster-whisper", "local-whisper", "whisper", "local"}:
        return LocalWhisperProvider(config=merged_config)
    if normalized == "openai":
        return OpenAIProvider(config=merged_config)
    if normalized in {"xai", "grok", "x.ai"}:
        return XAIProvider(config=merged_config)
    if normalized == "ollama":
        return OllamaProvider(config=merged_config)

    raise ValueError("Unsupported AI provider: {0}".format(normalized))


def _resolve_provider_name(
    merged_config: Dict[str, Any],
    section_priority: List[str],
    default: str = "faster-whisper",
    override_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolve provider name from config sections using priority order.

    When `override_config` is provided, its section providers are checked first.
    An explicit empty provider in an override section suppresses that section from
    fallback resolution in the merged config.
    """
    disabled_sections = set()

    if isinstance(override_config, dict):
        for section_name in section_priority:
            section = override_config.get(section_name, {})
            if not isinstance(section, dict) or "provider" not in section:
                continue

            provider_name = str(section.get("provider", "")).strip().lower()
            if provider_name:
                return provider_name

            disabled_sections.add(section_name)

    for section_name in section_priority:
        if section_name in disabled_sections:
            continue

        section = merged_config.get(section_name, {})
        if not isinstance(section, dict):
            continue

        provider_name = str(section.get("provider", "")).strip().lower()
        if provider_name:
            return provider_name

    return default


def get_stt_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    """Factory for STT providers resolved from `stt.provider`."""
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    provider_name = _resolve_provider_name(merged, ["stt"], override_config=override)
    return _build_provider(provider_name, merged)


def get_ipa_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    """Factory for IPA providers resolved from `ipa.provider` fallback chain."""
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    provider_name = _resolve_provider_name(
        merged,
        ["ipa", "llm", "stt"],
        override_config=override,
    )
    return _build_provider(provider_name, merged)


def get_llm_provider(config: Optional[Dict[str, Any]] = None) -> AIProvider:
    """Factory for LLM providers resolved from `llm.provider` fallback chain."""
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)
    provider_name = _resolve_provider_name(
        merged,
        ["llm", "stt"],
        override_config=override,
    )
    return _build_provider(provider_name, merged)


def get_provider(config: Dict[str, Any]) -> AIProvider:
    """Factory for AI providers.

    Deprecated: use `get_stt_provider`, `get_ipa_provider`, or
    `get_llm_provider` for feature-specific provider resolution.

    By default this resolves against STT provider configuration.
    Pass an explicit top-level `provider` key in `config` to override.
    """
    override = config or {}
    merged = _deep_merge_dicts(load_ai_config(), override)

    provider_name = str(override.get("provider", "")).strip().lower()
    if not provider_name:
        provider_name = _resolve_provider_name(merged, ["stt"])

    return _build_provider(provider_name, merged)


__all__ = [
    "Segment",
    "AIProvider",
    "LocalWhisperProvider",
    "OpenAIProvider",
    "XAIProvider",
    "OllamaProvider",
    "get_stt_provider",
    "get_ipa_provider",
    "get_llm_provider",
    "get_provider",
    "load_ai_config",
    "resolve_ai_config_path",
    "southern_kurdish_arabic_to_ipa",
]
