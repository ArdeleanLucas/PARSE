---
name: faster-whisper-gpu
description: Use Faster-Whisper on Lucas's RTX 5090 with explicit CUDA settings. Avoid Hermes local STT auto-selection pitfalls by forcing GPU + compute type explicitly.
version: 1.0.0
author: Marcus
---

# Faster-Whisper GPU

Use this when you want **local GPU transcription** on Lucas's machine instead of cloud STT or Hermes's generic auto path.

## When to use

- Transcribing Discord/Telegram voice notes locally
- Batch audio transcription on the RTX 5090
- Working around Hermes STT issues where local Faster-Whisper is selected but the wrong model/compute path gets used
- Needing deterministic local STT without API keys

## Verified environment on this machine

- GPU: `NVIDIA GeForce RTX 5090`
- Hermes repo: `/home/lucas/.hermes/hermes-agent`
- Hermes venv: `/home/lucas/.hermes/hermes-agent/venv`
- `faster-whisper==1.2.1`
- `ctranslate2==4.7.1`
- Verified cached model path:
  - `/home/lucas/.cache/ctranslate2/razhan-whisper-base-sdh-fp16`

## The important pitfall

Hermes's built-in local STT path currently uses:

```python
WhisperModel(model_name, device="auto", compute_type="auto")
```

That is unreliable on this machine for GPU use.

Also, `~/.hermes/config.yaml` currently has a conflicting STT setup:
- `stt.provider: local`
- `stt.local.model: base`
- but also top-level `stt.model: whisper-1`

That combination can send the wrong model string into local Faster-Whisper and break voice-note transcription.

## Verified working GPU settings

These worked locally on the cached voice note:
- `device="cuda", compute_type="float16"`
- `device="cuda", compute_type="float32"`

These failed with `CUBLAS_STATUS_NOT_SUPPORTED`:
- `device="cuda", compute_type="int8_float16"`
- `device="cuda", compute_type="int8_float32"`

**Default recommendation:** use `float16` on CUDA.

## Quick use

### 1) One-off transcription

```bash
cd /home/lucas/.hermes/hermes-agent
source venv/bin/activate
python ~/.hermes/skills/mlops-models/faster-whisper-gpu/scripts/transcribe_gpu.py \
  --input /path/to/audio.ogg
```

### 2) Force float32 on GPU if needed

```bash
cd /home/lucas/.hermes/hermes-agent
source venv/bin/activate
python ~/.hermes/skills/mlops-models/faster-whisper-gpu/scripts/transcribe_gpu.py \
  --input /path/to/audio.ogg \
  --compute-type float32
```

### 3) Write `.txt` output for automation

```bash
cd /home/lucas/.hermes/hermes-agent
source venv/bin/activate
python ~/.hermes/skills/mlops-models/faster-whisper-gpu/scripts/transcribe_gpu.py \
  --input /path/to/audio.ogg \
  --output-dir /tmp/fw-out
```

### 4) Emit structured JSON

```bash
cd /home/lucas/.hermes/hermes-agent
source venv/bin/activate
python ~/.hermes/skills/mlops-models/faster-whisper-gpu/scripts/transcribe_gpu.py \
  --input /path/to/audio.ogg \
  --json
```

## Integrating with Hermes voice-note transcription

If you want Hermes to use the GPU script instead of its built-in `device="auto"/compute_type="auto"` path, export a local command template before starting Hermes:

```bash
export HERMES_LOCAL_STT_COMMAND="bash -lc \"source /home/lucas/.hermes/hermes-agent/venv/bin/activate && python /home/lucas/.hermes/skills/mlops-models/faster-whisper-gpu/scripts/transcribe_gpu.py --input {input_path} --output-dir {output_dir} --language {language} --model {model}\""
```

Then Hermes local STT will use the script and read the generated `.txt` file from `{output_dir}`.

## What the helper script does

- Uses Faster-Whisper directly
- Forces `device=cuda`
- Defaults to `compute_type=float16`
- Maps `base` to the verified cached CTranslate2 model path when present
- Uses `beam_size=5` and `vad_filter=True`
- Prints transcript to stdout and optionally writes `.txt`/`.json`

## Windows: cublas64_12.dll not found at inference time

**Symptom:** `Library cublas64_12.dll is not found or cannot be loaded` when
`WhisperModel(...).transcribe()` is called — even though `ctranslate2` imported
without error and `get_cuda_device_count()` returned 1.

**Root cause:** Python 3.8+ Windows does not auto-add `site-packages`
subdirectories to the OS DLL search path. `ctranslate2` bundles its own copy of
`cublas64_12.dll` inside `site-packages/ctranslate2/`, but `LoadLibrary` can't
find it there.

**Location of bundled DLLs** (verified in `kurdish_asr` conda env):
```
site-packages/ctranslate2/  ← cublas64_12.dll, cublasLt64_12.dll, cudnn64_9.dll, ...
site-packages/torch/lib/    ← cublas64_13.dll (torch CUDA 13 builds)
```

**Fix:** Add `os.add_dll_directory()` at the very top of each Python entry-point
file, BEFORE any imports:

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

Apply to every file that can be a process entry point (server.py,
stt_pipeline.py, mcp_adapter.py). Each subprocess is a fresh process; DLL dirs
do not inherit.

**Verified working** on: Python 3.12, CT2 4.7.1, CUDA 13, RTX 5090,
`kurdish_asr` conda env at `C:\Users\Lucas\anaconda3\envs\kurdish_asr\`.

---

## Troubleshooting

### `CUBLAS_STATUS_NOT_SUPPORTED`
Use:

```bash
--compute-type float16
```

If that somehow still fails, try:

```bash
--compute-type float32
```

Do **not** use `int8_float16` or `int8_float32` on this machine unless you re-test them.

### Warning about `/sys/class/drm/card0/device/vendor`
You may still see an ONNX Runtime device-discovery warning under WSL. If transcription succeeds, ignore it.

### Model not found / wants to download
Use the verified local cached model path explicitly:

```bash
--model /home/lucas/.cache/ctranslate2/razhan-whisper-base-sdh-fp16
```

## Verification

A successful run should:
- return transcript text
- report language metadata
- avoid cloud/API usage entirely
- complete on GPU with `float16` or `float32`

## Files

- Helper script: `scripts/transcribe_gpu.py`
