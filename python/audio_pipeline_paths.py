from pathlib import Path


WORKING_ROOT_ERROR_PREFIX = (
    "Unsafe audio pipeline configuration: {0}. Refusing to normalize because "
    "outputs must stay isolated from read-only originals."
)


def describe_working_root_issue(working_root: Path, original_root: Path) -> str:
    try:
        if working_root.is_symlink():
            return (
                "audio/working is a symlink: "
                f"{working_root} -> {working_root.resolve()}"
            )
    except (OSError, RuntimeError):
        return "audio/working could not be inspected safely"

    try:
        working_resolved = working_root.resolve()
        original_resolved = original_root.resolve()
    except (OSError, RuntimeError) as exc:
        return "audio/working could not be resolved safely: {0}".format(exc)

    if working_resolved == original_resolved:
        return (
            "audio/working resolves to the same directory as audio/original: "
            f"{working_resolved}"
        )

    try:
        working_resolved.relative_to(original_resolved)
        return (
            "audio/working resolves inside audio/original: "
            f"{working_resolved}"
        )
    except ValueError:
        return ""


def ensure_safe_working_root(working_root: Path, original_root: Path) -> None:
    issue = describe_working_root_issue(working_root, original_root)
    if issue:
        raise ValueError(WORKING_ROOT_ERROR_PREFIX.format(issue))


def build_normalized_output_path(source_path: Path, working_dir: Path) -> Path:
    """Return the canonical PCM WAV working-copy path for a source recording."""
    return working_dir / source_path.with_suffix(".wav").name
