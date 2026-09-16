---
name: torchaudio-windows-dll-fix
description: >
  Fix torchaudio import failure on Windows when torch and torchaudio nightly builds
  have mismatched ABI versions (WinError 127 / OSError on _torchaudio.pyd). Applies
  a scipy fallback for torchaudio.functional.resample so the pipeline runs without
  a working torchaudio install. Use when torch is a dev/nightly build and torchaudio
  raises OSError on import.
tags: [torch, torchaudio, windows, conda, scipy, resample, dll, abi]
---

## Problem

On Windows with a conda env containing a **nightly/dev torch build**, `import torchaudio`
raises `OSError: Could not load this library: _torchaudio.pyd` (WinError 127 —
"specified procedure could not be found"). This happens because:

- torch nightly and torchaudio nightly must be built from the **same date/commit**
- Installing from PyPI or a different-date nightly wheel causes C++ ABI mismatch
- `_torchaudio.pyd` tries to call a symbol that no longer exists in that torch's DLLs

**Critical pitfall**: existing code guards with `except ImportError` — but `_torchaudio.pyd`
raises `OSError`, NOT `ImportError`. The guard silently fails to catch the crash.

---

## Diagnosis Steps

1. Check torch version:
   ```bash
   python.exe -c "import torch; print(torch.__version__)"
   # e.g. 2.10.0.dev20251021+cu130  ← dev/nightly flag
   ```

2. Try matching nightly torchaudio (same date, same CUDA):
   ```bash
   python.exe -m pip install torchaudio --pre \
     --index-url https://download.pytorch.org/whl/nightly/cu130
   python.exe -c "import torchaudio; print(torchaudio.__version__)"
   ```

3. If still failing with OSError, the nightly dates are too far apart — apply the
   scipy fallback instead (see below).

---

## Fix: Widen Import Guard + scipy Fallback

### Step 1 — Fix the import guard (catches OSError)

Replace every `except ImportError` that guards a `torchaudio` import:

```python
# BEFORE (broken — OSError not caught)
try:
    import torch
    import torchaudio
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

# AFTER (correct)
try:
    import torch
    import torchaudio
    _HAS_TORCH = True
    _HAS_TORCHAUDIO = True
except (ImportError, OSError):
    try:
        import torch
        _HAS_TORCH = True
    except (ImportError, OSError):
        _HAS_TORCH = False
    _HAS_TORCHAUDIO = False
```

### Step 2 — Add a resample helper with scipy fallback

Add this function after the import block. It's the only torchaudio function most
audio ML pipelines use:

```python
def _resample_audio(tensor, orig_sr: int, target_sr: int):
    """Resample a (C, T) or (T,) float32 torch tensor.
    Uses torchaudio.functional.resample when available, scipy otherwise."""
    if _HAS_TORCHAUDIO:
        return torchaudio.functional.resample(tensor, orig_sr, target_sr)
    # scipy fallback — always available in standard conda ML envs
    import scipy.signal
    data = tensor.numpy() if hasattr(tensor, "numpy") else tensor
    resampled = scipy.signal.resample_poly(data, target_sr, orig_sr, axis=-1)
    import torch as _torch
    return _torch.tensor(resampled, dtype=_torch.float32)
```

### Step 3 — Replace all `torchaudio.functional.resample` call sites

```python
# BEFORE
data_t = torchaudio.functional.resample(data_t, orig_sr, 16000)

# AFTER
data_t = _resample_audio(data_t, orig_sr, 16000)
```

---

## Verify the Fix

```bash
python.exe -c "
import sys; sys.path.insert(0, 'python')
import stt_pipeline
print('HAS_TORCH:', stt_pipeline._HAS_TORCH)
print('HAS_TORCHAUDIO:', stt_pipeline._HAS_TORCHAUDIO)
print('OK')
"
# Expected: HAS_TORCH: True | HAS_TORCHAUDIO: False | OK
# (False is correct — scipy fallback is active)
```

---

## PARSE-Specific Files

In `parse_v2`, this fix applies to:
- `python/ai/stt_pipeline.py` — two `torchaudio.functional.resample` call sites
- `python/ai/provider.py` — one call site in `Wav2Vec2IPAProvider.transcribe_window()`

---

## Why Not Just Upgrade torch?

torch `2.10.0.dev20251021+cu130` is pinned because:
- It's already installed with the CUDA 13 / Python 3.12 env (`kurdish_asr`)
- Upgrading risks breaking faster-whisper, transformers, and other deps
- The scipy fallback has identical output quality for 16 kHz resampling

---

## Notes

- `scipy.signal.resample_poly` is equivalent quality to `torchaudio.functional.resample`
  for standard audio resampling (both use polyphase filtering)
- Check scipy is available: `python.exe -c "import scipy; print(scipy.__version__)"`
- This approach makes the pipeline fully functional with `_HAS_TORCHAUDIO = False`
