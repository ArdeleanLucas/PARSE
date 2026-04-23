"""Regression guard for Tier 3's soundfile-based audio loader.

PARSE used to call ``torchaudio.load`` inside ``_load_audio_mono_16k``.
torchaudio 2.5+ defaults to ``load_with_torchcodec`` which raises
``"TorchCodec is required for load_with_torchcodec"`` when torchcodec
isn't installed — that silently killed the Tier 3 Fail02 run on the
kurdish_asr env. The loader now uses ``soundfile`` as the primary
decoder (already a PARSE dependency via stt_pipeline). These tests
stub ``soundfile`` + ``torch`` so they run without either installed
locally.
"""
from __future__ import annotations

import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai import forced_align as fa


# ---------------------------------------------------------------------------
# Minimal torch stub — only what _load_audio_mono_16k touches
# ---------------------------------------------------------------------------


class _FakeTensor:
    """Records transformation history so tests can assert on ops."""

    def __init__(self, data, shape=None, dtype="float32", history=None):
        self._data = data
        self.shape = shape if shape is not None else getattr(data, "shape", (0,))
        self.dtype = dtype
        self.ndim = len(self.shape)
        self.history = list(history or [])

    def mean(self, dim=None, keepdim=False):
        new_shape = list(self.shape)
        new_shape[dim] = 1
        return _FakeTensor(
            None,
            shape=tuple(new_shape),
            history=self.history + [("mean", dim, keepdim)],
        )

    def squeeze(self, dim):
        new_shape = list(self.shape)
        if dim < len(new_shape) and new_shape[dim] == 1:
            new_shape.pop(dim)
        return _FakeTensor(
            None,
            shape=tuple(new_shape),
            history=self.history + [("squeeze", dim)],
        )

    def unsqueeze(self, dim):
        new_shape = list(self.shape)
        new_shape.insert(dim, 1)
        return _FakeTensor(
            None,
            shape=tuple(new_shape),
            history=self.history + [("unsqueeze", dim)],
        )

    def contiguous(self):
        return _FakeTensor(
            self._data, shape=self.shape, history=self.history + [("contiguous",)]
        )

    def to(self, dtype):
        return _FakeTensor(
            self._data, shape=self.shape, dtype=str(dtype), history=self.history + [("to", str(dtype))]
        )


def _install_torch_stub(monkeypatch, resample_raises=False):
    """Install a torch module that supports the ops _load_audio_mono_16k needs."""
    torch_mod = types.ModuleType("torch")
    torch_mod.float32 = "float32"

    def _from_numpy(arr):
        # numpy (samples, channels) transposed → (channels, samples)
        shape = getattr(arr, "shape", (0,))
        return _FakeTensor(arr, shape=shape)

    torch_mod.from_numpy = _from_numpy

    # torchaudio.functional.resample — optional path
    if not resample_raises:
        ta_mod = types.ModuleType("torchaudio")
        ta_fn = types.ModuleType("torchaudio.functional")

        def _resample(waveform, sr_in, sr_out):
            # Produce a tensor whose last-axis length matches the expected
            # resampled count (ratio-scaled). Keep shape otherwise.
            old_shape = list(getattr(waveform, "shape", (1, 0)))
            if not old_shape:
                old_shape = [0]
            old_len = int(old_shape[-1]) if old_shape[-1] else 0
            new_len = max(1, int(round(old_len * sr_out / float(sr_in))))
            new_shape = old_shape[:-1] + [new_len]
            return _FakeTensor(None, shape=tuple(new_shape), history=(getattr(waveform, "history", []) or []) + [("resample", sr_in, sr_out, new_len)])

        ta_fn.resample = _resample
        ta_mod.functional = ta_fn
        monkeypatch.setitem(sys.modules, "torchaudio", ta_mod)
        monkeypatch.setitem(sys.modules, "torchaudio.functional", ta_fn)
    else:
        # Make torchaudio import succeed but .functional.resample blow up,
        # so the fallback linear-interp path is exercised.
        ta_mod = types.ModuleType("torchaudio")
        ta_fn = types.ModuleType("torchaudio.functional")

        def _broken(*args, **kwargs):
            raise RuntimeError("TorchCodec is required for resample")

        ta_fn.resample = _broken
        ta_mod.functional = ta_fn
        monkeypatch.setitem(sys.modules, "torchaudio", ta_mod)
        monkeypatch.setitem(sys.modules, "torchaudio.functional", ta_fn)

    # torch.nn.functional.interpolate — fallback resampler path
    nn_mod = types.ModuleType("torch.nn")
    nn_fn = types.ModuleType("torch.nn.functional")

    def _interpolate(tensor, size, mode, align_corners=False):
        old_shape = list(getattr(tensor, "shape", (1, 1, 0)))
        new_shape = old_shape[:-1] + [size]
        return _FakeTensor(None, shape=tuple(new_shape), history=getattr(tensor, "history", []) + [("interpolate", size, mode)])

    nn_fn.interpolate = _interpolate
    nn_mod.functional = nn_fn
    torch_mod.nn = nn_mod

    monkeypatch.setitem(sys.modules, "torch", torch_mod)
    monkeypatch.setitem(sys.modules, "torch.nn", nn_mod)
    monkeypatch.setitem(sys.modules, "torch.nn.functional", nn_fn)


def _install_soundfile_stub(monkeypatch, *, sample_rate=16000, channels=1, num_samples=16000):
    """Stub soundfile.read → (ndarray(num_samples, channels), sample_rate)."""
    sf_mod = types.ModuleType("soundfile")
    calls = []

    class _FakeNDArray:
        def __init__(self, shape):
            self.shape = shape

        @property
        def T(self):
            return _FakeNDArray((self.shape[1], self.shape[0]))

    def _read(path, dtype=None, always_2d=False):
        calls.append({"path": path, "dtype": dtype, "always_2d": always_2d})
        shape = (num_samples, channels) if always_2d else (num_samples,)
        return _FakeNDArray(shape), sample_rate

    sf_mod.read = _read
    sf_mod._calls = calls
    monkeypatch.setitem(sys.modules, "soundfile", sf_mod)
    return calls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_loads_mono_16k_without_resample(monkeypatch, tmp_path):
    _install_torch_stub(monkeypatch)
    calls = _install_soundfile_stub(monkeypatch, sample_rate=16000, channels=1, num_samples=32000)

    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"")
    out = fa._load_audio_mono_16k(wav)

    assert len(calls) == 1
    assert calls[0]["dtype"] == "float32"
    assert calls[0]["always_2d"] is True
    # soundfile returns (32000, 1) → torch.from_numpy(arr.T) = (1, 32000) → squeeze(0) → (32000,)
    assert out.shape == (32000,)
    # No resample step in the history (sr already matches).
    assert not any(step[0] == "resample" for step in out.history)


def test_downmixes_stereo_to_mono(monkeypatch, tmp_path):
    _install_torch_stub(monkeypatch)
    _install_soundfile_stub(monkeypatch, sample_rate=16000, channels=2, num_samples=16000)

    wav = tmp_path / "stereo.wav"
    wav.write_bytes(b"")
    out = fa._load_audio_mono_16k(wav)

    # Mean-across-channels was called on the (2, 16000) tensor.
    assert any(step[0] == "mean" and step[1] == 0 for step in out.history)


def test_resamples_44100_to_16000_via_torchaudio(monkeypatch, tmp_path):
    _install_torch_stub(monkeypatch)
    _install_soundfile_stub(monkeypatch, sample_rate=44100, channels=1, num_samples=44100)

    wav = tmp_path / "hi.wav"
    wav.write_bytes(b"")
    out = fa._load_audio_mono_16k(wav)

    resample_steps = [s for s in out.history if s[0] == "resample"]
    assert len(resample_steps) == 1
    assert resample_steps[0][1:3] == (44100, 16000)
    # 1s of 44.1k resampled to 16k should be ~16000 samples.
    assert out.shape[-1] == 16000


def test_resample_fallback_uses_interpolate_when_torchaudio_broken(monkeypatch, tmp_path):
    _install_torch_stub(monkeypatch, resample_raises=True)
    _install_soundfile_stub(monkeypatch, sample_rate=44100, channels=1, num_samples=44100)

    wav = tmp_path / "hi.wav"
    wav.write_bytes(b"")
    out = fa._load_audio_mono_16k(wav)

    interp_steps = [s for s in out.history if s[0] == "interpolate"]
    assert len(interp_steps) == 1
    assert interp_steps[0][1] == 16000  # 1s * 16 kHz
    # And the torchaudio resample attempt is not in history (it raised).
    assert not any(s[0] == "resample" for s in out.history)


def test_missing_soundfile_raises_helpful_error(monkeypatch, tmp_path):
    _install_torch_stub(monkeypatch)
    # Deliberately remove soundfile from sys.modules and import cache.
    monkeypatch.setitem(sys.modules, "soundfile", None)

    wav = tmp_path / "x.wav"
    wav.write_bytes(b"")
    with pytest.raises(RuntimeError, match="soundfile"):
        fa._load_audio_mono_16k(wav)
