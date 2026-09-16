---
name: cuda-inference-serialization
description: >
  Fix silent CUDA deadlock when multiple Python threads each load their own GPU
  model instance (WhisperModel, wav2vec2, etc.) and run inference concurrently.
  Use a module-level threading.Lock() to serialise all CUDA inference.
tags: [cuda, gpu, threading, whisper, faster-whisper, server, python, deadlock]
---

# CUDA Inference Serialization

## Problem

In a Python HTTP server running inference jobs as background threads, if multiple
threads each load their own `WhisperModel` (or any CUDA model) and call inference
simultaneously, they silently hang — no error, no timeout, no progress. The GPU
is shared but CUDA contexts are not thread-safe for concurrent inference from
separate model instances in the same process.

**Diagnostic signature:**
- N× `"Transcribing with VAD..."` in stderr logs
- 0× completions, completions, or error messages
- All jobs stuck at the same progress percentage indefinitely
- GPU utilisation looks idle despite jobs "running"

This happens with: `faster-whisper`, `wav2vec2`, `whisper.cpp`, `transformers`
pipeline objects — anything that owns a CUDA context internally.

---

## Fix: Module-level inference lock

Add a single `threading.Lock()` at the top of your server module and wrap
**every** CUDA inference call site with it:

```python
import threading

# One lock for the entire process — all CUDA inference serialised through this
_cuda_inference_lock = threading.Lock()
```

Then at each inference call site:

```python
# STT job
def _run_stt_job(job_id, ...):
    provider = get_stt_provider()        # load model (fast, outside lock)
    set_progress(job_id, 2.0, "Waiting for GPU")
    with _cuda_inference_lock:           # acquire before inference
        segments = provider.transcribe(audio_path, ...)
    # release happens automatically on exit

# Pipeline job
def _run_pipeline_job(job_id, ...):
    ...
    set_progress(job_id, 20.0, "Waiting for GPU")
    with _cuda_inference_lock:
        set_progress(job_id, 21.0, "Running pipeline")
        results = run_full_pipeline(audio_path, ...)
```

**Key rules:**
- Load the model OUTSIDE the lock (model loading is usually safe; inference isn't)
- Use a single shared lock for ALL inference, even different model types
- Jobs queue naturally — second job waits at "Waiting for GPU" until first finishes
- The lock is fair (FIFO ordering in CPython's threading.Lock)

---

## Status messages to surface queueing

Update progress messages so users know a job is queued vs. running:

```python
# Before acquiring lock:
set_progress(job_id, N, "Waiting for GPU (serialised)")

# After acquiring lock, before inference:
set_progress(job_id, N+1, "Running inference")
```

---

## Why not a model singleton?

A shared singleton also works but adds complexity (thread-safe lazy init, cache
invalidation on config change). The lock approach is simpler and safer for a
server where jobs are infrequent and throughput matters less than correctness.

If throughput is critical (many concurrent requests), consider a dedicated
inference process/service (TorchServe, Triton) instead.

---

## Pitfalls

- **Model loading vs inference** — `WhisperModel(path, device='cuda')` itself can
  be done outside the lock (it just allocates memory). The `.transcribe()` call
  is what needs serialisation.
- **Multiple lock types** — Do NOT use separate locks per model type (one for
  Whisper, one for wav2vec2). They share the same CUDA device and will still
  deadlock if both hold their own lock simultaneously.
- **False-positive completion** — If your pipeline function internally catches
  inference exceptions and returns empty results (e.g. `return {}`), the calling
  job runner may mark the job `complete` even on GPU failure. Always check result
  emptiness and propagate errors explicitly.
- **torch.cuda.is_available() is not a liveness check** — It returns True even
  when a specific DLL (e.g. `cublas64_12.dll`) is missing. The actual crash
  happens at inference time, not at availability check time.
- **`cublas64_12.dll` not found on Windows (Python 3.8+)** — Even when the DLL
  exists inside `site-packages/ctranslate2/`, Python 3.8+ Windows does NOT add
  that directory to the `LoadLibrary` DLL search path automatically. Fix: add
  `os.add_dll_directory()` at the very top of your entry-point script, BEFORE
  any imports:

  ```python
  import sys as _sys_pre
  if _sys_pre.platform == "win32":
      import os as _os_pre, site as _site_pre
      for _sp in _site_pre.getsitepackages():
          for _sub in ("ctranslate2", "torch/lib"):
              _d = _os_pre.path.join(_sp, _sub)
              if _os_pre.path.isdir(_d):
                  try:
                      _os_pre.add_dll_directory(_d)
                  except (OSError, ValueError):
                      pass
      del _sys_pre, _os_pre, _site_pre, _sp, _sub, _d
  else:
      del _sys_pre
  ```

  Add this to EVERY file that can be the process entry point (server.py,
  stt_pipeline.py, mcp_adapter.py, etc.) — not just the main server, because
  standalone scripts spawn as fresh processes with no inherited DLL dirs.

  **Diagnosis:** `ctranslate2.get_cuda_device_count()` returns 1 (imports fine)
  but `WhisperModel(...).transcribe()` raises
  `Library cublas64_12.dll is not found or cannot be loaded`.
  The count check uses CUDA runtime only; cuBLAS is loaded lazily at inference.

---

## Verification

After applying the lock, run two concurrent jobs and check that:
1. Job 1 starts immediately, acquires lock, progresses
2. Job 2 shows "Waiting for GPU" until Job 1 completes
3. Job 2 then runs to completion
4. No deadlock, no silent hang
