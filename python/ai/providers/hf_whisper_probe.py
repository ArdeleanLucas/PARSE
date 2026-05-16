from __future__ import annotations

from typing import Any, Dict

_HF_WHISPER_PROBE_SAMPLE_RATE = 16000
_HF_WHISPER_PROBE_SECONDS = 0.1


def _model_path(model: Any) -> str:
    config = getattr(model, "config", None)
    name_or_path = getattr(config, "name_or_path", None)
    if name_or_path:
        return str(name_or_path)
    return str(getattr(model, "name_or_path", "<unknown>"))


def _transformers_version() -> str:
    try:
        import transformers  # type: ignore

        return str(getattr(transformers, "__version__", "<unknown>"))
    except Exception:
        return "<unavailable>"


def _input_dict(inputs: Any) -> Dict[str, Any]:
    if isinstance(inputs, dict):
        return dict(inputs)
    items = getattr(inputs, "items", None)
    if callable(items):
        return dict(items())
    try:
        return dict(inputs)
    except (TypeError, ValueError) as exc:
        raise TypeError("HF Whisper probe processor output must be dict-like") from exc


def _probe_error(model: Any, reason: str) -> RuntimeError:
    return RuntimeError(
        "HF Whisper compatibility probe failed for model={model} transformers={version}: {reason}".format(
            model=_model_path(model),
            version=_transformers_version(),
            reason=reason,
        )
    )


def compatibility_probe(model: Any, processor: Any, *, language: str | None = None) -> None:
    """Verify the active Transformers Whisper stack returns generation scores.

    PARSE confidence provenance depends on ``generated.scores``. The decode
    policy is installed on ``model.generation_config`` before this probe runs;
    the probe deliberately sends only encoder inputs so future Transformers
    changes that stop honoring that config fail loudly at model-load time.
    """
    try:
        import numpy as np

        sample_count = int(round(_HF_WHISPER_PROBE_SAMPLE_RATE * _HF_WHISPER_PROBE_SECONDS))
        silence = np.zeros(sample_count, dtype=np.float32)
        inputs = processor(
            silence,
            sampling_rate=_HF_WHISPER_PROBE_SAMPLE_RATE,
            return_tensors="pt",
            return_attention_mask=True,
        )
        move_inputs = getattr(inputs, "to", None)
        if callable(move_inputs):
            device = getattr(model, "device", None)
            if device is not None:
                inputs = move_inputs(device)
        generated = model.generate(**_input_dict(inputs))
    except Exception as exc:  # pragma: no cover - exact third-party exception varies
        raise _probe_error(model, "exception {0}: {1}".format(type(exc).__name__, exc)) from exc

    if getattr(generated, "sequences", None) is None:
        raise _probe_error(model, "missing generated.sequences")
    scores = getattr(generated, "scores", None)
    if scores is None:
        raise _probe_error(model, "scores is None")
    if len(scores) <= 0:
        shape = getattr(getattr(generated, "sequences", None), "shape", "<unknown>")
        raise _probe_error(model, "scores is empty; sequences_shape={0}".format(shape))
