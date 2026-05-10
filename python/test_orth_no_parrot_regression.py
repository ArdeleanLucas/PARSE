from __future__ import annotations

import csv
import json
import types
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from ai.providers.hf_whisper import HFWhisperProvider
from app.http.lexeme_rerun_handlers import build_post_run_ipa_response, build_post_run_ortho_response
import server

DISTINCTIVE_MARKER_PROMPT = "<DISTINCTIVE-MARKER-PROMPT>"
CLEAN_TRANSCRIPT = "clean lexical decode"


class _FakeInputs(dict):
    def __init__(self) -> None:
        super().__init__({"input_features": "synthetic-features"})

    def to(self, _device: str) -> "_FakeInputs":
        return self


class _FakePromptIds:
    def __init__(self, text: str) -> None:
        self.text = text

    def to(self, _device: str) -> "_FakePromptIds":
        return self


class _PromptSensitiveProcessor:
    def __init__(self) -> None:
        self.prompt_ids_calls: list[str] = []

    def __call__(self, _audio: Any, **_kwargs: Any) -> _FakeInputs:
        return _FakeInputs()

    def get_prompt_ids(self, text: str, *, return_tensors: str) -> _FakePromptIds:
        assert return_tensors == "pt"
        self.prompt_ids_calls.append(text)
        return _FakePromptIds(text)

    def batch_decode(self, sequences: Any, **_kwargs: Any) -> list[str]:
        token_id = int(np.asarray(sequences)[0][-1])
        if token_id == 1:
            return [f"{DISTINCTIVE_MARKER_PROMPT} parroted output"]
        return [CLEAN_TRANSCRIPT]


class _PromptSensitiveModel:
    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> Any:
        self.generate_calls.append(kwargs)
        prompt_was_seeded = "prompt_ids" in kwargs
        token_id = 1 if prompt_was_seeded else 2
        return types.SimpleNamespace(
            sequences=np.asarray([[0, token_id]], dtype=np.int64),
            scores=(np.asarray([[0.0, 1.0, 1.0]], dtype=np.float32),),
        )


def _provider_with_distinctive_prompt() -> HFWhisperProvider:
    provider = HFWhisperProvider(
        config={
            "ortho": {
                "backend": "hf",
                "model_path": "razhan/whisper-base-sdh",
                "language": "sd",
                "device": "cpu",
                "initial_prompt": DISTINCTIVE_MARKER_PROMPT,
                "condition_on_previous_text": False,
                "compression_ratio_threshold": 1.8,
                "no_repeat_ngram_size": 3,
                "repetition_penalty": 1.2,
            }
        }
    )
    processor = _PromptSensitiveProcessor()
    model = _PromptSensitiveModel()
    provider._load_model = lambda: (processor, model)  # type: ignore[method-assign]
    return provider


def _synthetic_audio(sample_rate: int = 16000) -> np.ndarray:
    """Small CPU-only fixture: silence plus a brief deterministic tone."""
    duration_sec = 3.0
    samples = int(sample_rate * duration_sec)
    audio = np.zeros(samples, dtype=np.float32)
    tone_start = int(sample_rate * 0.75)
    tone_end = int(sample_rate * 0.95)
    t = np.arange(tone_end - tone_start, dtype=np.float32) / float(sample_rate)
    audio[tone_start:tone_end] = 0.15 * np.sin(2.0 * np.pi * 440.0 * t)
    return audio


def _write_workspace(root: Path, *, speaker: str = "Saha01") -> tuple[Path, Path]:
    (root / "annotations").mkdir(parents=True, exist_ok=True)
    audio_path = root / "audio" / "working" / speaker / "synthetic.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"synthetic audio is supplied in-memory by the runner")

    with (root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"])
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "concept_en": "distinctive root",
                "source_item": "distinctive-root",
                "source_survey": "TEST",
                "custom_order": "1",
            }
        )

    annotation_path = root / "annotations" / f"{speaker}.parse.json"
    annotation_path.write_text(
        json.dumps(
            {
                "project_id": "parse-test",
                "speaker": speaker,
                "source_audio": f"audio/working/{speaker}/synthetic.wav",
                "source_audio_duration_sec": 3.0,
                "tiers": {
                    "concept": {
                        "type": "interval",
                        "display_order": 3,
                        "intervals": [
                            {"start": 0.6, "end": 1.1, "text": "distinctive root", "concept_id": "1"}
                        ],
                    },
                    "ortho": {"type": "interval", "display_order": 2, "intervals": []},
                    "ipa": {"type": "interval", "display_order": 1, "intervals": []},
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return annotation_path, audio_path


def _normalize_speaker(value: Any) -> str:
    speaker = str(value or "").strip()
    if not speaker:
        raise ValueError("speaker is required")
    return speaker


def _read_json_any(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_record(payload: Any, speaker: str) -> dict[str, Any]:
    assert isinstance(payload, dict)
    normalized = dict(payload)
    normalized.setdefault("speaker", speaker)
    return normalized


def _hf_interval_runner(provider: HFWhisperProvider) -> Callable[..., str]:
    def run_interval(**kwargs: Any) -> str:
        start = float(kwargs["start"])
        end = float(kwargs["end"])
        segments = provider.transcribe_segments_in_memory(
            _synthetic_audio(),
            [(start, end)],
            sample_rate=16000,
            language=kwargs.get("language"),
        )
        return " ".join(str(segment.get("text", "")) for segment in segments).strip()

    return run_interval


@pytest.mark.parametrize("pad", [0.0, 0.2, 0.5])
@pytest.mark.parametrize("endpoint,tier_key", [("ortho", "ortho"), ("ipa", "ipa")])
def test_lexeme_rerun_outputs_never_include_configured_initial_prompt(
    tmp_path: Path,
    endpoint: str,
    tier_key: str,
    pad: float,
) -> None:
    """Regression for docs/orth-initial-prompt-suppression.md.

    The 2026-05-07 corpus audit found 100% prompt parrots in Fail01 (523/523),
    Fail02 (132/132), and Khan01 (287/287). This route-level test keeps a
    distinctive marker prompt out of saved ORTH/IPA rerun payloads for every
    allowed pad value.
    """
    provider = _provider_with_distinctive_prompt()
    _annotation_path, audio_path = _write_workspace(tmp_path)
    body = {"speaker": "Saha01", "concept_key": "distinctive-root", "start": 0.6, "end": 1.1, "pad": pad, "async": False}
    common_kwargs = {
        "body": body,
        "project_root": tmp_path,
        "normalize_speaker_id": _normalize_speaker,
        "annotation_read_path_for_speaker": lambda speaker: tmp_path / "annotations" / f"{speaker}.parse.json",
        "read_json_any_file": _read_json_any,
        "normalize_annotation_record": _normalize_record,
        "resolve_audio_path_for_speaker": lambda _speaker: audio_path,
        "locks_dir": tmp_path / ".parse-locks",
        "acquire_speaker_lock": lambda speaker, locks_dir: locks_dir / f"{speaker}.lock",
        "release_speaker_lock": lambda _speaker, _locks_dir: None,
    }

    if endpoint == "ortho":
        response = build_post_run_ortho_response(
            run_ortho_interval=_hf_interval_runner(provider),
            **common_kwargs,
        )
    else:
        response = build_post_run_ipa_response(
            run_ipa_interval=_hf_interval_runner(provider),
            **common_kwargs,
        )

    assert response.status == HTTPStatus.OK
    text = str(response.payload[tier_key])
    assert DISTINCTIVE_MARKER_PROMPT not in text
    assert text == CLEAN_TRANSCRIPT
    assert response.payload["interval"] == {"start": 0.6, "end": 1.1}


@pytest.mark.parametrize("pad", [0.0, 0.2, 0.5])
def test_concept_window_outputs_never_include_configured_initial_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pad: float,
) -> None:
    """Bulk concept-window ORTH must suppress configured Whisper prompts too."""
    import ai.forced_align as forced_align

    provider = _provider_with_distinctive_prompt()
    _write_workspace(tmp_path)
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        server,
        "_pipeline_audio_path_for_speaker",
        lambda speaker: tmp_path / "audio" / "working" / speaker / "synthetic.wav",
    )
    monkeypatch.setattr(forced_align, "_load_audio_mono_16k", lambda _path: _synthetic_audio())

    result = server._compute_speaker_ortho(
        "job-concept-window",
        {"speaker": "Saha01", "run_mode": "concept-windows", "pad": pad},
        provider=provider,
    )

    assert result["pad"] == pad
    annotation = json.loads((tmp_path / "annotations" / "Saha01.parse.json").read_text(encoding="utf-8"))
    rows = annotation["tiers"]["ortho"]["intervals"]
    assert rows
    assert all(DISTINCTIVE_MARKER_PROMPT not in str(row.get("text") or "") for row in rows)
    assert [row["text"] for row in rows] == [CLEAN_TRANSCRIPT]
