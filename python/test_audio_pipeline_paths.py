import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import audio_pipeline_paths as mod


def _make_dir_symlink_or_skip(link_path: pathlib.Path, target_path: pathlib.Path) -> None:
    try:
        link_path.symlink_to(target_path, target_is_directory=True)
    except (NotImplementedError, OSError, PermissionError) as exc:
        pytest.skip(f"directory symlink creation unavailable in this test environment: {exc}")


def test_describe_working_root_issue_detects_symlink(tmp_path: pathlib.Path) -> None:
    original_root = tmp_path / "audio" / "original"
    original_root.mkdir(parents=True)
    symlink_target = tmp_path / "raw-originals"
    symlink_target.mkdir()

    working_root = tmp_path / "audio" / "working"
    _make_dir_symlink_or_skip(working_root, symlink_target)

    issue = mod.describe_working_root_issue(working_root, original_root)

    assert "symlink" in issue
    assert str(symlink_target) in issue


def test_ensure_safe_working_root_rejects_symlink(tmp_path: pathlib.Path) -> None:
    original_root = tmp_path / "audio" / "original"
    original_root.mkdir(parents=True)
    symlink_target = tmp_path / "raw-originals"
    symlink_target.mkdir()

    working_root = tmp_path / "audio" / "working"
    _make_dir_symlink_or_skip(working_root, symlink_target)

    with pytest.raises(ValueError, match="Unsafe audio pipeline configuration"):
        mod.ensure_safe_working_root(working_root, original_root)


def test_ensure_safe_working_root_rejects_same_resolved_directory(tmp_path: pathlib.Path) -> None:
    original_root = tmp_path / "audio" / "original"
    original_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="same directory as audio/original"):
        mod.ensure_safe_working_root(original_root, original_root)


def test_ensure_safe_working_root_rejects_nested_directory(tmp_path: pathlib.Path) -> None:
    original_root = tmp_path / "audio" / "original"
    nested_working_root = original_root / "working"
    nested_working_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="resolves inside audio/original"):
        mod.ensure_safe_working_root(nested_working_root, original_root)


def test_build_normalized_output_path_forces_wav_extension(tmp_path: pathlib.Path) -> None:
    working_dir = tmp_path / "audio" / "working" / "Fail01"
    source_path = tmp_path / "audio" / "original" / "Fail01" / "recording.flac"

    output_path = mod.build_normalized_output_path(source_path, working_dir)

    assert output_path == working_dir / "recording.wav"


def test_build_normalized_output_path_preserves_nested_relative_directories(tmp_path: pathlib.Path) -> None:
    working_dir = tmp_path / "audio" / "working" / "Fail01" / "session-a"
    source_path = tmp_path / "audio" / "original" / "Fail01" / "session-a" / "recording.mp3"

    output_path = mod.build_normalized_output_path(source_path, working_dir)

    assert output_path == working_dir / "recording.wav"
