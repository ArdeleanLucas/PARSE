# Device selection (CPU/GPU)

PARSE resolves STT, ORTH, and IPA device placement through one shared model so local operators can make predictable CPU/GPU choices.

## Resolution order
For each stage, PARSE checks:

1. Stage-specific env var: `PARSE_STT_DEVICE`, `PARSE_ORTH_DEVICE`, or `PARSE_IPA_DEVICE`.
2. Global env var: `PARSE_COMPUTE_DEVICE`.
3. Stage config in `config/ai_config.json`.
4. Code default, usually `auto`.

Accepted values are `auto`, `cpu`, `cuda`, and `cuda:N`.

## Practical guidance
- Use `auto` for normal GPU workstations.
- Use `PARSE_COMPUTE_DEVICE=cpu` for stable CPU fallback across all stages.
- Use stage-specific overrides when one model stack is unstable but others can stay on CUDA.
- `PARSE_STT_FORCE_CPU=1` still works as a legacy STT-only alias, but new launch notes should prefer `PARSE_STT_DEVICE=cpu`.

## IPA compatibility note
If `wav2vec2.allow_wsl_cuda=false` is present in `config/ai_config.json`, IPA stays CPU before the shared resolver is consulted. Remove it or set it true only when the local CUDA stack is known-good.

Related: [Environment variables](../reference/environment-variables.md), [Configuration options](../reference/configuration.md), and [Compute architecture](compute.md).
