import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import audio_pipeline_paths as mod


def test_audio_pipeline_paths_only_exports_output_path_helper() -> None:
    assert hasattr(mod, "build_normalized_output_path")
    assert not hasattr(mod, "describe_working_root_issue")
    assert not hasattr(mod, "ensure_safe_working_root")


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
