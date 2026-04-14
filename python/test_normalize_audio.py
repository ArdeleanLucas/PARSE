import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import normalize_audio as mod


def test_describe_working_root_issue_detects_symlink(tmp_path: pathlib.Path) -> None:
    original_root = tmp_path / "audio" / "original"
    original_root.mkdir(parents=True)
    symlink_target = tmp_path / "raw-originals"
    symlink_target.mkdir()

    working_root = tmp_path / "audio" / "working"
    working_root.symlink_to(symlink_target, target_is_directory=True)

    issue = mod.describe_working_root_issue(working_root, original_root)

    assert "symlink" in issue
    assert str(symlink_target) in issue


def test_ensure_safe_working_root_allows_real_sibling_dirs(tmp_path: pathlib.Path) -> None:
    original_root = tmp_path / "audio" / "original"
    working_root = tmp_path / "audio" / "working"
    original_root.mkdir(parents=True)
    working_root.mkdir(parents=True)

    mod.ensure_safe_working_root(working_root, original_root)


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
