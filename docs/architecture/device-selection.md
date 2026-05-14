# Device selection (CPU/GPU)

PARSE can run STT, ORTH, and IPA on CPU or CUDA GPU depending on your machine and configuration. You usually do not need to tune this on a working GPU workstation, but it is useful to know where to look when a long run is slow or unstable.

## Short answer

| Situation | Recommended choice |
|---|---|
| CUDA works and the machine is stable | Leave devices on `auto`. |
| GPU runs crash or OOM repeatedly | Try smaller chunks first; then force the unstable stage to CPU. |
| You need the safest fallback | Set `PARSE_COMPUTE_DEVICE=cpu`. |
| STT competes with ORTH/IPA for GPU memory | Set `PARSE_STT_DEVICE=cpu` and leave ORTH/IPA on `auto`. |
| IPA stays CPU unexpectedly | Check `wav2vec2.allow_wsl_cuda` and `PARSE_IPA_DEVICE`. |

## How PARSE chooses a device

For each stage, PARSE checks:

1. Stage-specific env var: `PARSE_STT_DEVICE`, `PARSE_ORTH_DEVICE`, or `PARSE_IPA_DEVICE`.
2. Global env var: `PARSE_COMPUTE_DEVICE`.
3. Stage config in `config/ai_config.json`.
4. Code default, usually `auto`.

Accepted values are `auto`, `cpu`, `cuda`, and `cuda:N`.

## Practical examples

Use the default when things are healthy:

```bash
./scripts/parse-run.sh
```

Force all stages to CPU for stability:

```bash
PARSE_COMPUTE_DEVICE=cpu ./scripts/parse-run.sh
```

Keep STT on CPU but allow ORTH/IPA to use automatic placement:

```bash
PARSE_STT_DEVICE=cpu PARSE_ORTH_DEVICE=auto PARSE_IPA_DEVICE=auto ./scripts/parse-run.sh
```

## What to check in reports

Terminal stage results can report `device`. Use it as a sanity check:

- If you expected CUDA but see `cpu`, inspect env vars and `ai_config.json`.
- If you forced CPU and see CUDA, check whether a stage-specific env var overrides your global choice.
- If IPA ignores CUDA, check whether `wav2vec2.allow_wsl_cuda=false` is present.

## Fieldwork guidance

A slow CPU run is often better than a repeated failed GPU run. For thesis-scale long recordings, start with stable defaults, then change one thing at a time: chunk size, then per-stage device, then global CPU fallback if needed.

Related: [Environment variables](../reference/environment-variables.md), [Configuration options](../reference/configuration.md), [Processing long recordings](../user-guides/processing-long-recordings.md), and [Compute architecture](compute.md).
