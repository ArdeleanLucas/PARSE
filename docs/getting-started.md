# Getting Started

> Last updated: 2026-04-24
>
> This guide reflects the current React + Vite frontend, the Python backend in `python/server.py`, and the launcher workflow documented in the latest `README.md` and tracked scripts.

PARSE is a browser-based dual-mode research workstation for linguistic fieldwork and cross-speaker comparison. The fastest path is the tracked launcher script, which starts the Python API and the Vite frontend together and prints the working URLs.

If you are new to the project, use this page in order:

1. Check [requirements](#requirements)
2. Run the [one-command launcher](#one-command-launch-recommended)
3. Configure [`ai_config.json`](#configure-aiconfigjson)
4. Review the [workspace-first setup](#workspace-first-bootstrap-recommended-on-a-fresh-machine)
5. Use the [troubleshooting](#troubleshooting) section if startup or GPU inference fails

## Requirements

### Runtime expectations

PARSE currently assumes:

- **WSL / Linux shell tooling** for the default launcher workflow
- **Node.js 18+** with `npm install` run once per clone
- **Python 3.10–3.12** for the backend stack
- A working Python environment with the PARSE dependencies installed
- For thesis-scale speech work, a **CUDA-capable GPU** is the intended path for local STT, ORTH, and wav2vec2-based alignment

### Recommended Python environment

The current PARSE launcher supports two common cases:

- **Linux/WSL-native Python** (`python3`)
- **Windows `python.exe` from WSL**, typically a conda environment such as:

```bash
/mnt/c/Users/Lucas/anaconda3/envs/kurdish_asr/python.exe
```

This second setup matters because some local speech/model stacks may already be installed in a Windows-side conda environment.

### Required repository-local setup

Clone the repository and install frontend dependencies once per clone:

```bash
git clone https://github.com/ArdeleanLucas/PARSE.git
cd PARSE
npm install
```

## One-command launch (recommended)

The tracked launcher script starts both servers, integrates the latest code, cleans up stale processes, checks API health, and prints the URLs you should open.

```bash
./scripts/parse-run.sh
```

On success, you should see output in this shape:

```text
[parse-run] ════════════════════════════════════════
[parse-run]   PARSE is running
[parse-run]   React UI:  http://localhost:5173/
[parse-run]   Compare:   http://localhost:5173/compare
[parse-run]   API:       http://localhost:8766/api/config
[parse-run] ════════════════════════════════════════
```

Open:

- **Annotate**: `http://localhost:5173/`
- **Compare**: `http://localhost:5173/compare`

### What `scripts/parse-run.sh` does

The launcher is more than a simple two-process wrapper. It currently:

1. Integrates the latest `origin/main` according to `PARSE_PULL_MODE` unless `PARSE_SKIP_PULL=1`
2. Kills stale Python and Vite processes on both WSL and Windows sides
3. Probes whether the API port is actually bindable before starting the backend
4. Starts the Python API server (`python/server.py`) on `:8766`
5. Waits for `/api/config` to return `200`
6. Starts the Vite dev server on `:5173`
7. Waits for Vite to respond, then prints the URLs

Two helper commands are also part of the expected workflow:

```bash
scripts/parse-stop.sh   # kill both servers
parse-logs api          # tail Python API stderr
parse-logs vite         # tail Vite dev server output
```

## Workspace-first bootstrap (recommended on a fresh machine)

For real fieldwork workspaces, PARSE is designed to keep generated runtime state outside the git checkout.

Use the workspace initializer once:

```bash
# Scaffold a standalone workspace once
scripts/parse-init-workspace.sh /path/to/parse-workspace

# Then launch PARSE against that workspace
PARSE_WORKSPACE_ROOT="/path/to/parse-workspace" \
  PARSE_CHAT_MEMORY_PATH="/path/to/parse-workspace/parse-memory.md" \
  PARSE_EXTERNAL_READ_ROOTS="/mnt/c/Users/Lucas/Thesis" \
  ./scripts/parse-run.sh
```

This keeps original source WAV/CSV files untouched and lets PARSE copy selected files into the workspace instead of mutating an external source tree.

### Why this matters

The active frontend speaker list comes from the live workspace behind `/api/config`, not necessarily from the bare repo checkout. When `PARSE_WORKSPACE_ROOT` is set, runtime writes and imports must land in that workspace for the UI to reflect them.

This is especially important for:

- chat-assisted onboarding
- processed-speaker imports
- generated peaks and transcript caches
- persistent chat memory
- annotation and enrichment state during active fieldwork

## Configure `ai_config.json`

PARSE keeps machine-local AI configuration in `config/ai_config.json`, which is intentionally gitignored because it contains model paths, provider choices, and environment-specific settings.

Start from the tracked template:

```bash
cp config/ai_config.example.json config/ai_config.json
```

Then edit the file for your machine.

### Minimum configuration surface to review

#### `stt`

This controls the main speech-to-text provider.

Current template defaults:

```json
"stt": {
  "provider": "faster-whisper",
  "model_path": "",
  "language": "ku",
  "device": "cuda",
  "compute_type": "float16",
  "beam_size": 5
}
```

Important note: if `config/ai_config.json` is missing entirely, the backend can still start by falling back to built-in defaults, but STT falls back to a generic Whisper `base` model instead of a locally configured Razhan path.

#### `ortho`

This configures the orthographic transcription path. The tracked template documents **Razhan** as the canonical Southern Kurdish model:

```json
"ortho": {
  "provider": "faster-whisper",
  "model_path": "razhan/whisper-base-sdh",
  "language": "sd",
  "device": "cuda",
  "compute_type": "float16",
  "beam_size": 5,
  "vad_filter": false,
  "initial_prompt": "",
  "refine_lexemes": false
}
```

The template also explains two operational details worth preserving:

- `vad_filter` defaults to **false** for ORTH so Razhan can cover the full waveform unless you deliberately retune VAD for your recordings.
- `refine_lexemes=true` enables a short-clip Whisper pass after Tier 2 forced alignment, improving `tiers.ortho_words` at the cost of extra runtime.

#### `ipa` and `wav2vec2`

Tier 3 IPA is currently **acoustic wav2vec2-only**. The template is explicit that the older text-based IPA paths are gone.

```json
"ipa": {
  "engine": "wav2vec2",
  "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
  "model_only": true
},
"wav2vec2": {
  "provider": "wav2vec2-ipa",
  "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
  "device": "cuda",
  "force_cpu": false,
  "chunk_size": 150
}
```

#### `llm` and `chat`

These blocks control the in-app assistant provider and chat behavior:

```json
"llm": {
  "provider": "openai",
  "model": "gpt-5.4",
  "api_key_env": "OPENAI_API_KEY"
},
"chat": {
  "enabled": true,
  "read_only": false,
  "provider": "openai",
  "model": "gpt-5.4",
  "api_key_env": "OPENAI_API_KEY"
}
```

Supported LLM/chat backends are currently **OpenAI** and **xAI (Grok)**.

For the wider provider/model overview, see [AI Integration](./ai-integration.md).

## Environment variables

The launcher and MCP adapter both rely on a shared set of `PARSE_*` environment conventions.

| Variable | Default | Purpose |
|---|---|---|
| `PARSE_PY` | `python3` | Python interpreter for the backend. Can point to a Windows `python.exe` when launching from WSL. |
| `PARSE_ROOT` | auto-detected | Repository root. |
| `PARSE_WORKSPACE_ROOT` | `PARSE_ROOT` | Workspace/data root used by backend chat tools and runtime files. |
| `PARSE_CHAT_DOCS_ROOT` | `PARSE_WORKSPACE_ROOT` | Optional docs/text root used by text-preview tooling. |
| `PARSE_CHAT_MEMORY_PATH` | `PARSE_WORKSPACE_ROOT/parse-memory.md` | Persistent markdown memory file used by the chat assistant. |
| `PARSE_EXTERNAL_READ_ROOTS` | empty | Absolute roots that chat tools may read outside the workspace. Use OS path separators for multiple roots, or `*` to disable the sandbox entirely. |
| `PARSE_CHAT_READ_ONLY` | empty | Override chat mutability: `1` forces read-only, `0` forces write-enabled. Otherwise PARSE defers to `config/ai_config.json`. |
| `PARSE_API_PORT` | `8766` | Python API server port. |
| `PARSE_WS_PORT` | `8767` | Additive WebSocket job-streaming sidecar port for `ws://<host>/ws/jobs/{jobId}` subscriptions. |
| `PARSE_VITE_PORT` | `5173` | Vite dev server port. |
| `PARSE_SKIP_PULL` | `0` | Skip the `git pull` step in `parse-run.sh`. |
| `PARSE_PULL_MODE` | `auto` | Git integration strategy: `auto`, `ff`, `rebase`, or `reset`. |
| `PARSE_USE_PERSISTENT_WORKER` | empty | Enable the persistent compute worker path so wav2vec2 can stay warm across jobs. |
| `PARSE_COMPUTE_MODE` | empty | Explicit compute launcher mode such as `thread`, `subprocess`, or `persistent`. |

### `.parse-env` for machine-local overrides

For persistent machine-local settings, create a gitignored `.parse-env` file at the repo root.

Example:

```bash
PARSE_EXTERNAL_READ_ROOTS=/mnt/c/Users/Lucas/Thesis
PARSE_PY=/mnt/c/Users/Lucas/miniconda3/python.exe
PARSE_CHAT_MEMORY_PATH=/path/to/parse-memory.md
```

The launcher reads this file before applying defaults. The standalone MCP adapter mirrors the same convention.

## Manual launch (alternative)

If you prefer to start each server yourself:

```bash
# One-time per clone
cp config/ai_config.example.json config/ai_config.json

# Terminal 1 — Python API backend
cd /path/to/parse
/path/to/anaconda3/envs/kurdish_asr/python.exe python/server.py

# Terminal 2 — Vite frontend
cd /path/to/parse
npm install   # once per clone
npm run dev
```

The backend runs on `8766`; the optional WebSocket sidecar runs on `8767`; Vite runs on `5173`.

If you want realtime STT/job updates, connect to:

```text
ws://localhost:8767/ws/jobs/{jobId}
```

or override the sidecar port with `PARSE_WS_PORT`.

## CLEF configuration on a fresh workspace

Borrowing detection (CLEF) no longer assumes `config/sil_contact_languages.json` already exists.

On the first CLEF run, PARSE opens a guided **Configure CLEF** modal that lets you:

- pick 1–2 primary contact languages
- search the bundled SIL/ISO catalog
- save the language config only, or **Save & populate** immediately

Catalog entries now include an ISO 15924 `script` hint, and PARSE persists that hint into the CLEF config so bare Reference Forms can be routed deterministically even when providers return unlabeled raw strings.

The resulting config is written to:

- `config/sil_contact_languages.json`

If you need to extend the picker with extra language rows, add:

- `config/sil_catalog_extra.json`

## Open in browser

### Active development workflow

- Annotate mode: `http://localhost:5173/`
- Compare mode: `http://localhost:5173/compare`

### Python-served built frontend

After `npm run build`, the Python backend can serve the built UI at:

- Annotate mode: `http://localhost:8766/`
- Compare mode: `http://localhost:8766/compare`

## GPU and model notes

The current PARSE model stack documented in the repo centers on these components:

- **faster-whisper** — local STT / ORTH inference backend
- **CTranslate2** — optimized runtime for Whisper-family models
- **Razhan** (`razhan/whisper-base-sdh`) — Southern Kurdish orthographic transcription
- **Silero VAD** — segmentation for long recordings in Whisper-style decoding
- **wav2vec2** (`facebook/wav2vec2-xlsr-53-espeak-cv-ft`) — Tier 2 forced alignment and Tier 3 acoustic IPA

Operationally:

- The tracked config template defaults to **`device: "cuda"`** and **`compute_type: "float16"`**
- The intended research workflow is GPU-backed local inference
- The faster-whisper path includes explicit CUDA-runtime detection plus a CPU/int8 fallback if the local CUDA stack is unavailable
- `PARSE_STT_FORCE_CPU=1` is available as an emergency override when a WSL/driver stack is unstable and you need STT / ORTH to stay on CPU deliberately
- Tier 3 IPA is no longer text-based; it depends on the wav2vec2 acoustic path
- On WSL, the aligner now resolves to **CPU by default** for long wav2vec2 CTC workloads; the `wav2vec2.force_cpu` and `wav2vec2.chunk_size` settings in `config/ai_config.json` are the main tuning knobs for that path

### Runtime and deployment modes

The current backend runtime has a few operational features that are easy to miss if you only use the default launcher:

- the HTTP server runs behind a **bounded 4-worker request pool** rather than one ad-hoc OS thread per request
- compute jobs support three launcher modes:
  - `thread` — default in-process mode
  - `subprocess` — opt-in subprocess mode
  - `persistent` — preloads wav2vec2 once and reuses it across compute jobs
- `GET /api/worker/status` is the health endpoint for persistent-worker deployments
- if you supervise the backend with PM2, the tracked file is `deploy/pm2-ecosystem.config.cjs`, and `cwd` should point at the **live workspace**, not just the git checkout
- the PM2 config also documents WSL safety defaults such as `PARSE_STT_FORCE_CPU=1` and `CUDA_VISIBLE_DEVICES=""` for all-CPU fallback operation on unstable GPU stacks

For provider-specific details, see [AI Integration](./ai-integration.md).

## Troubleshooting

### `config/ai_config.json` is missing

Symptom:

- PARSE starts, but local STT does not use your intended model path

Fix:

```bash
cp config/ai_config.example.json config/ai_config.json
```

Then edit at least the `stt`, `ortho`, `llm`, `chat`, and `wav2vec2` blocks for your machine.

### `parse-run.sh` reports that it cannot bind `127.0.0.1:8766`

If the error mentions **`WinError 10013`** or **`10048`**, this is usually a Windows/WSL phantom port reservation.

Fix:

1. Run `wsl --shutdown` from Windows Command Prompt or PowerShell
2. Relaunch PARSE
3. If needed, temporarily override the port with `PARSE_API_PORT=<other>`

### WSL cannot kill a stale Windows-side `python.exe`

This happens when `PARSE_PY` points to a Windows conda environment. In that case, the real process is running on the Windows side, not inside WSL.

Current launcher behavior:

- detects the Windows-path case
- calls `taskkill.exe` via `/mnt/c/Windows/System32/`
- clears stale `python.exe` processes that still hold the API port

### The UI loads, but the workspace appears empty

One current config contract is worth knowing:

- `/api/config` responses carry `schema_version: 1`
- the React client validates that schema version at boot
- a mismatch surfaces as a banner rather than silently rendering an empty workspace

If you see a schema mismatch or outdated-server message, restart the Python backend with the latest code and reload the page.

### STT or ORTH coverage looks partial

PARSE distinguishes **"tier has intervals"** from **"the full WAV has been processed"**.

When reviewing pipeline state, prefer the coverage-aware fields:

- `duration_sec`
- `coverage_start_sec`
- `coverage_end_sec`
- `coverage_fraction`
- `full_coverage`

This matters when old runs only covered a stale timestamp window rather than the entire recording.

### Need logs during a launch failure

Use the helper aliases/scripts documented in the launcher workflow:

```bash
parse-logs api
parse-logs vite
scripts/parse-stop.sh
```

## Where to go next

- New user doing annotation work: [User Guide](./user-guide.md)
- Configuring models, chat providers, or tool surfaces: [AI Integration](./ai-integration.md)
- Extending the project itself: [Developer Guide](./developer-guide.md)
