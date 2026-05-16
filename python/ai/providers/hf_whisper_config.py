from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

_LEGACY_SCHEMA_COMMAND = "python python/tools/migrate_ai_config_ortho.py --workspace <path> --apply"
_LEGACY_SCHEMA_MESSAGE = (
    "Detected legacy flat ortho schema. Run `"
    + _LEGACY_SCHEMA_COMMAND
    + "` first."
)

_CT2_REQUIRED_FILES = frozenset({"model.bin", "config.json", "tokenizer.json"})
_TOP_LEVEL_KEYS = frozenset({"backend", "model", "generation", "decoding"})
_MODEL_KEYS = frozenset({"repo_id", "device"})
_GENERATION_KEYS = frozenset(
    {
        "task",
        "language",
        "return_dict_in_generate",
        "output_scores",
        "compression_ratio_threshold",
        "no_repeat_ngram_size",
        "repetition_penalty",
        "condition_on_prev_tokens",
        "temperature",
        "do_sample",
    }
)
_DECODING_KEYS = frozenset({"initial_prompt", "refine_lexemes"})
_LEGACY_FLAT_KEYS = frozenset(
    {
        "model_path",
        "language",
        "device",
        "compute_type",
        "vad_filter",
        "vad_parameters",
        "condition_on_previous_text",
        "compression_ratio_threshold",
        "no_repeat_ngram_size",
        "repetition_penalty",
        "initial_prompt",
        "refine_lexemes",
        "provider",
        "task",
    }
)


def legacy_schema_migration_command() -> str:
    return _LEGACY_SCHEMA_COMMAND


def legacy_schema_error_message() -> str:
    return _LEGACY_SCHEMA_MESSAGE


def is_legacy_ortho_schema_error(exc: BaseException) -> bool:
    return "Detected legacy flat ortho schema" in str(exc)


def _looks_like_ct2_whisper_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    children = {child.name for child in path.iterdir()}
    if not _CT2_REQUIRED_FILES.issubset(children):
        return False
    has_hf_weights = any(
        child.name == "pytorch_model.bin"
        or child.name == "model.safetensors"
        or child.name.startswith("pytorch_model-")
        or child.name.endswith(".safetensors")
        for child in path.iterdir()
    )
    return not has_hf_weights


def _ct2_model_path_error(repo_id: str) -> str:
    return (
        "[ORTH config error] ortho.model.repo_id expected HuggingFace repo id like "
        "`razhan/whisper-base-sdh` or a local HF-format directory; got CT2 "
        "directory `{0}` — either change ortho.model.repo_id to the HF id, or "
        "revert ortho.backend='faster-whisper'"
    ).format(repo_id)


def _unknown(scope: str, keys: set[str]) -> None:
    if keys:
        dotted = ", ".join(sorted(f"{scope}.{key}" if scope else key for key in keys))
        raise ValueError(f"Unknown ORTH HF config key(s): {dotted}")


def _as_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"ORTH HF config field `{field_name}` must be an object")
    return dict(value)


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Expected boolean ORTH HF config value, got {value!r}")


def _coerce_float(value: Any, default: float, *, minimum: float | None = None) -> float:
    if value is None:
        result = float(default)
    else:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Expected numeric ORTH HF config value, got {value!r}") from exc
    if minimum is not None and result < minimum:
        raise ValueError(f"ORTH HF numeric config value must be >= {minimum}, got {result}")
    return result


def _coerce_int(value: Any, default: int, *, minimum: int | None = None) -> int:
    if value is None:
        result = int(default)
    else:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Expected integer ORTH HF config value, got {value!r}") from exc
    if minimum is not None and result < minimum:
        raise ValueError(f"ORTH HF integer config value must be >= {minimum}, got {result}")
    return result


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class OrthoHFGenerationConfig:
    task: Literal["transcribe", "translate"] = "transcribe"
    language: str | None = "fa"
    return_dict_in_generate: bool = True
    output_scores: bool = True
    compression_ratio_threshold: float = 1.8
    no_repeat_ngram_size: int = 3
    repetition_penalty: float = 1.2
    condition_on_prev_tokens: bool = False
    temperature: float = 0.0
    do_sample: bool = False


@dataclass(frozen=True)
class OrthoHFModelConfig:
    repo_id: str = "razhan/whisper-base-sdh"
    device: str = "auto"


@dataclass(frozen=True)
class OrthoHFDecodingConfig:
    initial_prompt: str | None = None
    refine_lexemes: bool = False


@dataclass(frozen=True)
class OrthoHFConfig:
    backend: Literal["hf"] = "hf"
    model: OrthoHFModelConfig = field(default_factory=OrthoHFModelConfig)
    generation: OrthoHFGenerationConfig = field(default_factory=OrthoHFGenerationConfig)
    decoding: OrthoHFDecodingConfig = field(default_factory=OrthoHFDecodingConfig)

    @classmethod
    def from_dict(cls, raw: Any) -> "OrthoHFConfig":
        section = _as_mapping(raw, field_name="ortho")
        section_keys = set(section)
        has_sectioned = any(key in section for key in _TOP_LEVEL_KEYS - {"backend"})
        has_legacy = bool(section_keys.intersection(_LEGACY_FLAT_KEYS))
        if has_legacy and not has_sectioned:
            raise ValueError(_LEGACY_SCHEMA_MESSAGE)
        # Built-in defaults intentionally carry sectioned HF config plus flat
        # faster-whisper compatibility siblings. In that mixed shape, consume
        # only the sectioned keys and ignore legacy siblings here.
        unknown_top_keys = section_keys - _TOP_LEVEL_KEYS
        if has_sectioned:
            unknown_top_keys -= _LEGACY_FLAT_KEYS
        _unknown("ortho", unknown_top_keys)

        backend = str(section.get("backend", "hf") or "hf").strip().lower()
        if backend != "hf":
            raise ValueError(f"ORTH HF config backend must be 'hf', got {backend!r}")

        model_raw = _as_mapping(section.get("model"), field_name="ortho.model")
        generation_raw = _as_mapping(section.get("generation"), field_name="ortho.generation")
        decoding_raw = _as_mapping(section.get("decoding"), field_name="ortho.decoding")
        _unknown("ortho.model", set(model_raw) - _MODEL_KEYS)
        _unknown("ortho.generation", set(generation_raw) - _GENERATION_KEYS)
        _unknown("ortho.decoding", set(decoding_raw) - _DECODING_KEYS)

        repo_id = str(model_raw.get("repo_id", "razhan/whisper-base-sdh") or "").strip()
        if not repo_id:
            raise ValueError(
                "[ORTH config error] ortho.model.repo_id expected HuggingFace repo id "
                "like `razhan/whisper-base-sdh` or a local HF-format directory; got empty value"
            )
        candidate = Path(repo_id).expanduser()
        try:
            if candidate.exists() and _looks_like_ct2_whisper_directory(candidate.resolve()):
                raise ValueError(_ct2_model_path_error(str(candidate.resolve())))
        except OSError:
            pass

        task = str(generation_raw.get("task", "transcribe") or "transcribe").strip().lower()
        if task not in {"transcribe", "translate"}:
            raise ValueError("ORTH HF generation.task must be 'transcribe' or 'translate'")
        temperature = _coerce_float(generation_raw.get("temperature"), 0.0, minimum=0.0)
        do_sample = _coerce_bool(generation_raw.get("do_sample"), default=False)
        if temperature != 0.0 and not do_sample:
            raise ValueError("ORTH HF generation.temperature may be non-zero only when generation.do_sample=true")

        return cls(
            backend="hf",
            model=OrthoHFModelConfig(
                repo_id=repo_id,
                device=str(model_raw.get("device", "auto") or "auto").strip() or "auto",
            ),
            generation=OrthoHFGenerationConfig(
                task=task,  # type: ignore[arg-type]
                language=_optional_str(generation_raw.get("language", "fa")),
                return_dict_in_generate=_coerce_bool(
                    generation_raw.get("return_dict_in_generate"), default=True
                ),
                output_scores=_coerce_bool(generation_raw.get("output_scores"), default=True),
                compression_ratio_threshold=_coerce_float(
                    generation_raw.get("compression_ratio_threshold"), 1.8, minimum=0.0
                ),
                no_repeat_ngram_size=_coerce_int(
                    generation_raw.get("no_repeat_ngram_size"), 3, minimum=0
                ),
                repetition_penalty=_coerce_float(
                    generation_raw.get("repetition_penalty"), 1.2, minimum=1.0
                ),
                condition_on_prev_tokens=_coerce_bool(
                    generation_raw.get("condition_on_prev_tokens"), default=False
                ),
                temperature=temperature,
                do_sample=do_sample,
            ),
            decoding=OrthoHFDecodingConfig(
                initial_prompt=_optional_str(decoding_raw.get("initial_prompt")),
                refine_lexemes=_coerce_bool(decoding_raw.get("refine_lexemes"), default=False),
            ),
        )


__all__ = [
    "OrthoHFConfig",
    "OrthoHFDecodingConfig",
    "OrthoHFGenerationConfig",
    "OrthoHFModelConfig",
    "is_legacy_ortho_schema_error",
    "legacy_schema_error_message",
    "legacy_schema_migration_command",
]
