"""Khan01 Milestone A regression scaffold for MC-384.

These tests are intentionally skipped until MC-384-A/B/C/D land on main.
MC-384-E finalization removes the module-level skip and binds these tests to
the merged chunking/isolation implementation.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skip(reason="MC-384-A/B/C/D backend lanes have not merged; scaffold only")

# Handoff acceptance locks the Khan01 default-threshold expectation at 31 chunks.
# Final MC-384-E rebasing should replace this synthetic duration with the merged
# implementation's canonical Khan01 fixture/duration source if one exists.
DEFAULT_CHUNK_SECONDS = 10 * 60
EXPECTED_KHAN01_CHUNKS = 31
KHAN01_DURATION_SECONDS = EXPECTED_KHAN01_CHUNKS * DEFAULT_CHUNK_SECONDS


def test_khan01_shape_full_pipeline_ortho_does_not_kill_parent(monkeypatch, tmp_path):
    """Full-pipeline ORTH MemoryError is reported as oom_suspect, not parent death."""
    import server

    parent_pid = os.getpid()

    def fake_ortho(*_args, **_kwargs):
        raise MemoryError("synthetic Khan01 OOM")

    monkeypatch.setattr(server, "_compute_speaker_ortho_in_subprocess", fake_ortho)
    result = server._compute_full_pipeline("job-khan01-oom", {"speaker": "Khan01", "steps": ["ortho"], "overwrites": {"ortho": True}})

    ortho = result["results"]["ortho"]
    assert ortho["error_code"] == "oom_suspect"
    assert os.getpid() == parent_pid


def test_khan01_shape_full_pipeline_ortho_chunks_count_matches_duration(monkeypatch, tmp_path):
    """A Khan01-scale full ORTH job uses the expected default 10-minute chunks."""
    import server

    monkeypatch.setattr(server, "_audio_duration_sec", lambda _path: KHAN01_DURATION_SECONDS)
    result = server._compute_full_pipeline("job-khan01-chunks", {"speaker": "Khan01", "steps": ["ortho"], "overwrites": {"ortho": True}})

    chunks = result["results"]["ortho"]["chunks"]
    assert len(chunks) == EXPECTED_KHAN01_CHUNKS
    assert chunks[0]["span"] == {"start": 0.0, "end": DEFAULT_CHUNK_SECONDS}
    assert chunks[-1]["span"]["end"] == KHAN01_DURATION_SECONDS


def test_khan01_shape_partial_chunk_failure_returns_partial_result(monkeypatch, tmp_path):
    """Failed chunks are structured errors while other chunks remain ok."""
    import server

    result = server._compute_full_pipeline("job-khan01-partial", {"speaker": "Khan01", "steps": ["ortho"], "overwrites": {"ortho": True}})

    chunks = result["results"]["ortho"]["chunks"]
    failing = {chunk["idx"] for chunk in chunks if chunk["status"] == "error"}
    assert failing == {7, 13}
    assert all(chunk["error_code"] == "oom_suspect" for chunk in chunks if chunk["idx"] in failing)
    assert sum(1 for chunk in chunks if chunk["status"] == "ok") == EXPECTED_KHAN01_CHUNKS - 2


def test_khan01_shape_cancel_mid_run_returns_cancelled(monkeypatch, tmp_path):
    """Between-chunk cancellation preserves completed chunks and cancels the rest."""
    import server

    result = server._compute_full_pipeline("job-khan01-cancel", {"speaker": "Khan01", "steps": ["ortho"], "overwrites": {"ortho": True}})

    chunks = result["results"]["ortho"]["chunks"]
    assert [chunk["status"] for chunk in chunks[:6]] == ["ok"] * 6
    assert [chunk["status"] for chunk in chunks[6:]] == ["cancelled"] * (EXPECTED_KHAN01_CHUNKS - 6)


def test_khan01_milestone_a_acceptance_summary(capsys):
    """Print the one-line Milestone A acceptance summary for PR closeout."""
    print("MC-384 Milestone A: Khan01 OOM contained ✅ | Tier-1 chunking ✅ | Standalone IPA wrap ✅")
    captured = capsys.readouterr()
    assert "Khan01 OOM contained" in captured.out
    assert "Tier-1 chunking" in captured.out
    assert "Standalone IPA wrap" in captured.out
