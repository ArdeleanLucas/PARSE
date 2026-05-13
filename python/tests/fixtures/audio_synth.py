"""Synthetic WAV builders for long-form audio regression tests."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16_000
_BLOCK_SECONDS = 10.0
_SPEECH_THEN_SILENCE_SPEECH_SEC = 15.0 * 60.0
_HALLUCINATION_TRIGGER_START_SEC = 14.0 * 60.0
_HALLUCINATION_TRIGGER_NOISE_SEC = 15.0
_HALLUCINATION_TRIGGER_SILENCE_SEC = 15.0

GroundTruthInterval = dict[str, float | str]


def _default_output_path() -> Path:
    fd, raw_path = tempfile.mkstemp(suffix=".wav")
    try:
        return Path(raw_path)
    finally:
        import os

        os.close(fd)


def _candidate_seed_clip(seed_clip_path: Optional[Path]) -> np.ndarray | None:
    candidates: list[Path] = []
    if seed_clip_path is not None:
        candidates.append(Path(seed_clip_path))
    tests_root = Path(__file__).resolve().parents[1]
    if tests_root.exists():
        candidates.extend(sorted(tests_root.rglob("*.wav")))
    for candidate in candidates:
        try:
            data, sample_rate = sf.read(str(candidate), dtype="float32", always_2d=False)
        except Exception:
            continue
        if int(sample_rate) != SAMPLE_RATE:
            continue
        if data.size == 0:
            continue
        if data.ndim > 1:
            data = data.mean(axis=1)
        return np.asarray(data, dtype=np.float32)
    return None


def _speech_surrogate(start_sample: int, sample_count: int) -> np.ndarray:
    sample_index = np.arange(start_sample, start_sample + sample_count, dtype=np.float64)
    t = sample_index / float(SAMPLE_RATE)
    envelope = 0.55 + 0.35 * np.sin(2.0 * math.pi * 3.1 * t)
    audio = (
        0.18 * np.sin(2.0 * math.pi * 180.0 * t)
        + 0.09 * np.sin(2.0 * math.pi * 310.0 * t + 0.4)
        + 0.05 * np.sin(2.0 * math.pi * 620.0 * t + 1.1)
    )
    return np.asarray(envelope * audio, dtype=np.float32)


def _tile_seed(seed: np.ndarray, start_sample: int, sample_count: int) -> np.ndarray:
    positions = np.arange(start_sample, start_sample + sample_count, dtype=np.int64) % int(seed.size)
    return np.asarray(seed[positions], dtype=np.float32)


def _pink_noise_block(start_sample: int, sample_count: int) -> np.ndarray:
    # Deterministic test-only pink-ish noise; continuity is unnecessary for the
    # chunking regression, but seed by block start so generated WAVs are stable.
    rng = np.random.default_rng(384_000 + int(start_sample))
    white = rng.normal(0.0, 1.0, sample_count).astype(np.float32)
    brownish = np.cumsum(white, dtype=np.float32)
    peak = float(np.max(np.abs(brownish)) or 1.0)
    return np.asarray(0.18 * brownish / peak, dtype=np.float32)


def _block_for_pattern(
    speech_pattern: str,
    start_sample: int,
    sample_count: int,
    *,
    seed: np.ndarray | None,
    total_samples: int,
) -> np.ndarray:
    if speech_pattern == "tile":
        return _tile_seed(seed, start_sample, sample_count) if seed is not None else _speech_surrogate(start_sample, sample_count)

    if speech_pattern == "speech_then_silence":
        speech_samples = min(total_samples, int(round(_SPEECH_THEN_SILENCE_SPEECH_SEC * SAMPLE_RATE)))
        block = np.zeros(sample_count, dtype=np.float32)
        speech_count = max(0, min(sample_count, speech_samples - start_sample))
        if speech_count > 0:
            block[:speech_count] = _speech_surrogate(start_sample, speech_count)
        return block

    if speech_pattern == "hallucination_trigger":
        block = _tile_seed(seed, start_sample, sample_count) if seed is not None else _speech_surrogate(start_sample, sample_count)
        noise_start = int(round(_HALLUCINATION_TRIGGER_START_SEC * SAMPLE_RATE))
        noise_end = noise_start + int(round(_HALLUCINATION_TRIGGER_NOISE_SEC * SAMPLE_RATE))
        silence_end = noise_end + int(round(_HALLUCINATION_TRIGGER_SILENCE_SEC * SAMPLE_RATE))
        block_start = start_sample
        block_end = start_sample + sample_count
        overlap_start = max(block_start, noise_start)
        overlap_end = min(block_end, noise_end)
        if overlap_start < overlap_end:
            offset = overlap_start - block_start
            count = overlap_end - overlap_start
            block[offset : offset + count] = _pink_noise_block(overlap_start, count)
        silence_start = max(block_start, noise_end)
        silence_stop = min(block_end, silence_end)
        if silence_start < silence_stop:
            offset = silence_start - block_start
            block[offset : offset + (silence_stop - silence_start)] = 0.0
        return np.asarray(block, dtype=np.float32)

    raise ValueError(f"Unknown speech_pattern: {speech_pattern}")


def _ground_truth_intervals(duration_sec: float, speech_pattern: str) -> list[GroundTruthInterval]:
    if speech_pattern == "tile":
        return [{"start": 0.0, "end": float(duration_sec), "kind": "speech"}]
    if speech_pattern == "speech_then_silence":
        speech_end = min(float(duration_sec), _SPEECH_THEN_SILENCE_SPEECH_SEC)
        intervals: list[GroundTruthInterval] = [{"start": 0.0, "end": speech_end, "kind": "speech"}]
        if speech_end < float(duration_sec):
            intervals.append({"start": speech_end, "end": float(duration_sec), "kind": "silence"})
        return intervals
    if speech_pattern == "hallucination_trigger":
        trigger_start = min(float(duration_sec), _HALLUCINATION_TRIGGER_START_SEC)
        trigger_end = min(
            float(duration_sec),
            _HALLUCINATION_TRIGGER_START_SEC + _HALLUCINATION_TRIGGER_NOISE_SEC + _HALLUCINATION_TRIGGER_SILENCE_SEC,
        )
        intervals = []
        if trigger_start > 0.0:
            intervals.append({"start": 0.0, "end": trigger_start, "kind": "speech"})
        if trigger_end > trigger_start:
            intervals.append({"start": trigger_start, "end": trigger_end, "kind": "silence"})
        if trigger_end < float(duration_sec):
            intervals.append({"start": trigger_end, "end": float(duration_sec), "kind": "speech"})
        return intervals
    raise ValueError(f"Unknown speech_pattern: {speech_pattern}")


def build_synthetic_long_wav(
    duration_sec: float,
    speech_pattern: str = "tile",
    output_path: Path | None = None,
    seed_clip_path: Path | None = None,
) -> tuple[Path, list[GroundTruthInterval]]:
    """Build a deterministic 16 kHz mono WAV and return speech intervals.

    ``tile`` uses a discovered 16 kHz test WAV when one exists, otherwise a
    deterministic speech-frequency surrogate. Long files are streamed to disk so
    multi-hour fixtures do not materialize one giant NumPy array in memory.
    """
    duration = float(duration_sec)
    if duration <= 0.0:
        raise ValueError("duration_sec must be positive")
    if speech_pattern not in {"tile", "speech_then_silence", "hallucination_trigger"}:
        raise ValueError(f"Unknown speech_pattern: {speech_pattern}")

    wav_path = Path(output_path) if output_path is not None else _default_output_path()
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(round(duration * SAMPLE_RATE))
    block_samples = max(1, int(round(_BLOCK_SECONDS * SAMPLE_RATE)))
    seed = _candidate_seed_clip(seed_clip_path)

    with sf.SoundFile(str(wav_path), mode="w", samplerate=SAMPLE_RATE, channels=1, subtype="PCM_16") as wav_file:
        for start_sample in range(0, total_samples, block_samples):
            sample_count = min(block_samples, total_samples - start_sample)
            wav_file.write(
                _block_for_pattern(
                    speech_pattern,
                    start_sample,
                    sample_count,
                    seed=seed,
                    total_samples=total_samples,
                )
            )

    return wav_path, _ground_truth_intervals(duration, speech_pattern)
