from __future__ import annotations

from pathlib import Path

import numpy as np

from ai.providers.hf_whisper import HFWhisperProvider
from server_routes.annotate import _run_step_on_concept_windows
from test_hf_whisper_provider import (
    _RecordingModel,
    _RecordingProcessor,
    _config,
    _generated_result,
    _install_transformers_stub,
)


def test_annotate_concept_windows_hf_initial_prompt_none_reaches_generate(monkeypatch, tmp_path: Path) -> None:
    import ai.forced_align as forced_align

    processor, model = _install_transformers_stub(
        monkeypatch,
        processor=_RecordingProcessor(texts=["window-one"]),
        model=_RecordingModel(generated=[_generated_result(selected_token=1, score_row=[0.0, 1.0])]),
    )
    provider = HFWhisperProvider(config=_config(initial_prompt="CONFIG-PROMPT-MARKER"))
    monkeypatch.setattr(forced_align, "_load_audio_mono_16k", lambda _path: np.zeros(16000 * 3, dtype=np.float32))

    rows = _run_step_on_concept_windows(
        tmp_path / "fake.wav",
        [{"start": 1.0, "end": 1.5, "text": "root", "concept_id": "1"}],
        provider,
        "ortho",
        None,
        language="ku",
    )

    assert [row["text"] for row in rows] == ["window-one"]
    assert processor.prompt_ids_calls == []
    assert "prompt_ids" not in model.generate_calls[0]
