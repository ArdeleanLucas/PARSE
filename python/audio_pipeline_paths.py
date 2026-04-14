from pathlib import Path


def build_normalized_output_path(source_path: Path, working_dir: Path) -> Path:
    """Return the canonical PCM WAV working-copy path for a source recording."""
    return working_dir / source_path.with_suffix(".wav").name
