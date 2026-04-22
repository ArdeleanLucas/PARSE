"""On-demand spectrogram PNG generator with per-clip file cache.

Given a speaker + time window, renders a grayscale STFT spectrogram PNG and
caches it at ``spectrograms/<speaker>/<start_ms>_<end_ms>.png`` so that both
the Annotate and Compare views load the same file for the same clip.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import soundfile as sf


DEFAULT_WINDOW_SIZE = 2048
DEFAULT_OVERLAP = 0.75
DEFAULT_MAX_FREQ = 8000.0
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


def _compute_spectrogram(
    samples: np.ndarray,
    sample_rate: int,
    window_size: int,
    overlap: float,
    max_freq: float,
) -> np.ndarray:
    """Compute a magnitude STFT and clip to ``max_freq`` Hz.

    Returns a 2-D array of shape (freq_bins, time_frames), values in [0, 1].
    """
    if samples.size == 0:
        return np.zeros((1, 1), dtype=np.float32)

    hop = max(1, int(window_size * (1.0 - overlap)))
    window = np.hanning(window_size).astype(np.float32)

    if samples.size < window_size:
        padded = np.zeros(window_size, dtype=np.float32)
        padded[: samples.size] = samples
        samples = padded

    num_frames = 1 + (samples.size - window_size) // hop
    if num_frames <= 0:
        num_frames = 1

    spec = np.zeros((window_size // 2 + 1, num_frames), dtype=np.float32)
    for i in range(num_frames):
        offset = i * hop
        frame = samples[offset : offset + window_size]
        if frame.size < window_size:
            buf = np.zeros(window_size, dtype=np.float32)
            buf[: frame.size] = frame
            frame = buf
        spectrum = np.fft.rfft(frame * window)
        spec[:, i] = np.abs(spectrum).astype(np.float32)

    nyquist = sample_rate / 2.0
    if nyquist > 0 and max_freq < nyquist:
        cutoff = int(round(spec.shape[0] * (max_freq / nyquist)))
        cutoff = max(1, min(spec.shape[0], cutoff))
        spec = spec[:cutoff, :]

    # Convert to dB and normalize to [0, 1].
    spec_db = 20.0 * np.log10(spec + 1e-6)
    lo = float(np.percentile(spec_db, 5))
    hi = float(np.percentile(spec_db, 99))
    if hi - lo < 1e-3:
        hi = lo + 1.0
    norm = np.clip((spec_db - lo) / (hi - lo), 0.0, 1.0)
    return norm.astype(np.float32)


def _render_to_image(spec: np.ndarray, height: int) -> np.ndarray:
    """Flip + resize (freq_bins, frames) → (height, width) grayscale uint8.

    Higher frequencies on top, time flows left→right. Values inverted so that
    loud regions render dark on a light background (matches Praat conventions).
    """
    if spec.size == 0:
        return np.full((height, 1), 255, dtype=np.uint8)

    # Flip freq axis so high frequencies sit at the top of the image.
    spec = spec[::-1, :]
    freq_bins, frames = spec.shape

    # Linearly resample frequency axis to `height` rows.
    if freq_bins == height:
        resized = spec
    else:
        src_idx = np.linspace(0, freq_bins - 1, height).astype(np.int32)
        resized = spec[src_idx, :]

    # Time axis: keep native frame count, but cap at a sensible max width.
    max_width = max(64, frames)
    if frames > max_width:
        dst_idx = np.linspace(0, frames - 1, max_width).astype(np.int32)
        resized = resized[:, dst_idx]

    # Invert so that high-energy (1.0) → dark (0), low energy → light (255).
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
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8-bit grayscale

    # Each scanline prefixed with filter byte 0 (None).
    raw = bytearray()
    for row in image:
        raw.append(0)
        raw.extend(row.tobytes())
    idat = zlib.compress(bytes(raw), level=6)

    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def cache_path(project_root: Path, speaker: str, start_sec: float, end_sec: float) -> Path:
    start_ms = int(round(start_sec * 1000))
    end_ms = int(round(end_sec * 1000))
    safe_speaker = "".join(c for c in speaker if c.isalnum() or c in ("-", "_"))
    return project_root / "spectrograms" / safe_speaker / f"{start_ms}_{end_ms}.png"


def generate_spectrogram_png(
    audio_path: Path,
    start_sec: float,
    end_sec: float,
    cache_file: Path,
    *,
    window_size: int = DEFAULT_WINDOW_SIZE,
    overlap: float = DEFAULT_OVERLAP,
    max_freq: float = DEFAULT_MAX_FREQ,
    image_height: int = DEFAULT_IMAGE_HEIGHT,
    force: bool = False,
) -> Path:
    """Compute the spectrogram (or reuse cache) and return the PNG path."""
    if not force and cache_file.is_file() and cache_file.stat().st_size > 0:
        return cache_file

    samples, sample_rate = _load_segment(audio_path, max(0.0, start_sec), max(start_sec, end_sec))
    spec = _compute_spectrogram(samples, sample_rate, window_size, overlap, max_freq)
    image = _render_to_image(spec, image_height)
    png_bytes = _encode_png_grayscale(image)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(png_bytes)
    return cache_file
