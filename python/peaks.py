#!/usr/bin/env python3
"""
Generate wavesurfer-compatible PeaksData v2 JSON files from audio.

Single file:
    python generate_peaks.py --input audio/working/Fail01/recording.wav --output peaks/Fail01.json

Batch mode:
    python generate_peaks.py --input-dir audio/working --output-dir peaks
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import soundfile as sf


DEFAULT_SAMPLES_PER_PIXEL = 512
DEFAULT_FFMPEG_SAMPLE_RATE = 44100
INT16_MIN = -32768
INT16_MAX = 32767
AUDIO_EXTENSIONS = {".wav", ".wave", ".rf64", ".flac", ".mp3"}

STATUS_GENERATED = "generated"
STATUS_SKIPPED_EXISTING = "skipped_existing"
STATUS_SKIPPED_EMPTY = "skipped_empty"


class PeakAccumulator:
    """Incrementally builds interleaved int16 min/max peak pairs."""

    def __init__(self, samples_per_pixel: int) -> None:
        self.samples_per_pixel = samples_per_pixel
        self.total_samples = 0
        self._carry = np.empty(0, dtype=np.float32)
        self._data: list[int] = []

    def add_samples(self, samples: np.ndarray) -> None:
        """Add mono float32 samples and append completed peak windows."""
        if samples.size == 0:
            return

        mono = samples.astype(np.float32, copy=False).reshape(-1)
        self.total_samples += int(mono.size)

        if self._carry.size > 0:
            mono = np.concatenate((self._carry, mono))
            self._carry = np.empty(0, dtype=np.float32)

        window_count = mono.size // self.samples_per_pixel
        if window_count > 0:
            usable_samples = window_count * self.samples_per_pixel
            windows = mono[:usable_samples].reshape(window_count, self.samples_per_pixel)
            mins = np.min(windows, axis=1)
            maxs = np.max(windows, axis=1)
            self._append_peak_pairs(mins, maxs)
            mono = mono[usable_samples:]

        if mono.size > 0:
            self._carry = mono.copy()

    def finish(self) -> list[int]:
        """Flush remaining partial samples as a final min/max pair."""
        if self._carry.size > 0:
            mins = np.array([np.min(self._carry)], dtype=np.float32)
            maxs = np.array([np.max(self._carry)], dtype=np.float32)
            self._append_peak_pairs(mins, maxs)
            self._carry = np.empty(0, dtype=np.float32)

        return self._data

    def _append_peak_pairs(self, mins: np.ndarray, maxs: np.ndarray) -> None:
        """Scale float peaks to int16 range and append interleaved min/max."""
        min_int = scale_float_array_to_int16(mins)
        max_int = scale_float_array_to_int16(maxs)

        interleaved = np.empty(min_int.size * 2, dtype=np.int32)
        interleaved[0::2] = min_int
        interleaved[1::2] = max_int

        self._data.extend(interleaved.tolist())


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    print(f"ERROR: {message}", file=sys.stderr)


def print_warning(message: str) -> None:
    """Print a warning message to stderr."""
    print(f"WARNING: {message}", file=sys.stderr)


def scale_float_array_to_int16(values: np.ndarray) -> np.ndarray:
    """Scale float samples in [-1, 1] to clamped signed 16-bit integers."""
    scaled = np.trunc(values.astype(np.float32, copy=False) * 32767.0)
    clamped = np.clip(scaled, INT16_MIN, INT16_MAX)
    return clamped.astype(np.int32, copy=False)


def downmix_to_mono(samples: np.ndarray) -> np.ndarray:
    """Convert N-channel float32 samples to mono by averaging channels."""
    if samples.ndim == 1:
        return samples.astype(np.float32, copy=False)
    return np.mean(samples, axis=1, dtype=np.float32)


def guard_against_self_overwrite(input_path: Path, output_path: Path) -> None:
    """Abort if input and output resolve to the same real path."""
    input_real = input_path.resolve(strict=True)
    output_real = output_path.resolve(strict=False)
    if input_real == output_real:
        raise ValueError(
            f"Input and output resolve to the same path: {input_path}"
        )


def generate_peaks_with_soundfile(
    input_path: Path, samples_per_pixel: int
) -> tuple[int, list[int], int]:
    """Read audio via soundfile and compute PeaksData min/max pairs."""
    with sf.SoundFile(str(input_path), mode="r") as audio_file:
        sample_rate = int(audio_file.samplerate)
        if sample_rate <= 0:
            raise RuntimeError(f"Invalid sample rate in file: {sample_rate}")

        total_frames = int(len(audio_file))
        if total_frames == 0:
            return sample_rate, [], 0

        chunk_frames = max(1, sample_rate)
        accumulator = PeakAccumulator(samples_per_pixel)

        while True:
            chunk = audio_file.read(
                frames=chunk_frames,
                dtype="float32",
                always_2d=True,
            )
            if chunk.size == 0:
                break

            mono = downmix_to_mono(chunk)
            accumulator.add_samples(mono)

        return sample_rate, accumulator.finish(), accumulator.total_samples


def generate_peaks_with_ffmpeg_mp3(
    input_path: Path, samples_per_pixel: int
) -> tuple[int, list[int], int]:
    """Fallback MP3 decoder using ffmpeg raw float32 mono output."""
    sample_rate = DEFAULT_FFMPEG_SAMPLE_RATE
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(input_path),
        "-f",
        "f32le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "pipe:1",
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg not found for MP3 fallback") from exc

    chunk_bytes = sample_rate * 4
    byte_carry = b""
    stderr_bytes = b""
    accumulator = PeakAccumulator(samples_per_pixel)

    try:
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("Failed to create ffmpeg pipes")

        while True:
            raw = process.stdout.read(chunk_bytes)
            if raw == b"":
                break

            byte_carry += raw
            usable = (len(byte_carry) // 4) * 4
            if usable == 0:
                continue

            block = byte_carry[:usable]
            byte_carry = byte_carry[usable:]

            samples = np.frombuffer(block, dtype="<f4")
            accumulator.add_samples(samples)

        stderr_bytes = process.stderr.read()
    finally:
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    return_code = process.wait()
    if return_code != 0:
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        detail = stderr_text if stderr_text else "unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg MP3 decode failed: {detail}")

    return sample_rate, accumulator.finish(), accumulator.total_samples


def generate_peaks_for_audio(
    input_path: Path, samples_per_pixel: int
) -> tuple[int, list[int], int]:
    """Generate peaks for an audio file, with MP3 ffmpeg fallback when needed."""
    try:
        return generate_peaks_with_soundfile(input_path, samples_per_pixel)
    except Exception as exc:
        if input_path.suffix.lower() == ".mp3":
            print_warning(
                f"soundfile could not decode MP3 ({exc}); falling back to ffmpeg"
            )
            return generate_peaks_with_ffmpeg_mp3(input_path, samples_per_pixel)
        raise RuntimeError(f"soundfile decode failed: {exc}") from exc


def build_peaks_payload(
    sample_rate: int, samples_per_pixel: int, data: list[int]
) -> dict:
    """Build a PeaksData v2 payload for wavesurfer."""
    if len(data) % 2 != 0:
        raise ValueError("Peak data must contain interleaved min/max pairs")

    return {
        "version": 2,
        "channels": 1,
        "sample_rate": int(sample_rate),
        "samples_per_pixel": int(samples_per_pixel),
        "bits": 16,
        "length": len(data) // 2,
        "data": data,
    }


def write_peaks_json(output_path: Path, payload: dict) -> None:
    """Write the PeaksData payload to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, separators=(",", ":"))


def process_audio_file(
    input_path: Path,
    output_path: Path,
    samples_per_pixel: int,
    force: bool,
) -> str:
    """Generate a single peaks file and return status."""
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    guard_against_self_overwrite(input_path, output_path)

    if output_path.exists() and not force:
        print(f"SKIP: {output_path} (already exists)")
        return STATUS_SKIPPED_EXISTING

    sample_rate, peak_data, total_samples = generate_peaks_for_audio(
        input_path,
        samples_per_pixel,
    )

    if total_samples == 0:
        print_warning(f"Zero-length file, skipped: {input_path}")
        return STATUS_SKIPPED_EMPTY

    payload = build_peaks_payload(sample_rate, samples_per_pixel, peak_data)
    write_peaks_json(output_path, payload)

    print(
        f"WROTE: {output_path} "
        f"(sample_rate={payload['sample_rate']}, pixels={payload['length']})"
    )
    return STATUS_GENERATED


def discover_audio_files(input_dir: Path) -> list[Path]:
    """Recursively discover supported audio files in a directory."""
    audio_files: list[Path] = []

    for root, _, files in os.walk(input_dir):
        root_path = Path(root)
        for filename in files:
            suffix = Path(filename).suffix.lower()
            if suffix in AUDIO_EXTENSIONS:
                audio_files.append(root_path / filename)

    audio_files.sort(key=lambda path: path.as_posix().lower())
    return audio_files


def speaker_key_for_file(input_dir: Path, audio_path: Path) -> str:
    """Get speaker key from path relative to input_dir."""
    relative = audio_path.relative_to(input_dir)
    if len(relative.parts) >= 2:
        return relative.parts[0]
    return relative.stem


def unique_output_name(base_name: str, used_names: set[str]) -> str:
    """Return a unique output stem, appending a numeric suffix if needed."""
    if base_name not in used_names:
        return base_name

    index = 2
    while True:
        candidate = f"{base_name}_{index}"
        if candidate not in used_names:
            return candidate
        index += 1


def plan_batch_jobs(
    input_dir: Path,
    output_dir: Path,
    audio_files: list[Path],
) -> list[tuple[Path, Path]]:
    """Map discovered audio files to output JSON files."""
    grouped: dict[str, list[Path]] = {}
    for audio_path in audio_files:
        speaker = speaker_key_for_file(input_dir, audio_path)
        grouped.setdefault(speaker, []).append(audio_path)

    used_names: set[str] = set()
    jobs: list[tuple[Path, Path]] = []

    for speaker in sorted(grouped.keys()):
        files = sorted(grouped[speaker], key=lambda path: path.as_posix().lower())
        multiple_for_speaker = len(files) > 1

        for audio_path in files:
            base_name = speaker
            if multiple_for_speaker:
                base_name = f"{speaker}_{audio_path.stem}"

            output_stem = unique_output_name(base_name, used_names)
            used_names.add(output_stem)
            jobs.append((audio_path, output_dir / f"{output_stem}.json"))

    return jobs


def run_single_mode(
    input_path: Path,
    output_path: Path,
    samples_per_pixel: int,
    force: bool,
) -> int:
    """Run peaks generation for a single file."""
    if not input_path.is_file():
        print_error(f"Input file not found: {input_path}")
        return 1

    try:
        status = process_audio_file(
            input_path=input_path,
            output_path=output_path,
            samples_per_pixel=samples_per_pixel,
            force=force,
        )
    except Exception as exc:
        print_error(str(exc))
        return 1

    if status == STATUS_SKIPPED_EXISTING:
        print("Nothing to do. Use --force to regenerate.")
    elif status == STATUS_SKIPPED_EMPTY:
        print("Input had no samples; nothing written.")
    else:
        print("Done.")

    return 0


def run_batch_mode(
    input_dir: Path,
    output_dir: Path,
    samples_per_pixel: int,
    force: bool,
) -> int:
    """Run peaks generation for all discovered files in a directory tree."""
    if not input_dir.is_dir():
        print_error(f"Input directory not found: {input_dir}")
        return 1

    audio_files = discover_audio_files(input_dir)
    if not audio_files:
        print_warning(f"No supported audio files found in: {input_dir}")
        return 0

    jobs = plan_batch_jobs(input_dir, output_dir, audio_files)

    generated_count = 0
    skipped_existing_count = 0
    skipped_empty_count = 0
    error_count = 0

    print(f"Discovered {len(jobs)} audio file(s).")

    for index, (input_path, output_path) in enumerate(jobs, start=1):
        relative = input_path.relative_to(input_dir)
        print(f"[{index}/{len(jobs)}] {relative}")

        try:
            status = process_audio_file(
                input_path=input_path,
                output_path=output_path,
                samples_per_pixel=samples_per_pixel,
                force=force,
            )
        except Exception as exc:
            print_error(f"{relative}: {exc}")
            error_count += 1
            continue

        if status == STATUS_GENERATED:
            generated_count += 1
        elif status == STATUS_SKIPPED_EXISTING:
            skipped_existing_count += 1
        elif status == STATUS_SKIPPED_EMPTY:
            skipped_empty_count += 1

    print(
        "Batch complete: "
        f"generated={generated_count}, "
        f"skipped_existing={skipped_existing_count}, "
        f"skipped_empty={skipped_empty_count}, "
        f"errors={error_count}"
    )

    if error_count > 0:
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    """Parse and validate CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate wavesurfer PeaksData v2 JSON from audio files.",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--input",
        type=Path,
        help="Single input audio file",
    )
    mode_group.add_argument(
        "--input-dir",
        type=Path,
        help="Input directory for batch mode (recursive)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON path for single-file mode",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for batch mode",
    )
    parser.add_argument(
        "--samples-per-pixel",
        type=int,
        default=DEFAULT_SAMPLES_PER_PIXEL,
        help=f"Samples per waveform pixel (default: {DEFAULT_SAMPLES_PER_PIXEL})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate peaks even when output JSON already exists",
    )

    args = parser.parse_args()

    if args.samples_per_pixel < 1:
        parser.error("--samples-per-pixel must be >= 1")

    if args.input is not None:
        if args.output is None:
            parser.error("--output is required when using --input")
        if args.output_dir is not None:
            parser.error("--output-dir cannot be used with --input")
    else:
        if args.output_dir is None:
            parser.error("--output-dir is required when using --input-dir")
        if args.output is not None:
            parser.error("--output cannot be used with --input-dir")

    return args


def main() -> None:
    """CLI entry point."""
    args = parse_args()

    if args.input is not None:
        exit_code = run_single_mode(
            input_path=args.input,
            output_path=args.output,
            samples_per_pixel=args.samples_per_pixel,
            force=args.force,
        )
    else:
        exit_code = run_batch_mode(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            samples_per_pixel=args.samples_per_pixel,
            force=args.force,
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
