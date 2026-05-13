"""Tests for _run_normalize_job inplace (src==dst) handling."""
import json
import pathlib
import struct
import subprocess
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


def _stub_ffmpeg_output(dest_path: pathlib.Path, *, bytes_: bytes = b"RIFF0000WAVEfmt \x01\x00\x01\x00\x40\x1f\x00\x00") -> None:
    """Write a small file where ffmpeg would have written its output."""
    dest_path.write_bytes(bytes_)


def _write_silence_wav(dest_path: pathlib.Path, *, duration_sec: float, sample_rate: int = 16000) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(duration_sec * sample_rate)
    with wave.open(str(dest_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        chunk = struct.pack("<16000h", *([0] * 16000))
        full_chunks, remainder = divmod(frame_count, 16000)
        for _ in range(full_chunks):
            w.writeframes(chunk)
        if remainder:
            w.writeframes(struct.pack(f"<{remainder}h", *([0] * remainder)))


def _seed_annotation(project_root: pathlib.Path, speaker: str, *, duration: float) -> pathlib.Path:
    annotation_path = project_root / "annotations" / f"{speaker}.parse.json"
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "t",
                "speaker": speaker,
                "source_audio": f"audio/working/{speaker}/source.wav",
                "source_audio_duration_sec": duration,
                "tiers": {
                    "ipa": {"type": "interval", "display_order": 1, "intervals": []},
                    "ortho": {"type": "interval", "display_order": 2, "intervals": []},
                    "concept": {"type": "interval", "display_order": 3, "intervals": []},
                    "speaker": {"type": "interval", "display_order": 4, "intervals": []},
                },
                "metadata": {"language_code": "sdh", "created": "2026-01-01T00:00:00Z", "modified": "2026-01-01T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    return annotation_path


def _fake_run(results_by_cmd):
    """Build a subprocess.run stub keyed by whether the command ends with
    measure (`-f null -`) or normalize (ends in a WAV path)."""
    calls = []

    def runner(cmd, *args, **kwargs):
        calls.append(cmd)
        # First measure pass — return empty stderr so loudnorm_stats stays None
        if "null" in cmd:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
        # Second pass: write an output file at the last arg and return success
        dest = pathlib.Path(cmd[-1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if results_by_cmd.get("succeed", True):
            _stub_ffmpeg_output(dest)
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            cmd, returncode=1, stdout="",
            stderr="x" * 2000 + "[Errno 21] Is a directory",  # important text in the tail
        )

    return runner, calls


def _seed_workspace_wav(project_root: pathlib.Path, speaker: str, name: str = "source.wav") -> pathlib.Path:
    working_dir = project_root / "audio" / "working" / speaker
    working_dir.mkdir(parents=True, exist_ok=True)
    wav_path = working_dir / name
    # Generate a minimal valid WAV so audio_path.resolve() doesn't complain.
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(struct.pack("<8000h", *[0] * 8000))
    return wav_path


def test_inplace_source_is_not_truncated_mid_ffmpeg(tmp_path, monkeypatch):
    """Regression for the 'source file inside workspace' bug: when the
    resolved source path equals the computed output path, the worker must
    route ffmpeg's output to a sibling temp file and atomically swap — never
    letting ffmpeg read-and-write the same path, which would truncate input
    mid-read."""
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    wav_path = _seed_workspace_wav(tmp_path, "Fail01", "Faili_M_1984.wav")
    original_bytes = wav_path.read_bytes()

    runner, calls = _fake_run({"succeed": True})
    monkeypatch.setattr(server.subprocess, "run", runner)

    job_id = server._create_job("normalize", {"speaker": "Fail01"})
    server._run_normalize_job(job_id, "Fail01", "audio/working/Fail01/Faili_M_1984.wav")

    job = server._jobs[job_id]
    assert job["status"] == "complete", job.get("error")

    # The ffmpeg normalize command should have targeted a *temp* path, not
    # the input path. Find the normalize call (second subprocess.run).
    normalize_cmd = [c for c in calls if isinstance(c, list) and "-af" in c and c[-1].endswith(".wav")][-1]
    dest_arg = normalize_cmd[-1]
    assert dest_arg != str(wav_path), "ffmpeg must not read-and-write the same path"
    assert dest_arg.endswith(".normalized.tmp.wav"), dest_arg

    # After the atomic swap, the canonical output path exists, and no temp
    # file is left behind.
    assert wav_path.exists()
    assert not (tmp_path / "audio/working/Fail01" / "Faili_M_1984.normalized.tmp.wav").exists()
    # The canonical output path carries the *new* (stubbed) bytes.
    assert wav_path.read_bytes() != original_bytes


def test_non_inplace_writes_directly_to_output_path(tmp_path, monkeypatch):
    """When the source is not already at the working-copy path (normal
    onboard flow, source under audio/original/), ffmpeg writes directly."""
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    # Source lives under audio/original/, not audio/working/
    original_dir = tmp_path / "audio" / "original" / "Fail01"
    original_dir.mkdir(parents=True)
    src = original_dir / "raw.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(struct.pack("<8000h", *[0] * 8000))

    runner, calls = _fake_run({"succeed": True})
    monkeypatch.setattr(server.subprocess, "run", runner)

    job_id = server._create_job("normalize", {"speaker": "Fail01"})
    server._run_normalize_job(job_id, "Fail01", "audio/original/Fail01/raw.wav")

    assert server._jobs[job_id]["status"] == "complete"
    normalize_cmd = [c for c in calls if isinstance(c, list) and "-af" in c and c[-1].endswith(".wav")][-1]
    dest_arg = normalize_cmd[-1]
    assert dest_arg.endswith("audio/working/Fail01/raw.wav") or dest_arg.endswith("audio\\working\\Fail01\\raw.wav"), dest_arg
    assert ".normalized.tmp.wav" not in dest_arg  # no temp indirection needed


def test_inplace_ffmpeg_failure_cleans_up_temp_and_reports_exit_code(tmp_path, monkeypatch):
    """If ffmpeg fails during the inplace flow, the temp file must be
    removed so a retry doesn't stumble over it, and the RuntimeError must
    carry the exit code + stderr tail."""
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    wav_path = _seed_workspace_wav(tmp_path, "Fail01", "Faili_M_1984.wav")

    runner, _ = _fake_run({"succeed": False})
    monkeypatch.setattr(server.subprocess, "run", runner)

    job_id = server._create_job("normalize", {"speaker": "Fail01"})
    server._run_normalize_job(job_id, "Fail01", "audio/working/Fail01/Faili_M_1984.wav")

    job = server._jobs[job_id]
    assert job["status"] == "error"
    assert "exit 1" in job["error"]
    assert "Is a directory" in job["error"]
    # Temp file must be removed so retries don't see stale artifacts
    assert not (tmp_path / "audio/working/Fail01" / "Faili_M_1984.normalized.tmp.wav").exists()
    # Original source should remain untouched
    assert wav_path.exists()


def test_normalize_refreshes_source_audio_duration(tmp_path, monkeypatch):
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    annotation_path = _seed_annotation(tmp_path, "Fail01", duration=12000.0)
    _seed_workspace_wav(tmp_path, "Fail01", "source.wav")

    def runner(cmd, *args, **kwargs):
        if "null" in cmd:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
        _write_silence_wav(pathlib.Path(cmd[-1]), duration_sec=60.0)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(server.subprocess, "run", runner)

    job_id = server._create_job("normalize", {"speaker": "Fail01"})
    server._run_normalize_job(job_id, "Fail01", "audio/working/Fail01/source.wav")

    assert server._jobs[job_id]["status"] == "complete"
    refreshed = json.loads(annotation_path.read_text(encoding="utf-8"))
    assert refreshed["source_audio_duration_sec"] == 60.0


def test_refresh_source_audio_duration_noops_when_already_within_one_second(tmp_path, monkeypatch):
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    annotation_path = _seed_annotation(tmp_path, "Fail01", duration=60.4)
    wav_path = tmp_path / "audio" / "working" / "Fail01" / "source.wav"
    _write_silence_wav(wav_path, duration_sec=60.0)
    before = annotation_path.read_text(encoding="utf-8")

    changed = server._refresh_source_audio_duration("Fail01", wav_path)

    assert changed is False
    assert annotation_path.read_text(encoding="utf-8") == before
