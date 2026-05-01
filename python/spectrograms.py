"""On-demand spectrogram PNG generator with per-clip file cache.

Given a speaker + time window, renders a grayscale STFT spectrogram PNG and
caches it at ``spectrograms/v2/<speaker>/<start_ms>_<end_ms>.png`` so that
both the Annotate and Compare views load the same file for the same clip.

DSP defaults match Praat (and the front-end ``spectrogram-worker.ts``):
Gaussian window, ~0.005 s wideband length, +6 dB/oct pre-emphasis above
50 Hz, 50 dB dynamic range, max frequency 5500 Hz, dark-on-white render.

Cache path is versioned (``v2``) so PNGs cached under the previous Hann +
percentile-clip pipeline are not served stale after deploy.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf


CACHE_VERSION = "v2"

DEFAULT_WINDOW_LENGTH_SEC = 0.005
DEFAULT_OVERLAP = 0.875
DEFAULT_MAX_FREQ = 5500.0
DEFAULT_DYNAMIC_RANGE_DB = 50.0
DEFAULT_PRE_EMPHASIS_HZ = 50.0
DEFAULT_IMAGE_HEIGHT = 256


def _load_segment(audio_path: Path, start_sec: float, end_sec: float) -> Tuple[np.ndarray, int]:
    """Read [start_sec, end_sec] from audio_path as mono float32."""
    with sf.SoundFile(str(audio_path), mode="r") as fh:
        sample_rate = fh.samplerate
        total_frames = len(fh)
        start_frame = max(0, int(round(start_sec * sample_rate)))
        end_frame = min(total_frames, int(round(end_sec * sample_rate)))
        if end_frame <= start_frame:
            return np.zeros(0, dtype=np.float32), sample_rate
        fh.seek(start_frame)
        data = fh.read(end_frame - start_frame, dtype="float32", always_2d=True)
    if data.ndim == 2 and data.shape[1] > 1:
        mono = data.mean(axis=1)
    else:
        mono = data[:, 0] if data.ndim == 2 else data
    return mono.astype(np.float32, copy=False), sample_rate


def _next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return p


def _gaussian_window(n_samples: int) -> np.ndarray:
    """Praat-style Gaussian: w[i] = exp(-12 (i - center)^2 / (N-1)^2).

    Edges decay to ~exp(-3) ≈ 0.05; matches ``spectrogram-worker.ts`` exactly.
    """
    if n_samples <= 1:
        return np.ones(max(1, n_samples), dtype=np.float32)
    center = (n_samples - 1) / 2.0
    denom = (n_samples - 1) ** 2
    indices = np.arange(n_samples, dtype=np.float64)
    return np.exp(-12.0 * (indices - center) ** 2 / denom).astype(np.float32)


def _pre_emphasize(samples: np.ndarray, sample_rate: int, cutoff_hz: float) -> np.ndarray:
    """1st-order IIR: y[n] = x[n] - alpha * x[n-1], alpha = exp(-2*pi*cutoff/SR)."""
    if cutoff_hz <= 0 or samples.size == 0:
        return samples
    alpha = float(np.exp(-2.0 * np.pi * cutoff_hz / float(sample_rate)))
    out = np.empty_like(samples)
    out[0] = samples[0]
    out[1:] = samples[1:] - alpha * samples[:-1]
    return out


def _compute_spectrogram(
    samples: np.ndarray,
    sample_rate: int,
    window_length_sec: float,
    overlap: float,
    max_freq: float,
    dynamic_range_db: float,
    pre_emphasis_hz: float,
) -> np.ndarray:
    """Compute a Praat-style STFT and map dB to [0, 1] via dB-cutoff.

    Returns a 2-D array of shape (freq_bins, time_frames), values in [0, 1]
    where 1.0 = loud (within ``dynamic_range_db`` of peak).
    """
    if samples.size == 0:
        return np.zeros((1, 1), dtype=np.float32)

    win_len = max(8, int(round(window_length_sec * sample_rate)))
    fft_size = _next_pow2(win_len)
    hop = max(1, int(round(win_len * (1.0 - overlap))))
    window = _gaussian_window(win_len)

    samples = _pre_emphasize(samples, sample_rate, pre_emphasis_hz)

    if samples.size < win_len:
        padded = np.zeros(win_len, dtype=np.float32)
        padded[: samples.size] = samples
        samples = padded

    num_frames = max(1, 1 + (samples.size - win_len) // hop)

    # rfft on (fft_size,) frames; spec is (fft_size//2+1, num_frames)
    spec_db = np.empty((fft_size // 2 + 1, num_frames), dtype=np.float32)
    for i in range(num_frames):
        offset = i * hop
        frame = samples[offset : offset + win_len]
        if frame.size < win_len:
            buf = np.zeros(win_len, dtype=np.float32)
            buf[: frame.size] = frame
            frame = buf
        windowed = frame * window
        spectrum = np.fft.rfft(windowed, n=fft_size)
        mag = np.abs(spectrum).astype(np.float32)
        spec_db[:, i] = 20.0 * np.log10(np.maximum(mag, 1e-10))

    nyquist = sample_rate / 2.0
    if nyquist > 0 and max_freq < nyquist:
        cutoff = int(round(spec_db.shape[0] * (max_freq / nyquist)))
        cutoff = max(1, min(spec_db.shape[0], cutoff))
        spec_db = spec_db[:cutoff, :]

    db_max = float(spec_db.max())
    db_floor = db_max - max(1.0, float(dynamic_range_db))
    range_db = max(1.0, float(dynamic_range_db))
    norm = np.clip((spec_db - db_floor) / range_db, 0.0, 1.0)
    return norm.astype(np.float32)


def _render_to_image(spec: np.ndarray, height: int) -> np.ndarray:
    """Flip + resize (freq_bins, frames) → (height, width) grayscale uint8.

    Higher frequencies on top, time flows left→right. Inverted so that loud
    regions render dark on a light background (Praat aesthetic).
    """
    if spec.size == 0:
        return np.full((height, 1), 255, dtype=np.uint8)

    spec = spec[::-1, :]
    freq_bins, frames = spec.shape

    if freq_bins == height:
        resized = spec
    else:
        src_idx = np.linspace(0, freq_bins - 1, height).astype(np.int32)
        resized = spec[src_idx, :]

    max_width = max(64, frames)
    if frames > max_width:
        dst_idx = np.linspace(0, frames - 1, max_width).astype(np.int32)
        resized = resized[:, dst_idx]

    inverted = 1.0 - resized
    return np.clip(inverted * 255.0, 0, 255).astype(np.uint8)


def _encode_png_grayscale(image: np.ndarray) -> bytes:
    """Encode a 2-D uint8 array as a grayscale PNG with zero external deps."""
    if image.ndim != 2:
        raise ValueError("image must be 2-D grayscale")
    height, width = image.shape

    def chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return length + tag + data + crc

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)

    raw = bytearray()
    for row in image:
        raw.append(0)
        raw.extend(row.tobytes())
    idat = zlib.compress(bytes(raw), level=6)

    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def cache_path(project_root: Path, speaker: str, start_sec: float, end_sec: float) -> Path:
    """Versioned cache path. Bumping ``CACHE_VERSION`` invalidates older PNGs."""
    start_ms = int(round(start_sec * 1000))
    end_ms = int(round(end_sec * 1000))
    safe_speaker = "".join(c for c in speaker if c.isalnum() or c in ("-", "_"))
    return project_root / "spectrograms" / CACHE_VERSION / safe_speaker / f"{start_ms}_{end_ms}.png"


def generate_spectrogram_png(
    audio_path: Path,
    start_sec: float,
    end_sec: float,
    cache_file: Path,
    *,
    window_length_sec: float = DEFAULT_WINDOW_LENGTH_SEC,
    overlap: float = DEFAULT_OVERLAP,
    max_freq: float = DEFAULT_MAX_FREQ,
    dynamic_range_db: float = DEFAULT_DYNAMIC_RANGE_DB,
    pre_emphasis_hz: float = DEFAULT_PRE_EMPHASIS_HZ,
    image_height: int = DEFAULT_IMAGE_HEIGHT,
    force: bool = False,
) -> Path:
    """Compute the spectrogram (or reuse cache) and return the PNG path."""
    if not force and cache_file.is_file() and cache_file.stat().st_size > 0:
        return cache_file

    samples, sample_rate = _load_segment(audio_path, max(0.0, start_sec), max(start_sec, end_sec))
    spec = _compute_spectrogram(
        samples,
        sample_rate,
        window_length_sec=window_length_sec,
        overlap=overlap,
        max_freq=max_freq,
        dynamic_range_db=dynamic_range_db,
        pre_emphasis_hz=pre_emphasis_hz,
    )
    image = _render_to_image(spec, image_height)
    png_bytes = _encode_png_grayscale(image)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(png_bytes)
    return cache_file
