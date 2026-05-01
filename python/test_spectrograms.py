"""Tests for python/spectrograms.py — Praat-style DSP and cache versioning."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from spectrograms import (
    CACHE_VERSION,
    DEFAULT_DYNAMIC_RANGE_DB,
    DEFAULT_MAX_FREQ,
    DEFAULT_PRE_EMPHASIS_HZ,
    DEFAULT_WINDOW_LENGTH_SEC,
    _compute_spectrogram,
    _gaussian_window,
    _pre_emphasize,
    cache_path,
)


def test_default_constants_match_praat():
    assert DEFAULT_WINDOW_LENGTH_SEC == 0.005
    assert DEFAULT_MAX_FREQ == 5500.0
    assert DEFAULT_DYNAMIC_RANGE_DB == 50.0
    assert DEFAULT_PRE_EMPHASIS_HZ == 50.0


def test_cache_path_contains_version_segment(tmp_path: Path):
    path = cache_path(tmp_path, "Saha01", 1.0, 2.0)
    assert CACHE_VERSION in path.parts
    expected = tmp_path / "spectrograms" / CACHE_VERSION / "Saha01" / "1000_2000.png"
    assert path == expected


def test_cache_path_strips_unsafe_speaker_chars(tmp_path: Path):
    path = cache_path(tmp_path, "name with/slash & space", 0.0, 0.5)
    assert "namewithslashspace" in path.parts


def test_gaussian_window_peaks_at_center_and_decays_at_edges():
    w = _gaussian_window(513)
    assert math.isclose(float(w[(513 - 1) // 2]), 1.0, abs_tol=1e-6)
    assert float(w[0]) < 0.06
    assert float(w[-1]) < 0.06
    assert float(w[0]) > 0.0


def test_gaussian_window_handles_tiny_lengths():
    assert _gaussian_window(1).shape == (1,)
    assert float(_gaussian_window(1)[0]) == 1.0


def test_pre_emphasize_matches_alpha_formula():
    sample_rate = 44100
    cutoff = 50.0
    expected_alpha = math.exp(-2.0 * math.pi * cutoff / sample_rate)
    assert math.isclose(expected_alpha, 0.99287, abs_tol=1e-4)

    x = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    y = _pre_emphasize(x, sample_rate, cutoff)
    assert math.isclose(float(y[0]), 1.0, abs_tol=1e-6)
    assert math.isclose(float(y[1]), 2.0 - expected_alpha * 1.0, abs_tol=1e-5)
    assert math.isclose(float(y[2]), 3.0 - expected_alpha * 2.0, abs_tol=1e-5)
    assert math.isclose(float(y[3]), 4.0 - expected_alpha * 3.0, abs_tol=1e-5)


def test_pre_emphasize_passthrough_when_cutoff_zero_or_negative():
    x = np.array([0.5, -0.5, 0.5], dtype=np.float32)
    assert _pre_emphasize(x, 44100, 0.0) is x
    assert _pre_emphasize(x, 44100, -10.0) is x


def test_compute_spectrogram_returns_normalized_floats_in_unit_range():
    sample_rate = 22050
    duration = 0.4
    n = int(sample_rate * duration)
    t = np.arange(n, dtype=np.float32) / sample_rate
    samples = np.sin(2 * np.pi * 440 * t).astype(np.float32)

    spec = _compute_spectrogram(
        samples,
        sample_rate,
        window_length_sec=DEFAULT_WINDOW_LENGTH_SEC,
        overlap=0.875,
        max_freq=DEFAULT_MAX_FREQ,
        dynamic_range_db=DEFAULT_DYNAMIC_RANGE_DB,
        pre_emphasis_hz=DEFAULT_PRE_EMPHASIS_HZ,
    )
    assert spec.dtype == np.float32
    assert spec.ndim == 2
    assert float(spec.min()) >= 0.0
    assert float(spec.max()) <= 1.0
    assert float(spec.max()) > 0.5  # at least one bin near peak


def test_compute_spectrogram_concentrates_energy_near_440_hz():
    sample_rate = 22050
    duration = 0.3
    n = int(sample_rate * duration)
    t = np.arange(n, dtype=np.float32) / sample_rate
    samples = np.sin(2 * np.pi * 440 * t).astype(np.float32)

    spec = _compute_spectrogram(
        samples,
        sample_rate,
        window_length_sec=DEFAULT_WINDOW_LENGTH_SEC,
        overlap=0.875,
        max_freq=DEFAULT_MAX_FREQ,
        dynamic_range_db=DEFAULT_DYNAMIC_RANGE_DB,
        pre_emphasis_hz=0.0,  # disable pre-emphasis to make the peak crisp
    )
    middle = spec[:, spec.shape[1] // 2]
    peak_bin_in_clipped_array = int(np.argmax(middle))
    # spec was clipped to max_freq; bin spacing is sample_rate / fft_size
    win_len = max(8, int(round(DEFAULT_WINDOW_LENGTH_SEC * sample_rate)))
    fft_size = 1
    while fft_size < win_len:
        fft_size <<= 1
    expected_full_bin = round(440 * fft_size / sample_rate)
    assert abs(peak_bin_in_clipped_array - expected_full_bin) <= 2


def test_compute_spectrogram_empty_samples_returns_minimal_array():
    spec = _compute_spectrogram(
        np.zeros(0, dtype=np.float32),
        22050,
        window_length_sec=DEFAULT_WINDOW_LENGTH_SEC,
        overlap=0.875,
        max_freq=DEFAULT_MAX_FREQ,
        dynamic_range_db=DEFAULT_DYNAMIC_RANGE_DB,
        pre_emphasis_hz=DEFAULT_PRE_EMPHASIS_HZ,
    )
    assert spec.shape == (1, 1)
