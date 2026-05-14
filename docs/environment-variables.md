# Environment variables

> Last updated: 2026-05-14. This is the operator-facing reference for PARSE `PARSE_*` environment variables. Runtime model/provider defaults still live in `config/ai_config.json`; this page documents environment overrides that the launcher, backend, MCP adapter, and compute workers read.

## Precedence model

PARSE uses environment variables for machine-local runtime choices and `config/ai_config.json` for project/provider defaults.

Device placement has its own resolver in `python/ai/device.py`:

In short: stage-specific → global → config → default.

1. Stage-specific env var: `PARSE_STT_DEVICE`, `PARSE_ORTH_DEVICE`, or `PARSE_IPA_DEVICE`
2. Global env fallback: `PARSE_COMPUTE_DEVICE`
3. The matching `ai_config.json` section's `device` value (`stt.device`, `ortho.device`, `wav2vec2.device`)
4. Code default, usually `auto`

Accepted device values are `auto`, `cpu`, `cuda`, and `cuda:N`. `auto` resolves to CUDA only when PyTorch reports an available CUDA device; otherwise it resolves to CPU. Explicit CUDA requests fall back to CPU with a warning if CUDA is unavailable.

`PARSE_STT_FORCE_CPU` remains a backwards-compatible STT-only escape hatch. A truthy value (`1`, `true`, `yes`, `y`, `on`) is equivalent to `PARSE_STT_DEVICE=cpu` and also keeps faster-whisper on CPU/int8 fallback semantics.

IPA has one legacy compatibility gate: `wav2vec2.allow_wsl_cuda=false` in `config/ai_config.json` still forces wav2vec2/IPA to CPU before the unified resolver is consulted. When the key is omitted or true, `PARSE_IPA_DEVICE` / `PARSE_COMPUTE_DEVICE` / `wav2vec2.device` participate normally.

## Launcher and workspace variables

| Variable | Default | Purpose |
|---|---:|---|
| `PARSE_PY` | `python3` | Python interpreter used by `scripts/parse-run.sh`; may point at a Windows `python.exe` from WSL. |
| `PARSE_ROOT` | auto-detected repo root | Repository root for the launcher and backend. |
| `PARSE_WORKSPACE_ROOT` | `PARSE_ROOT` | Runtime workspace/data root. In fieldwork, point this outside the git checkout. |
| `PARSE_API_PORT` | `8766` | Python HTTP API port. |
| `PARSE_PORT` | fallback for API port in some proxy paths | Compatibility port fallback used by Vite/proxy tooling. Prefer `PARSE_API_PORT` for new setup. |
| `PARSE_VITE_PORT` | `5173` | Vite development server port. |
| `PARSE_WS_PORT` | `8767` | Optional WebSocket job-streaming sidecar port. |
| `PARSE_SKIP_PULL` | `0` | Skip launcher git update when set. |
| `PARSE_PULL_MODE` | `auto` | Launcher update strategy: `auto`, `ff`, `rebase`, or `reset`. |
| `PARSE_EXTERNAL_READ_ROOTS` | empty | Extra absolute roots that chat/MCP tools may read outside the workspace; use platform path separators or `*` to disable the sandbox. |
| `PARSE_CHAT_DOCS_ROOT` | `PARSE_WORKSPACE_ROOT` | Optional docs/text root for preview tooling. |
| `PARSE_CHAT_MEMORY_PATH` | `PARSE_WORKSPACE_ROOT/parse-memory.md` | Persistent local assistant memory file. |
| `PARSE_CHAT_READ_ONLY` | config-driven | `1` forces chat tools read-only; `0` forces write-enabled. |

## Compute launcher variables

| Variable | Default | Purpose |
|---|---:|---|
| `PARSE_COMPUTE_MODE` | `thread` in backend if unset | Outer compute launcher mode: `thread`, `subprocess`, or `persistent`. The launcher warns when unset because the backend keeps the legacy thread default. |
| `PARSE_USE_PERSISTENT_WORKER` | unset | Truthy shortcut that selects `persistent` worker mode. |
| `PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC` | `14400` | Timeout for outer per-job subprocess mode and nested isolated full-mode STT/ORTH/IPA subprocesses. Positive finite values are honored by the nested helper; invalid/zero/negative values fall back to 4 hours. |
| `PARSE_FULL_PIPELINE_MIN_MEM_GB` | backend default `12` | Host-memory preflight threshold before memory-heavy full-pipeline steps; low-memory failures surface `oom_suspect`. |
| `PARSE_JOB_SNAPSHOT_DIR` | workspace `.parse/jobs` | Durable job snapshots used to mark interrupted jobs as `server_restarted` after backend restart. |
| `PARSE_ACTIVE_JOBS_TERMINAL_DWELL_SEC` | `10` | Seconds `/api/jobs/active` keeps terminal complete/error/cancelled snapshots visible to the header strip; clamped to 0–120. |

## Long-file processing variables

| Variable | Default | Stage | Purpose |
|---|---:|---|---|
| `PARSE_STT_DEFAULT_CHUNK_MINUTES` | `10` | STT Tier 1 | Full-file STT splits recordings longer than this duration into adjacent chunks. `0` disables duration chunking; invalid values fall back to 10. |
| `PARSE_ORTH_DEFAULT_CHUNK_MINUTES` | `10` | ORTH Tier 1 | Full-mode ORTH splits recordings longer than this duration into adjacent chunks before Tier 2 forced alignment. `0` disables duration chunking; invalid values fall back to 10. |
| `PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC` | `60` | IPA overwrite guard | Emits `coverage_shrink_warning` when an overwrite would shrink existing IPA coverage by more than this threshold or by a severe count drop. `0` disables the warning. This is not an IPA audio-duration chunking knob. |

Chunking is intent-aware: full-file/full-pipeline STT and ORTH use the robust path; concept-window and edited-only reruns stay on bounded fast paths and do not use duration chunking. IPA is interval-driven and does not chunk by whole-audio duration.

## Device variables

| Variable | Default | Scope | Purpose |
|---|---:|---|---|
| `PARSE_COMPUTE_DEVICE` | `auto` | STT, ORTH, IPA | Global fallback device override. |
| `PARSE_STT_DEVICE` | unset | STT | Stage-specific STT device override; supersedes `PARSE_COMPUTE_DEVICE`. |
| `PARSE_ORTH_DEVICE` | unset | ORTH | Stage-specific ORTH device override; supersedes `PARSE_COMPUTE_DEVICE`. |
| `PARSE_IPA_DEVICE` | unset | IPA / wav2vec2 | Stage-specific IPA device override; supersedes `PARSE_COMPUTE_DEVICE` when `wav2vec2.allow_wsl_cuda` is not explicitly false. |
| `PARSE_STT_FORCE_CPU` | unset | STT | Legacy truthy alias for `PARSE_STT_DEVICE=cpu`; kept for emergency WSL/driver fallback scripts. |

## Common configurations

### Default robust local run

```bash
./scripts/parse-run.sh
```

With current defaults, full-file STT and ORTH chunk at 10 minutes, memory-heavy full-mode STT/ORTH/IPA stages are subprocess-isolated, and devices resolve automatically from env → config → CUDA availability.

### Force every compute stage to CPU

```bash
PARSE_COMPUTE_DEVICE=cpu ./scripts/parse-run.sh
```

Use this on unstable GPU stacks or machines without working CUDA. It is slower but predictable.

### Keep STT on CPU, allow ORTH/IPA to use CUDA

```bash
PARSE_STT_DEVICE=cpu PARSE_ORTH_DEVICE=auto PARSE_IPA_DEVICE=auto ./scripts/parse-run.sh
```

Equivalent legacy STT-only form:

```bash
PARSE_STT_FORCE_CPU=1 ./scripts/parse-run.sh
```

### Smaller chunks for a fragile long recording

```bash
PARSE_STT_DEFAULT_CHUNK_MINUTES=5 \
PARSE_ORTH_DEFAULT_CHUNK_MINUTES=5 \
./scripts/parse-run.sh
```

Smaller chunks reduce per-provider-call memory/decoder risk at the cost of more temp WAV slicing and more model-call overhead.

### Disable duration chunking for a controlled comparison

```bash
PARSE_STT_DEFAULT_CHUNK_MINUTES=0 \
PARSE_ORTH_DEFAULT_CHUNK_MINUTES=0 \
./scripts/parse-run.sh
```

Do this only when you explicitly want the old monolithic behavior for a controlled benchmark or bug isolation. It removes the robust long-file guard that protects fieldwork recordings.

## Related docs

- [Compute architecture](architecture/compute.md)
- [Worker process architecture](architecture/worker-processes.md)
- [MCP schema](mcp-schema.md#compute-job-result-shapes)
- [User guide: Processing long recordings](user-guide.md#processing-long-recordings)
