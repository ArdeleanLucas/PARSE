"""Unit tests for _compute_speaker_ipa (ipa_only compute type)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _StubIpaProvider:
    """Returns an uppercase ASCII mirror so tests can check exact output."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def to_ipa(self, text: str, language: str) -> str:
        self.calls.append((text, language))
        return "IPA:" + text.upper()


def _seed_annotation(tmp_path: pathlib.Path, speaker: str, ortho: list[dict], ipa: list[dict]):
    (tmp_path / "annotations").mkdir(exist_ok=True)
    annotation = {
        "version": 1,
        "project_id": "t",
        "speaker": speaker,
        "source_audio": "x.wav",
        "source_audio_duration_sec": 10.0,
        "tiers": {
            "ipa":     {"type": "interval", "display_order": 1, "intervals": ipa},
            "ortho":   {"type": "interval", "display_order": 2, "intervals": ortho},
            "concept": {"type": "interval", "display_order": 3, "intervals": []},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
        "metadata": {"language_code": "sdh", "created": "2026-01-01T00:00:00Z", "modified": "2026-01-01T00:00:00Z"},
    }
    (tmp_path / "annotations" / f"{speaker}.parse.json").write_text(
        json.dumps(annotation), encoding="utf-8",
    )
    return annotation


def _load_canonical(tmp_path: pathlib.Path, speaker: str) -> dict:
    return json.loads((tmp_path / "annotations" / f"{speaker}.parse.json").read_text("utf-8"))


def test_fills_empty_ipa_slots_from_ortho(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    stub = _StubIpaProvider()
    monkeypatch.setattr(server, "get_ipa_provider", lambda: stub)

    ortho = [
        {"start": 1.0, "end": 1.5, "text": "hair"},
        {"start": 2.0, "end": 2.5, "text": "forehead"},
        {"start": 3.0, "end": 3.5, "text": ""},   # empty ortho — skipped
    ]
    ipa = [{"start": 1.0, "end": 1.5, "text": ""}]  # only one empty ipa, second one absent
    _seed_annotation(tmp_path, "Fail02", ortho, ipa)

    result = server._compute_speaker_ipa("j1", {"speaker": "Fail02"})
    assert result["filled"] == 2
    assert result["skipped"] == 1
    assert result["total"] == 3

    ann = _load_canonical(tmp_path, "Fail02")
    ipa_intervals = ann["tiers"]["ipa"]["intervals"]
    ipa_by_start = {round(i["start"], 3): i["text"] for i in ipa_intervals}
    assert ipa_by_start[1.0] == "IPA:HAIR"
    assert ipa_by_start[2.0] == "IPA:FOREHEAD"
    assert stub.calls == [("hair", "sdh"), ("forehead", "sdh")]


def test_preserves_existing_ipa_unless_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    stub = _StubIpaProvider()
    monkeypatch.setattr(server, "get_ipa_provider", lambda: stub)

    ortho = [{"start": 1.0, "end": 1.5, "text": "hair"}]
    ipa = [{"start": 1.0, "end": 1.5, "text": "manual-keep"}]
    _seed_annotation(tmp_path, "Fail02", ortho, ipa)

    result = server._compute_speaker_ipa("j1", {"speaker": "Fail02"})
    assert result["filled"] == 0
    assert result["skipped"] == 1
    ann = _load_canonical(tmp_path, "Fail02")
    assert ann["tiers"]["ipa"]["intervals"][0]["text"] == "manual-keep"
    assert stub.calls == []


def test_overwrite_true_replaces_existing_ipa(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    stub = _StubIpaProvider()
    monkeypatch.setattr(server, "get_ipa_provider", lambda: stub)

    ortho = [{"start": 1.0, "end": 1.5, "text": "hair"}]
    ipa = [{"start": 1.0, "end": 1.5, "text": "manual-keep"}]
    _seed_annotation(tmp_path, "Fail02", ortho, ipa)

    result = server._compute_speaker_ipa("j1", {"speaker": "Fail02", "overwrite": True})
    assert result["filled"] == 1
    ann = _load_canonical(tmp_path, "Fail02")
    assert ann["tiers"]["ipa"]["intervals"][0]["text"] == "IPA:HAIR"


def test_run_compute_job_dispatches_ipa_only(tmp_path, monkeypatch):
    """_run_compute_job should route compute_type='ipa_only' to _compute_speaker_ipa."""
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "get_ipa_provider", lambda: _StubIpaProvider())
    _seed_annotation(
        tmp_path, "Fail02",
        [{"start": 1.0, "end": 1.5, "text": "hair"}], [],
    )

    captured: dict = {}

    def fake_complete(job_id, result, **kwargs):
        captured["result"] = result

    def fake_error(job_id, err):
        captured["error"] = err

    monkeypatch.setattr(server, "_set_job_progress", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_set_job_complete", fake_complete)
    monkeypatch.setattr(server, "_set_job_error", fake_error)

    server._run_compute_job("j1", "ipa_only", {"speaker": "Fail02"})
    assert "error" not in captured
    assert captured["result"]["filled"] == 1

    # Also try the hyphenated alias
    captured.clear()
    # Re-seed (previous call wrote to the same file)
    _seed_annotation(
        tmp_path, "Fail03",
        [{"start": 2.0, "end": 2.5, "text": "ash"}], [],
    )
    server._run_compute_job("j2", "ipa-only", {"speaker": "Fail03"})
    assert captured["result"]["filled"] == 1


def test_missing_annotation_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    import pytest

    with pytest.raises(RuntimeError, match="No annotation"):
        server._compute_speaker_ipa("j1", {"speaker": "GhostSpeaker"})


def test_skips_when_provider_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)

    class _EmptyProvider:
        def to_ipa(self, text, lang):
            return ""

    monkeypatch.setattr(server, "get_ipa_provider", lambda: _EmptyProvider())
    _seed_annotation(
        tmp_path, "Fail02",
        [{"start": 1.0, "end": 1.5, "text": "hair"}], [],
    )
    result = server._compute_speaker_ipa("j1", {"speaker": "Fail02"})
    assert result["filled"] == 0
    assert result["skipped"] == 1
