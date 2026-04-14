#!/usr/bin/env python3
"""
normalize_audio.py - Two-pass ffmpeg loudnorm normalization for PARSE.

This script reads source audio from audio/original/ and writes normalized
working copies to audio/working/. It is the first step in the PARSE data
pipeline; downstream tools should read from audio/working/ only.

Examples:
    python normalize_audio.py --input audio/original/Fail01/recording.wav --output audio/working/Fail01/recording.wav
    python normalize_audio.py --speaker Fail01 --base-dir /path/to/project/
    python normalize_audio.py --all --base-dir /path/to/project/
    python normalize_audio.py --all --base-dir /path/to/project/ --force
    python normalize_audio.py --all --base-dir . --ffmpeg "C:/ProgramData/chocolatey/bin/ffmpeg.exe"
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from audio_pipeline_paths import build_normalized_output_path


TARGET_I = "-16"
TARGET_I_FLOAT = -16.0
TARGET_TP = "-1.5"
TARGET_LRA = "11"
TARGET_SR = "44100"
TARGET_CHANNELS = "1"
TARGET_SAMPLE_FMT = "s16"

SUPPORTED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
}

CHOCO_FFMPEG = Path("C:/ProgramData/chocolatey/bin/ffmpeg.exe")


def print_error(message: str) -> None:
    print(message, file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize audio to 16-bit PCM WAV, mono, 44.1kHz, -16 LUFS using "
            "a two-pass ffmpeg loudnorm pipeline."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--input",
        metavar="FILE",
        help="Single source audio file under audio/original/",
    )
    mode.add_argument(
        "--speaker",
        metavar="SPEAKER",
        help="Normalize all supported audio files under audio/original/<Speaker>/",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Normalize all speakers discovered under audio/original/",
    )

    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Output path for --input mode (must be under audio/working/ and end in .wav)",
    )
    parser.add_argument(
        "--base-dir",
        metavar="DIR",
        default=".",
        help="Project base directory (default: current directory)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-normalization even when output is newer than source",
    )
    parser.add_argument(
        "--ffmpeg",
        metavar="PATH",
        default="",
        help="Path to ffmpeg executable (highest priority)",
    )

    return parser


def resolve_path(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def display_path(path: Path, base_dir: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except (ValueError, OSError, RuntimeError):
        return path.as_posix()


def is_supported_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def validate_speaker_name(speaker: str) -> str:
    speaker_name = speaker.strip()
    if not speaker_name:
        raise ValueError("Speaker name cannot be empty")
    if speaker_name in (".", ".."):
        raise ValueError("Speaker must be a directory name, not '.' or '..'")
    if "/" in speaker_name or "\\" in speaker_name:
        raise ValueError("Speaker must be a single directory name (no path separators)")
    if Path(speaker_name).name != speaker_name:
        raise ValueError("Speaker must be a single directory name")
    return speaker_name


def verify_ffmpeg_binary(candidate: str) -> bool:
    try:
        probe = subprocess.run(
            [candidate, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def resolve_ffmpeg_binary(cli_ffmpeg: str) -> str:
    candidate = cli_ffmpeg.strip()
    if candidate:
        if verify_ffmpeg_binary(candidate):
            return candidate
        print_error(f"ERROR: --ffmpeg is set but not executable: {candidate}")
        raise SystemExit(1)

    env_candidate = os.environ.get("FFMPEG_PATH", "").strip()
    if env_candidate:
        if verify_ffmpeg_binary(env_candidate):
            return env_candidate
        print(f"[normalize] WARNING: ignoring invalid FFMPEG_PATH: {env_candidate}")

    path_candidate = shutil.which("ffmpeg")
    if path_candidate and verify_ffmpeg_binary(path_candidate):
        return path_candidate

    choco_candidate = str(CHOCO_FFMPEG)
    if CHOCO_FFMPEG.exists() and verify_ffmpeg_binary(choco_candidate):
        return choco_candidate

    print_error("ERROR: Could not find a working ffmpeg binary.")
    print_error("Checked in this order:")
    print_error("  1) --ffmpeg argument")
    print_error("  2) FFMPEG_PATH environment variable")
    print_error("  3) ffmpeg on system PATH")
    print_error(f"  4) {choco_candidate}")
    print_error("")
    print_error("Install ffmpeg and try one of:")
    print_error("  - pass --ffmpeg /path/to/ffmpeg")
    print_error("  - set FFMPEG_PATH=/path/to/ffmpeg")
    print_error("  - add ffmpeg to your system PATH")
    raise SystemExit(1)


def collect_audio_files(speaker_input_dir: Path) -> list:
    files = []
    for candidate in speaker_input_dir.rglob("*"):
        if is_supported_audio_file(candidate):
            files.append(candidate)
    files.sort()
    return files


def make_job(source_path: Path, output_path: Path, label: str) -> dict:
    return {
        "source": source_path,
        "output": output_path,
        "label": label,
    }


def build_jobs_for_speaker(
    speaker: str,
    original_root: Path,
    working_root: Path,
) -> list:
    speaker_name = validate_speaker_name(speaker)
    speaker_input_dir = original_root / speaker_name
    if not speaker_input_dir.exists() or not speaker_input_dir.is_dir():
        raise ValueError(f"Speaker directory not found: {speaker_input_dir}")

    source_files = collect_audio_files(speaker_input_dir)
    jobs = []
    for source_path in source_files:
        relative_inside_speaker = source_path.relative_to(speaker_input_dir)
        working_dir = (working_root / speaker_name / relative_inside_speaker.parent).resolve()
        output_path = build_normalized_output_path(source_path, working_dir).resolve()
        source_label = f"{speaker_name}/{relative_inside_speaker.as_posix()}"
        jobs.append(make_job(source_path.resolve(), output_path, source_label))

    return jobs


def ensure_output_under_speaker_dir(output_path: Path, working_root: Path) -> None:
    if not path_is_within(output_path, working_root):
        raise ValueError("Output must be under audio/working/")

    relative_output = output_path.resolve().relative_to(working_root.resolve())
    if len(relative_output.parts) < 2:
        raise ValueError("Output must be under audio/working/<Speaker>/")


def ensure_unique_outputs(jobs: list) -> None:
    seen = {}
    for job in jobs:
        output_key = str(job["output"].resolve())
        source_path = job["source"]
        if output_key in seen:
            other_source = seen[output_key]
            raise ValueError(
                "Multiple input files map to the same output file: "
                f"{other_source} and {source_path}"
            )
        seen[output_key] = source_path


def build_jobs_for_all(original_root: Path, working_root: Path) -> list:
    if not original_root.exists() or not original_root.is_dir():
        raise ValueError(f"Input root does not exist: {original_root}")

    speaker_dirs = [p for p in original_root.iterdir() if p.is_dir()]
    speaker_dirs.sort(key=lambda p: p.name.lower())

    jobs = []
    for speaker_dir in speaker_dirs:
        jobs.extend(build_jobs_for_speaker(speaker_dir.name, original_root, working_root))
    return jobs


def build_jobs(
    args: argparse.Namespace,
    base_dir: Path,
    original_root: Path,
    working_root: Path,
) -> list:
    if args.input:
        if not args.output:
            raise ValueError("--output is required when using --input")

        source_path = resolve_path(args.input, base_dir)
        output_path = resolve_path(args.output, base_dir)

        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"Input file not found: {source_path}")
        if not path_is_within(source_path, original_root):
            raise ValueError(
                f"Input must be under {original_root.as_posix()} (read-only originals)"
            )
        if output_path.suffix.lower() != ".wav":
            raise ValueError("Output file must use .wav extension")
        if source_path.resolve() == output_path.resolve():
            raise ValueError("Input and output resolve to the same file")
        if path_is_within(output_path, original_root):
            raise ValueError("Refusing to write inside audio/original/")
        ensure_output_under_speaker_dir(output_path, working_root)

        label = source_path.resolve().relative_to(original_root.resolve()).as_posix()
        jobs = [make_job(source_path.resolve(), output_path.resolve(), label)]
        ensure_unique_outputs(jobs)
        return jobs

    if args.output:
        raise ValueError("--output can only be used together with --input")

    if args.speaker:
        jobs = build_jobs_for_speaker(args.speaker, original_root, working_root)
        ensure_unique_outputs(jobs)
        return jobs

    jobs = build_jobs_for_all(original_root, working_root)
    ensure_unique_outputs(jobs)
    return jobs


def is_up_to_date(source_path: Path, output_path: Path, force: bool) -> bool:
    if force:
        return False
    if not output_path.exists() or not output_path.is_file():
        return False
    return output_path.stat().st_mtime >= source_path.stat().st_mtime


def is_windows_binary(ffmpeg_bin: str) -> bool:
    """Return True if the ffmpeg binary is a Windows .exe (needs Windows-style paths)."""
    return ffmpeg_bin.lower().endswith(".exe")


def to_ffmpeg_path(path: Path, ffmpeg_bin: str) -> str:
    """Convert a Path to the format expected by ffmpeg.
    Windows .exe binaries need C:\\ style paths; native binaries get POSIX paths."""
    if is_windows_binary(ffmpeg_bin):
        try:
            result = subprocess.run(
                ["wslpath", "-w", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            win_path = result.stdout.strip()
            if win_path:
                return win_path
        except Exception:
            pass
    return str(path)


def run_command(command: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def extract_loudnorm_json_text(stderr_text: str) -> str:
    match = None
    for candidate in re.finditer(r'"input_i"\s*:', stderr_text):
        match = candidate

    if match is None:
        return ""

    marker_index = match.start()
    block_start = stderr_text.rfind("{", 0, marker_index)
    if block_start < 0:
        return ""

    depth = 0
    for index in range(block_start, len(stderr_text)):
        char = stderr_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stderr_text[block_start:index + 1]

    return ""


def parse_loudnorm_stats(stderr_text: str) -> dict:
    payload_text = extract_loudnorm_json_text(stderr_text)
    if not payload_text:
        return {}

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return {}

    required_keys = [
        "input_i",
        "input_tp",
        "input_lra",
        "input_thresh",
        "target_offset",
    ]

    stats = {}
    for key in required_keys:
        if key not in payload:
            return {}
        value_text = str(payload[key]).strip()
        try:
            float(value_text)
        except ValueError:
            return {}
        stats[key] = value_text

    return stats


def build_pass1_command(ffmpeg_bin: str, source_path: Path) -> list:
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-y",
        "-i",
        to_ffmpeg_path(source_path, ffmpeg_bin),
        "-af",
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
        "-f",
        "null",
        "-",
    ]


def build_pass2_command(ffmpeg_bin: str, source_path: Path, output_path: Path, stats: dict) -> list:
    loudnorm_filter = (
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:"
        f"measured_I={stats['input_i']}:"
        f"measured_TP={stats['input_tp']}:"
        f"measured_LRA={stats['input_lra']}:"
        f"measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}:"
        "linear=true"
    )

    return [
        ffmpeg_bin,
        "-hide_banner",
        "-y",
        "-i",
        to_ffmpeg_path(source_path, ffmpeg_bin),
        "-af",
        loudnorm_filter,
        "-ar",
        TARGET_SR,
        "-ac",
        TARGET_CHANNELS,
        "-c:a",
        "pcm_s16le",
        "-sample_fmt",
        TARGET_SAMPLE_FMT,
        to_ffmpeg_path(output_path, ffmpeg_bin),
    ]


def build_single_pass_command(ffmpeg_bin: str, source_path: Path, output_path: Path) -> list:
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-y",
        "-i",
        to_ffmpeg_path(source_path, ffmpeg_bin),
        "-af",
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}",
        "-ar",
        TARGET_SR,
        "-ac",
        TARGET_CHANNELS,
        "-c:a",
        "pcm_s16le",
        "-sample_fmt",
        TARGET_SAMPLE_FMT,
        to_ffmpeg_path(output_path, ffmpeg_bin),
    ]


def normalize_file(ffmpeg_bin: str, source_path: Path, output_path: Path, label: str) -> tuple:
    pass1 = run_command(build_pass1_command(ffmpeg_bin, source_path))
    if pass1.returncode != 0:
        return False, None, (
            "ffmpeg pass 1 failed\n"
            f"{pass1.stderr.strip()}"
        )

    stats = parse_loudnorm_stats(pass1.stderr)
    input_lufs = None

    if stats:
        try:
            input_lufs = float(stats["input_i"])
        except ValueError:
            input_lufs = None

        pass2 = run_command(build_pass2_command(ffmpeg_bin, source_path, output_path, stats))
        if pass2.returncode != 0:
            return False, input_lufs, (
                "ffmpeg pass 2 failed\n"
                f"{pass2.stderr.strip()}"
            )
    else:
        print(
            f"[normalize] WARNING: {label}: loudnorm JSON parse failed; using single-pass fallback"
        )
        fallback = run_command(build_single_pass_command(ffmpeg_bin, source_path, output_path))
        if fallback.returncode != 0:
            return False, None, (
                "ffmpeg single-pass fallback failed\n"
                f"{fallback.stderr.strip()}"
            )

    if not output_path.exists() or output_path.stat().st_size <= 0:
        return False, input_lufs, "ffmpeg reported success but output file was not created"

    return True, input_lufs, ""


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    base_dir = Path(args.base_dir).expanduser().resolve()
    original_root = base_dir / "audio" / "original"
    working_root = base_dir / "audio" / "working"

    try:
        jobs = build_jobs(args, base_dir, original_root, working_root)
    except ValueError as exc:
        print_error(f"ERROR: {exc}")
        return 1

    if not jobs:
        print("No matching audio files found.")
        print("Normalized 0 files, skipped 0 (already up-to-date), 0 errors")
        return 0

    ffmpeg_bin = resolve_ffmpeg_binary(args.ffmpeg)

    normalized_count = 0
    skipped_count = 0
    error_count = 0

    total = len(jobs)
    for index, job in enumerate(jobs, start=1):
        source_path = job["source"]
        output_path = job["output"]
        label = job["label"]

        print(f"Processing {index}/{total}: {label}")

        if is_up_to_date(source_path, output_path, args.force):
            output_display = display_path(output_path, base_dir)
            print(f"[normalize] {label} -> {output_display} (skipped, already up-to-date)")
            skipped_count += 1
            continue

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print_error(f"[normalize] ERROR: {label}: failed creating output directory: {exc}")
            error_count += 1
            continue

        success, input_lufs, error_message = normalize_file(
            ffmpeg_bin=ffmpeg_bin,
            source_path=source_path,
            output_path=output_path,
            label=label,
        )

        if not success:
            print_error(f"[normalize] ERROR: {label}")
            if error_message:
                print_error(error_message)
            error_count += 1
            continue

        output_display = display_path(output_path, base_dir)
        if input_lufs is None:
            before = "unknown"
        else:
            before = f"{input_lufs:.1f}"

        print(
            f"[normalize] {label} -> {output_display} "
            f"(done, {before} -> {TARGET_I_FLOAT:.1f} LUFS)"
        )
        normalized_count += 1

    print(
        f"Normalized {normalized_count} files, skipped {skipped_count} "
        f"(already up-to-date), {error_count} errors"
    )

    if error_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
