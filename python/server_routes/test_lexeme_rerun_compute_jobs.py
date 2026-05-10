from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
import server


def _seed_workspace(root: Path, speaker: str = "Saha01") -> tuple[Path, Path]:
    (root / "annotations").mkdir(parents=True, exist_ok=True)
    (root / "audio" / "working" / speaker).mkdir(parents=True, exist_ok=True)
    audio_path = root / "audio" / "working" / speaker / "working.wav"
    audio_path.write_bytes(b"RIFFWAVEfake")
    with (root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "root", "source_item": "root", "source_survey": "KLQ", "custom_order": ""})
    annotation_path = root / "annotations" / f"{speaker}.parse.json"
    annotation_path.write_text(json.dumps({
        "speaker": speaker,
        "metadata": {"language_code": "ku"},
        "tiers": {"concept": {"intervals": [{"start": 1.0, "end": 2.0, "text": "root", "concept_id": "1"}]}},
    }), encoding="utf-8")
    return annotation_path, audio_path


@pytest.fixture
def lexeme_compute_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    server._install_route_bindings()
    annotation_path, audio_path = _seed_workspace(tmp_path)
    progress: list[tuple[float, dict[str, Any]]] = []
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_normalize_speaker_id", lambda value: str(value or "").strip())
    monkeypatch.setattr(server, "_annotation_read_path_for_speaker", lambda speaker: annotation_path)
    monkeypatch.setattr(server, "_read_json_any_file", lambda path: json.loads(Path(path).read_text(encoding="utf-8")))
    monkeypatch.setattr(server, "_normalize_annotation_record", lambda payload, speaker: payload)
    monkeypatch.setattr(server, "_pipeline_audio_path_for_speaker", lambda speaker: audio_path)
    monkeypatch.setattr(server, "_set_job_progress", lambda job_id, pct, **kwargs: progress.append((float(pct), kwargs)))
    return tmp_path, audio_path, progress


def test_compute_lexeme_rerun_ortho_emits_progress_and_returns_result(monkeypatch: pytest.MonkeyPatch, lexeme_compute_env) -> None:
    _root, audio_path, progress = lexeme_compute_env
    import server_routes.lexeme_rerun as lexeme_rerun

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        lexeme_rerun,
        "_run_ortho_interval_in_subprocess",
        lambda **kwargs: calls.append(kwargs) or "شار",
    )

    result = server._compute_lexeme_rerun_ortho(
        "job-ortho",
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0, "pad": 0.2},
    )

    assert result == {"ortho": "شار", "tier": "ortho", "text": "شار", "interval": {"start": 1.0, "end": 2.0}, "source": "rerun"}
    assert calls == [{"audio_path": audio_path, "start": pytest.approx(0.8), "end": pytest.approx(2.2), "language": "ku"}]
    assert [pct for pct, _payload in progress] == [5.0, 30.0, 95.0]
    assert [payload.get("message") for _pct, payload in progress] == ["Loading record", "Running subprocess", "Finalising"]


def test_compute_lexeme_rerun_ipa_emits_progress_and_returns_result(monkeypatch: pytest.MonkeyPatch, lexeme_compute_env) -> None:
    _root, audio_path, progress = lexeme_compute_env
    import server_routes.lexeme_rerun as lexeme_rerun

    monkeypatch.setattr(lexeme_rerun, "_run_ipa_interval_in_subprocess", lambda **kwargs: "ʃari:")

    result = server._compute_lexeme_rerun_ipa(
        "job-ipa",
        {"speaker": "Saha01", "concept_key": "root", "start": 1.0, "end": 2.0, "pad": 0.0},
    )

    assert result == {"ipa": "ʃari:", "tier": "ipa", "text": "ʃari:", "interval": {"start": 1.0, "end": 2.0}, "source": "rerun"}
    assert [pct for pct, _payload in progress] == [5.0, 30.0, 95.0]
