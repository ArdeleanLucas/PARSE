#!/usr/bin/env python3
"""
generate_peaks.py — Generate wavesurfer-compatible peaks JSON from WAV files.

Reads a WAV file (16-bit PCM, mono or stereo) and outputs a pre-computed
peaks JSON file for use with wavesurfer.js v7's MediaElement backend.

This allows waveform rendering without decoding the full audio in the browser,
which is critical for 500MB+ source recordings.

Usage:
    python generate_peaks.py <input.wav> <output.json> [--samples-per-pixel N]

Arguments:
    input.wav           Path to input WAV file (must be 16-bit PCM)
    output.json         Path for output peaks JSON file
    --samples-per-pixel Number of audio samples per waveform peak (default: auto, ~100/sec)

Output format (wavesurfer PeaksData v2):
    {
        "version": 2,
        "channels": 1,
        "sample_rate": 44100,
        "samples_per_pixel": 441,
        "bits": 16,
        "length": <number_of_peak_pairs>,
        "data": [min1, max1, min2, max2, ...]   // 16-bit integers
    }

Notes:
    - Only 16-bit PCM WAV files are supported (validate with ffprobe first)
    - Stereo files are averaged to mono peaks
    - Processes in chunks to handle 500MB+ files without loading into RAM
"""

import wave
import struct
import json
import math
import argparse
import sys
import os


# ── Constants ──────────────────────────────────────────────────────────────────

CHUNK_FRAMES = 44100 * 10         # Process 10 seconds of audio at a time
PCM16_MIN = -32768
PCM16_MAX = 32767


# ── WAV Validation ─────────────────────────────────────────────────────────────

def open_and_validate_wav(wav_path, output_path):
    """
    Open a WAV file, validate it meets requirements, and guard against self-overwrite.

    Returns:
        wave.Wave_read object (caller must close it)
    """
    if not os.path.exists(wav_path):
        print(f"ERROR: Input file not found: {wav_path}", file=sys.stderr)
        sys.exit(1)

    input_real = os.path.realpath(os.path.abspath(wav_path))
    output_real = os.path.realpath(os.path.abspath(output_path))
    if input_real == output_real:
        print(f"ERROR: Input and output paths point to the same file: {wav_path}", file=sys.stderr)
        print("       Aborting to prevent destructive overwrite.", file=sys.stderr)
        sys.exit(1)

    try:
        if os.path.exists(output_path) and os.path.samefile(wav_path, output_path):
            print(f"ERROR: Input and output paths point to the same file: {wav_path}", file=sys.stderr)
            print("       Aborting to prevent destructive overwrite.", file=sys.stderr)
            sys.exit(1)
    except OSError:
        pass # samefile not supported or file doesn't exist yet

    try:
        wav_file = wave.open(wav_path, 'rb')
    except wave.Error as e:
        print(f"ERROR: Could not open WAV file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error opening file: {e}", file=sys.stderr)
        sys.exit(1)

    sample_width = wav_file.getsampwidth()
    if sample_width != 2:
        bit_depth = sample_width * 8
        print(f"ERROR: Unsupported bit depth: {bit_depth}-bit", file=sys.stderr)
        print(f"       Only 16-bit PCM WAV files are supported.", file=sys.stderr)
        wav_file.close()
        sys.exit(1)

    n_channels = wav_file.getnchannels()
    if n_channels < 1 or n_channels > 2:
        print(f"ERROR: Unsupported channel count: {n_channels}", file=sys.stderr)
        wav_file.close()
        sys.exit(1)

    n_frames = wav_file.getnframes()
    if n_frames == 0:
        print(f"ERROR: WAV file contains no audio frames.", file=sys.stderr)
        wav_file.close()
        sys.exit(1)

    sample_rate = wav_file.getframerate()
    if sample_rate <= 0:
        print(f"ERROR: Invalid sample rate: {sample_rate}", file=sys.stderr)
        wav_file.close()
        sys.exit(1)

    duration_sec = n_frames / sample_rate
    file_size_mb = os.path.getsize(wav_path) / (1024 * 1024)

    print(f"  Format:      16-bit PCM {'mono' if n_channels == 1 else 'stereo'}")
    print(f"  Sample rate: {sample_rate} Hz")
    print(f"  Duration:    {duration_sec:.1f}s ({duration_sec / 60:.1f} min)")
    print(f"  Frames:      {n_frames:,}")
    print(f"  File size:   {file_size_mb:.1f} MB")

    return wav_file


# ── Peak Generation ─────────────────────────────────────────────────────────────

def _coerce_peak_int(value):
    """Convert a numeric peak value to a clamped signed 16-bit integer."""
    peak = int(round(value))
    if peak < PCM16_MIN:
        return PCM16_MIN
    if peak > PCM16_MAX:
        return PCM16_MAX
    return peak


def generate_peaks(wav_file, samples_per_pixel):
    """
    Generate interleaved min/max peaks from a WAV file as 16-bit integers.
    """
    n_channels = wav_file.getnchannels()
    n_frames = wav_file.getnframes()
    is_stereo = (n_channels == 2)

    fmt_char = '<' + ('h' * n_channels)
    frame_size = struct.calcsize(fmt_char)

    peaks = []

    current_min = float('inf')
    current_max = float('-inf')
    samples_in_window = 0

    frames_processed = 0
    last_progress = -1

    while True:
        raw = wav_file.readframes(CHUNK_FRAMES)
        if not raw:
            break

        n_raw_frames = len(raw) // frame_size
        if n_raw_frames == 0:
            break

        for sample_tuple in struct.iter_unpack(fmt_char, raw[:n_raw_frames * frame_size]):
            if is_stereo:
                sample = (sample_tuple[0] + sample_tuple[1]) / 2.0
            else:
                sample = sample_tuple[0]

            if sample < current_min:
                current_min = sample
            if sample > current_max:
                current_max = sample

            samples_in_window += 1

            if samples_in_window >= samples_per_pixel:
                peaks.append(_coerce_peak_int(current_min))
                peaks.append(_coerce_peak_int(current_max))
                current_min = float('inf')
                current_max = float('-inf')
                samples_in_window = 0

        frames_processed += n_raw_frames

        progress = int(frames_processed / n_frames * 10) * 10
        if progress != last_progress and progress <= 100:
            print(f"  Progress: {progress}% ({frames_processed:,} / {n_frames:,} frames)", end='\r')
            last_progress = progress

    print()

    if samples_in_window > 0 and current_min != float('inf'):
        peaks.append(_coerce_peak_int(current_min))
        peaks.append(_coerce_peak_int(current_max))

    return peaks


# ── Output ──────────────────────────────────────────────────────────────────────

def build_peaks_payload(sample_rate, samples_per_pixel, peaks):
    """Build a wavesurfer/audiowaveform PeaksData v2 payload."""
    if len(peaks) % 2 != 0:
        raise ValueError("peaks array must contain interleaved min/max pairs")

    coerced_peaks = []
    for peak in peaks:
        if not isinstance(peak, int):
            raise ValueError("peaks array must contain signed 16-bit integers")
        if peak < PCM16_MIN or peak > PCM16_MAX:
            raise ValueError(f"peak out of signed 16-bit range: {peak}")
        coerced_peaks.append(peak)

    n_pairs = len(coerced_peaks) // 2
    return {
        "version": 2,
        "channels": 1,
        "sample_rate": sample_rate,
        "samples_per_pixel": samples_per_pixel,
        "bits": 16,
        "length": n_pairs,
        "data": coerced_peaks,
    }


def write_peaks_json(output_path, sample_rate, samples_per_pixel, peaks):
    """
    Write peaks data to a JSON file in wavesurfer v2 format.
    """
    peaks_data = build_peaks_payload(sample_rate, samples_per_pixel, peaks)
    n_pairs = peaks_data["length"]

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(peaks_data, f, separators=(',', ':'))

    output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Peak pairs:  {n_pairs:,}")
    print(f"  Output size: {output_size_mb:.2f} MB")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate wavesurfer-compatible peaks JSON from a WAV file.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'input_wav',
        help='Path to input WAV file (16-bit PCM required)'
    )
    parser.add_argument(
        'output_json',
        help='Path for output peaks JSON file'
    )
    parser.add_argument(
        '--samples-per-pixel',
        type=int,
        default=None,
        metavar='N',
        help='Audio samples per waveform peak pair (default: auto, ~100 peaks/sec)'
    )

    args = parser.parse_args()

    print(f"Generating peaks for: {args.input_wav}")
    print(f"Output:               {args.output_json}")
    
    print("Validating WAV file...")
    wav_file = open_and_validate_wav(args.input_wav, args.output_json)

    sample_rate = wav_file.getframerate()
    
    samples_per_pixel = args.samples_per_pixel
    if samples_per_pixel is None:
        samples_per_pixel = sample_rate // 100
        print(f"Samples per pixel:    {samples_per_pixel} (auto-computed)")
    else:
        print(f"Samples per pixel:    {samples_per_pixel}")
        if samples_per_pixel < 1:
            print(f"ERROR: --samples-per-pixel must be >= 1, got {samples_per_pixel}", file=sys.stderr)
            sys.exit(1)

    approx_peaks_per_sec = sample_rate / samples_per_pixel
    print(f"  Peaks/second: ~{approx_peaks_per_sec:.1f}")
    print()

    print("Generating peaks...")
    try:
        peaks = generate_peaks(wav_file, samples_per_pixel)
    finally:
        wav_file.close()

    print()

    print("Writing output...")
    write_peaks_json(args.output_json, sample_rate, samples_per_pixel, peaks)

    print()
    print(f"Done! Peaks written to: {args.output_json}")


if __name__ == '__main__':
    main()
