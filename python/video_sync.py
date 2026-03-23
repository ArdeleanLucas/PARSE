#!/usr/bin/env python3
"""
video_sync.py - FFT-based audio sync for PARSE video review.

Examples:
    python video_sync.py --video Khan01_session.mp4 --audio audio/working/Khan01/REC00002.wav --fps 60
    python video_sync.py --video Khan01_session.mp4 --audio audio/working/Khan01/REC00002.wav --fps 60 --points 5 --output sync/Khan01_sync.json
    python video_sync.py --video Khan01_session.mp4 --audio audio/working/Khan01/REC00002.wav --fps 60 --ffmpeg "C:/ProgramData/chocolatey/bin/ffmpeg.exe"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

try:
    from scipy.signal import fftconvolve as _scipy_fftconvolve
except Exception:
    _scipy_fftconvolve = None


SAMPLE_RATE_HZ = 16000
DEFAULT_CHUNK_SEC = 30.0
DEFAULT_DRIFT_POINTS = 5
ANCHOR_POINTS = 3
MIN_ANALYSIS_SEC = 2.0
DRIFT_WARNING_SEC_PER_MIN = 0.1
PEAK_EXCLUSION_SEC = 0.05

_SCIPY_WARNING_SHOWN = False


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    print(f"ERROR: {message}", file=sys.stderr)



def print_warning(message: str) -> None:
    """Print a warning message to stderr."""
    print(f"WARNING: {message}", file=sys.stderr)



def _require_input_file(path: Path, label: str) -> None:
    """Validate that a required input path exists and is a file."""
    if not path.exists():
        raise RuntimeError(f"{label} not found: {path}")
    if not path.is_file():
        raise RuntimeError(f"{label} is not a file: {path}")



def _resolve_ffprobe_path(ffmpeg_path: str) -> str:
    """Infer ffprobe path from ffmpeg path when possible."""
    ffmpeg_binary = ffmpeg_path.strip()
    ffmpeg_name = Path(ffmpeg_binary).name.lower()
    if ffmpeg_name == "ffmpeg":
        return str(Path(ffmpeg_binary).with_name("ffprobe"))
    if ffmpeg_name == "ffmpeg.exe":
        return str(Path(ffmpeg_binary).with_name("ffprobe.exe"))
    return "ffprobe"



def _run_subprocess(command: list[str], description: str) -> subprocess.CompletedProcess:
    """Run a subprocess command and raise a detailed RuntimeError on failure."""
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"{description}: executable not found: {command[0]}. "
            "Install ffmpeg/ffprobe or pass --ffmpeg with a valid path."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"{description}: failed to run command: {exc}") from exc

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
        detail = stderr_text if stderr_text else "unknown subprocess error"
        raise RuntimeError(f"{description} failed: {detail}")

    return result



def _probe_duration_seconds(path: Path, ffprobe_path: str) -> float:
    """Get media duration (seconds) via ffprobe."""
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = _run_subprocess(command, f"ffprobe duration check for {path}")
    output_text = result.stdout.decode("utf-8", errors="replace").strip()
    if output_text == "":
        raise RuntimeError(f"Could not read duration from ffprobe output: {path}")

    try:
        duration = float(output_text)
    except ValueError as exc:
        raise RuntimeError(
            f"ffprobe returned a non-numeric duration for {path}: {output_text!r}"
        ) from exc

    if not np.isfinite(duration) or duration <= 0.0:
        raise RuntimeError(f"Invalid media duration for {path}: {duration}")
    return float(duration)



def _extract_audio_chunk(
    input_path: Path,
    start_sec: float,
    duration_sec: float,
    ffmpeg_path: str,
    is_video_input: bool,
) -> np.ndarray:
    """Extract mono float32 16kHz samples from a media chunk using ffmpeg."""
    if duration_sec <= 0.0:
        return np.empty(0, dtype=np.float32)

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-ss",
        f"{max(0.0, start_sec):.6f}",
        "-i",
        str(input_path),
        "-t",
        f"{duration_sec:.6f}",
    ]

    if is_video_input:
        command.append("-vn")

    command.extend(
        [
            "-ar",
            str(SAMPLE_RATE_HZ),
            "-ac",
            "1",
            "-f",
            "f32le",
            "pipe:1",
        ]
    )

    result = _run_subprocess(command, f"ffmpeg audio extraction for {input_path}")
    raw = result.stdout
    if not raw:
        return np.empty(0, dtype=np.float32)

    usable_bytes = (len(raw) // 4) * 4
    if usable_bytes <= 0:
        return np.empty(0, dtype=np.float32)

    if usable_bytes != len(raw):
        raw = raw[:usable_bytes]

    return np.frombuffer(raw, dtype="<f4").astype(np.float32, copy=False)



def _normalize_signal(samples: np.ndarray) -> np.ndarray:
    """Center and scale a signal for correlation stability."""
    if samples.size == 0:
        return samples.astype(np.float32, copy=False)

    centered = samples.astype(np.float32, copy=False) - np.mean(samples, dtype=np.float32)
    std = float(np.std(centered, dtype=np.float32))
    if std > 1e-8:
        centered = centered / std
    return centered



def _fft_convolve_numpy(signal_a: np.ndarray, signal_b: np.ndarray) -> np.ndarray:
    """Numpy-only FFT convolution fallback when scipy is unavailable."""
    target_len = int(signal_a.size + signal_b.size - 1)
    if target_len <= 0:
        return np.empty(0, dtype=np.float64)

    fft_len = 1 << (target_len - 1).bit_length()
    fft_a = np.fft.rfft(signal_a, n=fft_len)
    fft_b = np.fft.rfft(signal_b, n=fft_len)
    full = np.fft.irfft(fft_a * fft_b, n=fft_len)
    return full[:target_len]



def _fft_cross_correlation(video_samples: np.ndarray, audio_samples: np.ndarray) -> np.ndarray:
    """Compute full cross-correlation using scipy fftconvolve when available."""
    global _SCIPY_WARNING_SHOWN

    reversed_audio = audio_samples[::-1]
    if _scipy_fftconvolve is not None:
        return _scipy_fftconvolve(video_samples, reversed_audio, mode="full")

    if not _SCIPY_WARNING_SHOWN:
        print_warning(
            "scipy is not available; using numpy FFT fallback for cross-correlation"
        )
        _SCIPY_WARNING_SHOWN = True

    return _fft_convolve_numpy(video_samples, reversed_audio)



def _peak_confidence(abs_correlation: np.ndarray, peak_index: int) -> float:
    """Estimate confidence from primary-vs-secondary peak prominence ratio."""
    if abs_correlation.size == 0:
        return 0.0

    peak_value = float(abs_correlation[peak_index])
    if peak_value <= 0.0:
        return 0.0

    if abs_correlation.size == 1:
        return 1.0

    exclusion_radius = max(1, int(PEAK_EXCLUSION_SEC * SAMPLE_RATE_HZ))
    left = max(0, peak_index - exclusion_radius)
    right = min(abs_correlation.size, peak_index + exclusion_radius + 1)

    competing = abs_correlation.copy()
    competing[left:right] = 0.0
    second_peak = float(np.max(competing))

    if second_peak <= 0.0:
        return 1.0

    prominence_ratio = (peak_value - second_peak) / peak_value
    return float(np.clip(prominence_ratio, 0.0, 1.0))



def _analysis_chunk_seconds(overlap_duration_sec: float) -> float:
    """Choose a chunk length that fits inside the overlap region."""
    if overlap_duration_sec <= 0.0:
        return 0.0

    chunk_sec = min(DEFAULT_CHUNK_SEC, overlap_duration_sec)
    if chunk_sec < MIN_ANALYSIS_SEC:
        return overlap_duration_sec
    return float(chunk_sec)



def _build_probe_centers(
    overlap_duration_sec: float,
    n_points: int,
    chunk_sec: float,
) -> list[float]:
    """Build evenly spaced probe center times within valid extraction bounds."""
    if n_points <= 1:
        return [overlap_duration_sec / 2.0]

    if overlap_duration_sec <= chunk_sec:
        return [overlap_duration_sec / 2.0]

    start_center = chunk_sec / 2.0
    end_center = overlap_duration_sec - (chunk_sec / 2.0)
    if end_center <= start_center:
        return [overlap_duration_sec / 2.0]

    if n_points == 2:
        return [start_center, end_center]

    step = (end_center - start_center) / float(n_points - 1)
    return [start_center + (index * step) for index in range(n_points)]



def _measure_offset_at_center(
    video_path: Path,
    audio_path: Path,
    center_sec: float,
    chunk_sec: float,
    ffmpeg_path: str,
) -> dict:
    """Measure correlation offset at a single analysis center time."""
    start_sec = max(0.0, center_sec - (chunk_sec / 2.0))

    video_chunk = _extract_audio_chunk(
        input_path=video_path,
        start_sec=start_sec,
        duration_sec=chunk_sec,
        ffmpeg_path=ffmpeg_path,
        is_video_input=True,
    )
    audio_chunk = _extract_audio_chunk(
        input_path=audio_path,
        start_sec=start_sec,
        duration_sec=chunk_sec,
        ffmpeg_path=ffmpeg_path,
        is_video_input=False,
    )

    usable_samples = int(min(video_chunk.size, audio_chunk.size))
    min_required_samples = int(MIN_ANALYSIS_SEC * SAMPLE_RATE_HZ)
    if usable_samples < min_required_samples:
        raise RuntimeError(
            f"Not enough overlapping samples at t={center_sec:.2f}s "
            f"(got {usable_samples}, need at least {min_required_samples})"
        )

    video_norm = _normalize_signal(video_chunk[:usable_samples])
    audio_norm = _normalize_signal(audio_chunk[:usable_samples])

    if float(np.std(video_norm)) < 1e-6 or float(np.std(audio_norm)) < 1e-6:
        raise RuntimeError(f"Chunk near t={center_sec:.2f}s is too silent for stable sync")

    correlation = _fft_cross_correlation(video_norm, audio_norm)
    abs_correlation = np.abs(correlation)
    if abs_correlation.size == 0:
        raise RuntimeError(f"Cross-correlation returned no samples at t={center_sec:.2f}s")

    peak_index = int(np.argmax(abs_correlation))
    lag_samples = peak_index - (audio_norm.size - 1)
    offset_sec = float(lag_samples) / float(SAMPLE_RATE_HZ)
    confidence = _peak_confidence(abs_correlation, peak_index)

    return {
        "time_sec": float(center_sec),
        "offset_sec": float(offset_sec),
        "confidence": float(confidence),
    }



def _collect_sync_points(
    video_path: Path,
    audio_path: Path,
    n_points: int,
    ffmpeg_path: str,
) -> list[dict]:
    """Collect offset measurements at evenly spaced points across the overlap."""
    if n_points < 1:
        raise ValueError("n_points must be >= 1")

    _require_input_file(video_path, "Video file")
    _require_input_file(audio_path, "Audio file")

    ffprobe_path = _resolve_ffprobe_path(ffmpeg_path)
    video_duration_sec = _probe_duration_seconds(video_path, ffprobe_path)
    audio_duration_sec = _probe_duration_seconds(audio_path, ffprobe_path)

    overlap_duration_sec = float(min(video_duration_sec, audio_duration_sec))
    if overlap_duration_sec <= 0.0:
        raise RuntimeError("No overlapping duration between video and audio files")

    if video_duration_sec < audio_duration_sec:
        print_warning(
            "Video is shorter than reference audio; using overlap only for sync analysis"
        )

    chunk_sec = _analysis_chunk_seconds(overlap_duration_sec)
    if chunk_sec <= 0.0:
        raise RuntimeError("Could not determine a valid analysis chunk length")

    centers = _build_probe_centers(overlap_duration_sec, n_points, chunk_sec)

    measurements = []
    for center_sec in centers:
        try:
            measurement = _measure_offset_at_center(
                video_path=video_path,
                audio_path=audio_path,
                center_sec=float(center_sec),
                chunk_sec=chunk_sec,
                ffmpeg_path=ffmpeg_path,
            )
            measurements.append(measurement)
        except RuntimeError as exc:
            print_warning(str(exc))

    if not measurements:
        raise RuntimeError(
            "Failed to compute any sync points. "
            "Check that both files contain clear overlapping speech/audio."
        )

    return measurements



def _fit_offset_line(points: list[dict]) -> tuple[float, float, float]:
    """Fit offset = intercept + slope * time and return residual std deviation."""
    if not points:
        raise ValueError("At least one sync point is required")

    if len(points) == 1:
        return 0.0, float(points[0]["offset_sec"]), 0.0

    x_values = np.array([float(point["time_sec"]) for point in points], dtype=np.float64)
    y_values = np.array([float(point["offset_sec"]) for point in points], dtype=np.float64)

    x_mean = float(np.mean(x_values))
    y_mean = float(np.mean(y_values))
    centered_x = x_values - x_mean
    denominator = float(np.dot(centered_x, centered_x))

    if denominator <= 1e-12:
        slope = 0.0
    else:
        numerator = float(np.dot(centered_x, y_values - y_mean))
        slope = numerator / denominator

    intercept = y_mean - (slope * x_mean)
    residuals = y_values - (intercept + (slope * x_values))
    residual_std = float(np.std(residuals))
    return float(slope), float(intercept), float(residual_std)



def _robust_intercept(points: list[dict], slope_sec_per_sec: float) -> float:
    """Estimate time-zero offset using the median corrected offset across points."""
    if not points:
        raise ValueError("At least one sync point is required")

    corrected_offsets = np.array(
        [
            float(point["offset_sec"]) - (slope_sec_per_sec * float(point["time_sec"]))
            for point in points
        ],
        dtype=np.float64,
    )
    return float(np.median(corrected_offsets))



def _combined_confidence(points: list[dict], residual_std: float) -> float:
    """Combine per-point peak confidence with line-fit consistency."""
    if not points:
        return 0.0

    point_confidence = float(
        np.median(np.array([float(point["confidence"]) for point in points], dtype=np.float64))
    )
    fit_confidence = float(np.clip(1.0 - (residual_std / 0.25), 0.0, 1.0))
    return float(np.clip((0.75 * point_confidence) + (0.25 * fit_confidence), 0.0, 1.0))



def _detect_offset_with_points(
    video_path: Path,
    audio_path: Path,
    n_points: int,
    ffmpeg_path: str,
) -> dict:
    """Internal detect_offset implementation with configurable drift points."""
    anchor_points = _collect_sync_points(
        video_path=video_path,
        audio_path=audio_path,
        n_points=ANCHOR_POINTS,
        ffmpeg_path=ffmpeg_path,
    )
    drift_points = _collect_sync_points(
        video_path=video_path,
        audio_path=audio_path,
        n_points=max(1, n_points),
        ffmpeg_path=ffmpeg_path,
    )

    slope_sec_per_sec, _ols_intercept, residual_std = _fit_offset_line(drift_points)
    drift_rate_sec_per_min = slope_sec_per_sec * 60.0
    if abs(drift_rate_sec_per_min) > DRIFT_WARNING_SEC_PER_MIN:
        print_warning(
            f"High drift detected: {drift_rate_sec_per_min:.6f} sec/min "
            f"(threshold: {DRIFT_WARNING_SEC_PER_MIN:.3f})"
        )

    all_points = anchor_points + drift_points
    offset_sec = _robust_intercept(all_points, slope_sec_per_sec)
    confidence = _combined_confidence(all_points, residual_std)

    return {
        "offset_sec": float(offset_sec),
        "drift_rate": float(drift_rate_sec_per_min),
        "confidence": float(confidence),
        "method": "fft_auto",
    }



def detect_offset(video_path: Path, audio_path: Path, ffmpeg_path: str = "ffmpeg") -> dict:
    """
    Detect time offset between video and reference WAV.

    Returns: {"offset_sec": float, "drift_rate": float, "confidence": float, "method": "fft_auto"}
    """
    return _detect_offset_with_points(
        video_path=video_path,
        audio_path=audio_path,
        n_points=DEFAULT_DRIFT_POINTS,
        ffmpeg_path=ffmpeg_path,
    )



def sync_points(
    video_path: Path,
    audio_path: Path,
    n_points: int = 5,
    ffmpeg_path: str = "ffmpeg",
) -> list[dict]:
    """
    Measure offset at N evenly spaced points through the recording.

    Returns list of {"time_sec": float, "offset_sec": float} dicts.
    """
    points = _collect_sync_points(
        video_path=video_path,
        audio_path=audio_path,
        n_points=n_points,
        ffmpeg_path=ffmpeg_path,
    )
    return [
        {
            "time_sec": float(point["time_sec"]),
            "offset_sec": float(point["offset_sec"]),
        }
        for point in points
    ]



def _build_sync_payload(video_file: str, audio_file: str, fps: int, sync_data: dict) -> dict:
    """Build sync JSON payload in PARSE schema."""
    payload_sync = {
        "status": str(sync_data.get("status", "synced")),
        "offset_sec": float(sync_data.get("offset_sec", 0.0)),
        "drift_rate": float(sync_data.get("drift_rate", 0.0)),
        "method": str(sync_data.get("method", "fft_auto")),
        "ai_verified": bool(sync_data.get("ai_verified", False)),
        "manual_adjustment_sec": float(sync_data.get("manual_adjustment_sec", 0.0)),
    }

    return {
        "video_file": video_file,
        "audio_file": audio_file,
        "fps": int(fps),
        "sync": payload_sync,
    }



def write_sync_file(
    output_path: Path,
    video_file: str,
    audio_file: str,
    fps: int,
    sync_data: dict,
) -> None:
    """Write sync result JSON to disk."""
    payload = _build_sync_payload(
        video_file=video_file,
        audio_file=audio_file,
        fps=fps,
        sync_data=sync_data,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, indent=2)



def _build_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Detect video/audio offset and drift using FFT cross-correlation "
            "on extracted 16kHz mono chunks."
        )
    )
    parser.add_argument(
        "--video",
        required=True,
        type=Path,
        help="Path to input video file",
    )
    parser.add_argument(
        "--audio",
        required=True,
        type=Path,
        help="Path to reference WAV file",
    )
    parser.add_argument(
        "--fps",
        required=True,
        type=int,
        help="Video frame rate used downstream for timestamp mapping",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=DEFAULT_DRIFT_POINTS,
        help=f"Number of drift probe points (default: {DEFAULT_DRIFT_POINTS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output JSON path",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="Path to ffmpeg executable (default: ffmpeg from PATH)",
    )
    return parser



def main() -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.fps <= 0:
        parser.error("--fps must be > 0")
    if args.points < 1:
        parser.error("--points must be >= 1")

    try:
        sync_data = _detect_offset_with_points(
            video_path=args.video,
            audio_path=args.audio,
            n_points=args.points,
            ffmpeg_path=args.ffmpeg,
        )
    except (RuntimeError, ValueError) as exc:
        print_error(str(exc))
        return 1

    sync_record = {
        "status": "synced",
        "offset_sec": float(sync_data["offset_sec"]),
        "drift_rate": float(sync_data["drift_rate"]),
        "method": str(sync_data.get("method", "fft_auto")),
        "ai_verified": False,
        "manual_adjustment_sec": 0.0,
    }

    payload = _build_sync_payload(
        video_file=args.video.name,
        audio_file=args.audio.as_posix(),
        fps=args.fps,
        sync_data=sync_record,
    )

    print(json.dumps(payload, indent=2))
    print(
        f"confidence={sync_data['confidence']:.3f}, "
        f"offset_sec={sync_data['offset_sec']:.6f}, "
        f"drift_rate={sync_data['drift_rate']:.6f} sec/min"
    )

    if args.output is not None:
        try:
            write_sync_file(
                output_path=args.output,
                video_file=args.video.name,
                audio_file=args.audio.as_posix(),
                fps=args.fps,
                sync_data=sync_record,
            )
        except OSError as exc:
            print_error(f"Failed writing output file {args.output}: {exc}")
            return 1
        print(f"WROTE: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
