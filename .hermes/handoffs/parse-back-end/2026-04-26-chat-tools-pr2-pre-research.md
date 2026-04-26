# chat_tools PR 2 pre-research — acoustic starters + pipeline orchestration

## Scope
Pre-load the next implementation slice after the wait-rule lifts, without starting the work.

Target tools (8):
- `stt_start`
- `stt_word_level_start`
- `forced_align_start`
- `ipa_transcribe_acoustic_start`
- `audio_normalize_start`
- `pipeline_state_read`
- `pipeline_state_batch`
- `pipeline_run`

## Evidence anchor
- Audit branch head: `9af9caaff6a1df0dfd95b6aa075bd93186444f63` (PR #80 base commit)
- Current rebuild `origin/main` inspected for code truth: `bf9912c...`
- Current `origin/main:python/ai/chat_tools.py` size: **5428 LoC**
- PR #68 pattern remains the extraction model: grouped-domain modules + thin delegating wrappers left in `chat_tools.py`

## Tool map

| Tool | Spec lines | Spec LoC | Handler lines | Handler LoC | Gross extractable LoC | Key dependencies / coupling |
|---|---:|---:|---:|---:|---:|---|
| `stt_start` | `636-657` | 22 | `2261-2302` | 42 | 64 | `_start_stt_job`, `_resolve_project_path`, `_normalize_speaker`; builds project-relative `sourceWav` payload |
| `stt_word_level_start` | `658-681` | 24 | `2312-2338` | 27 | 51 | Delegates directly to `_tool_stt_start`; must stay adjacent to `stt_start` or share a helper |
| `forced_align_start` | `682-716` | 35 | `2344-2401` | 58 | 93 | `_start_compute_job`, `_normalize_speaker`; dry-run plan mirrors Tier-2 compute payload |
| `ipa_transcribe_acoustic_start` | `717-742` | 26 | `2407-2451` | 45 | 71 | `_start_compute_job`, `_normalize_speaker`; Tier-3 `ipa_only` compute starter |
| `pipeline_state_read` | `1096-1120` | 25 | `2466-2478` | 13 | 38 | `_pipeline_state`, `_normalize_speaker` |
| `pipeline_state_batch` | `1121-1151` | 31 | `2480-2538` | 59 | 90 | `_pipeline_state`, `_normalize_speaker`, and **`_tool_speakers_list()`** fallback |
| `pipeline_run` | `1152-1235` | 84 | `2540-2600` | 61 | 145 | `_start_compute_job`, `_normalize_speaker`; validates `steps` / `overwrites` for `full_pipeline` |
| `audio_normalize_start` | `1236-1261` | 26 | `2610-2641` | 32 | 58 | `_start_normalize_job`, `_normalize_speaker`; dry-run/start pattern matches other job starters |

## Gross extraction size
- Spec blocks total: **273 LoC**
- Handler blocks total: **337 LoC**
- Combined gross extractable content: **610 LoC**

That gross number matters because the amended PR #59 prompt explicitly said:
- one module is acceptable **unless line count exceeds ~600**
- otherwise split into `acoustic_starters.py` + `pipeline_tools.py`

At **610 gross LoC**, PR 2 now lands just over that threshold. The cleanest recommendation is therefore a **2-module split**, not one jumbo module.

## Recommended grouped-module structure

### 1. `python/ai/tools/acoustic_starter_tools.py`
Bundle:
- `stt_start`
- `stt_word_level_start`
- `forced_align_start`
- `ipa_transcribe_acoustic_start`
- `audio_normalize_start`

Why these belong together:
- all are **stateful job starters**, not pollers
- all expose the same dry-run/start pattern
- all depend on callback wiring supplied through `ParseChatTools.__init__`
- `stt_word_level_start` is a thin semantic wrapper over `stt_start`, so splitting them apart would create awkward cross-module calls immediately

Gross extractable LoC for this module:
- **337** (`64 + 51 + 93 + 71 + 58`)

Risk:
- **medium** — these start real jobs, but their handlers are still relatively shallow and callback-driven

### 2. `python/ai/tools/pipeline_orchestration_tools.py`
Bundle:
- `pipeline_state_read`
- `pipeline_state_batch`
- `pipeline_run`

Why these belong together:
- all are about **pipeline preflight/orchestration**, not individual acoustic jobs
- they share `_pipeline_state` and the `full_pipeline` mental model
- `pipeline_state_batch` aggregates the exact same pipeline step family that `pipeline_run` launches

Gross extractable LoC for this module:
- **273** (`38 + 90 + 145`)

Risk:
- **medium** — more validation logic than the single-step starters, but still coherent and isolated

## Why not one `acoustic_pipeline_tools.py` module?
A one-file bundle is technically possible, but it would start around **610 gross LoC before imports/handler tables/comments**, which is already over the prompt's own soft ceiling. That would make the PR review less honest than necessary when a clean two-module split is available now.

## Thin-wrapper plan in `chat_tools.py`
Following the PR #68 pattern, `chat_tools.py` should keep:
- `ParseChatTools`
- public import compatibility
- one-line delegating wrappers such as:
  - `return _acoustic_starters.handle_stt_start(self, args)`
  - `return _pipeline_tools.handle_pipeline_run(self, args)`

Important nuance:
- `stt_word_level_start` currently delegates to `_tool_stt_start(args)`, so after extraction it should delegate to the **shared module helper**, not bounce back through the old in-class wrapper.

## Coupling to PR #68 modules
Direct coupling is small but real:
- `pipeline_state_batch` currently falls back to `self._tool_speakers_list({})`
- `_tool_speakers_list()` is already a thin wrapper around the PR #68 `project_read_tools.py` module

Implication:
- PR 2 should either:
  1. keep using `tools._tool_speakers_list({})` from the extracted handler, or
  2. import/call the underlying project-read helper directly

Recommendation:
- prefer the underlying project-read helper directly inside the extracted pipeline module so the dependency is explicit and does not bounce through an in-class wrapper for internal composition.

## Estimated `chat_tools.py` reduction
Using PR #68 as the modeling precedent:
- gross extracted content: **610 LoC**
- expected wrapper/import overhead left behind: roughly **90-110 LoC**
- estimated net reduction: **~500-520 LoC**

Projected file size after PR 2 alone:
- current: **5428 LoC**
- after PR 2: roughly **4908-4928 LoC**

This is a meaningful second step but still leaves the file large enough that PRs 3 and 4 remain necessary.

## Test surface map

### Tests already aligned with acoustic starters
Main existing surface:
- `python/ai/test_acoustic_alignment_mcp_tools.py`

Direct coverage already exists for:
- `stt_word_level_start`
- `forced_align_start`
- `ipa_transcribe_acoustic_start`
- dry-run behavior
- missing-callback behavior for forced-align

Coverage gap to note:
- `stt_start` itself is much less directly exercised than `stt_word_level_start`
- `audio_normalize_start` is mostly covered via adapter metadata/dry-run tests, not a dedicated chat-tools starter suite

### Tests already aligned with pipeline tools
Main existing surface:
- `python/ai/test_pipeline_chat_tools.py`

Direct coverage already exists for:
- `pipeline_state_read`
- `pipeline_state_batch`
- `pipeline_run`
- step normalization / invalid-step rejection / callback-required errors

### Adapter/integration tests that must still pass unchanged
- `python/adapters/test_mcp_adapter.py`
  - MCP exposure counts and metadata
  - dry-run support for `stt_start` and `audio_normalize_start`
  - project-loaded / stateful-job safety metadata assertions

## PR 2 execution brief (for later, not now)
When the wait-rule lifts, PR 2 should:
1. extract `acoustic_starter_tools.py`
2. extract `pipeline_orchestration_tools.py`
3. leave thin delegating wrappers in `chat_tools.py`
4. add/adjust focused module-level tests where direct extraction coverage is missing
5. re-run the existing pipeline/acoustic/adapter suites before full gates

## Bottom line
PR 2 is already well-shaped:
- **do not** use one oversized module
- use a **2-module split**
- keep `stt_start` + `stt_word_level_start` together
- keep the three pipeline tools together
- expect a **~500-520 LoC** net reduction from `chat_tools.py`

That is the cleanest, reviewable next implementation slice once the wait-rule is explicitly lifted.
