import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import normalize_audio as mod


def test_normalize_audio_no_longer_exports_working_root_guard_wrappers() -> None:
    assert not hasattr(mod, "describe_working_root_issue")
    assert not hasattr(mod, "ensure_safe_working_root")


def test_build_jobs_for_speaker_preserves_nested_relative_output_dirs(tmp_path: pathlib.Path) -> None:
    original_root = tmp_path / "audio" / "original"
    working_root = tmp_path / "audio" / "working"
    nested_source_dir = original_root / "Fail01" / "session-a"
    nested_source_dir.mkdir(parents=True)
    source_path = nested_source_dir / "recording.mp3"
    source_path.write_bytes(b"fake")

    jobs = mod.build_jobs_for_speaker("Fail01", original_root, working_root)

    assert len(jobs) == 1
    assert jobs[0]["output"] == (working_root / "Fail01" / "session-a" / "recording.wav").resolve()


def test_normalize_commands_force_pcm_s16le_output() -> None:
    source_path = pathlib.Path("/tmp/source.wav")
    output_path = pathlib.Path("/tmp/output.wav")
    stats = {
        "input_i": "-20.4",
        "input_tp": "-1.1",
        "input_lra": "5.2",
        "input_thresh": "-31.2",
        "target_offset": "0.3",
    }

    pass2 = mod.build_pass2_command("ffmpeg", source_path, output_path, stats)
    single_pass = mod.build_single_pass_command("ffmpeg", source_path, output_path)

    assert pass2[pass2.index("-c:a") + 1] == "pcm_s16le"
    assert single_pass[single_pass.index("-c:a") + 1] == "pcm_s16le"
