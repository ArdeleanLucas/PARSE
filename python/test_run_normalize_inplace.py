"""Tests for _run_normalize_job inplace (src==dst) handling."""
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
