# Processing long recordings

> Last updated: 2026-05-14. This is the practical fieldwork guide for running multi-hour recordings through PARSE after the MC-384 compute-architecture changes. For implementation details, see [Compute architecture](../architecture/compute.md). For failure recovery, see [Troubleshooting long files](../troubleshooting/long-files.md).

PARSE is designed to handle long elicitation recordings, but the safest workflow is still deliberate: import one speaker, confirm the audio metadata, run bounded support jobs, read the progress, and review the result before moving to the next speaker.

## Quick answer: how to process a three-hour recording

Use the default robust path unless you have a specific debugging reason not to.

1. **Launch PARSE with a real workspace root.** Keep fieldwork data outside the git checkout.
   ```bash
   PARSE_WORKSPACE_ROOT="/path/to/parse-workspace" ./scripts/parse-run.sh
   ```
2. **Import or hydrate the speaker.** Confirm the waveform loads and the speaker appears in Annotate mode.
3. **Normalize audio if the recording levels are uneven.** This creates a stable working WAV for repeatable STT/ORTH/IPA work.
4. **Run the full speaker pipeline or run the stages explicitly in order:** STT → ORTH → IPA.
5. **Watch the header job strip while it runs.** Long full-file STT and full-mode ORTH should show chunk progress such as `STT chunk 2/18` or `ORTH chunk 4/18` for a three-hour file with the default 10-minute chunk size.
6. **Open the batch report when it finishes.** Expand any partial row, read the per-chunk outcome table, and note failed `span` values.
7. **Review in Annotate mode.** Treat automation as candidate evidence: confirm boundaries, retime suspicious intervals, and rerun short concept windows where needed.
8. **Move to Compare mode only after coverage is plausible.** Use `coverage_fraction` / `full_coverage` in pipeline state or the visible annotation tiers, not just the fact that a tier has at least one interval.

For most users, no environment changes are required. Default long-file behavior is already chunk-aware and subprocess-isolated.

## What PARSE does by default

| Stage | Default long-file behavior | Why it matters |
|---|---|---|
| STT | Full-file STT splits recordings longer than `PARSE_STT_DEFAULT_CHUNK_MINUTES=10` into adjacent chunks. | A hallucination or decoder loop in one slice should not stop the rest of the recording from being attempted. |
| ORTH | Full-mode ORTH splits Tier-1 transcription longer than `PARSE_ORTH_DEFAULT_CHUNK_MINUTES=10`, merges the output, then runs Tier 2 once. | Reduces peak memory and keeps Tier 2 alignment operating on the merged transcript. |
| IPA | IPA is interval-driven and does not chunk by whole-audio duration. | IPA works over existing STT/ORTH/concept intervals rather than one monolithic recording pass. |
| Subprocess isolation | Full-file STT, full-mode ORTH, and full-mode IPA run in isolated subprocesses. | A model crash/OOM should become a structured job error instead of killing the backend. |

Chunking is **intent-aware**:

- Full speaker / full pipeline runs use the robust long-file path.
- Concept-window and edited-only reruns stay fast and bounded; they do not use duration chunking.
- A short recording below the configured chunk duration uses one provider call and returns `chunks: []`.

## Monitoring progress in the UI

During a long run, use three places:

1. **Header job strip** — shows the active job, stage, and chunk progress.
2. **Batch report** — after completion, distinguishes OK, partial, empty, error, cancelled, and skipped outcomes.
3. **Chunk details** — expand a partial batch cell to see `#`, `span`, `status`, `code`, and `error` for each chunk.

Typical progress messages look like:

```text
STT chunk 1/18 (0s–600s)
STT chunk 2/18 (600s–1200s)
ORTH chunk 1/18 (0s-600s)
```

A three-hour recording is about 18 chunks at the 10-minute default. A 2 h 32 min file is about 16 chunks. A one-hour file is about 6 chunks.

## What happens if some chunks fail

PARSE records chunk failures instead of flattening the whole stage into a single opaque failure.

| Chunk status/code | Meaning | What to do next |
|---|---|---|
| `ok` | That chunk produced usable output. | Review the merged tier normally. |
| `error` + `oom_suspect` | The model or subprocess likely ran out of host RAM/VRAM. | Close other heavy apps, lower chunk size, or use CPU/device overrides for that stage. |
| `error` + `timeout` | The chunk exceeded the configured subprocess timeout or stalled long enough to be killed. | Inspect logs, increase timeout only if the chunk is still making progress, or lower chunk size. |
| `error` + `provider_error` | The provider raised a non-OOM exception. | Read `job_logs` / report traceback; check model paths, language, audio health, and provider config. |
| `cancelled` | The user or caller cancelled before this chunk ran. | Decide whether to resume the stage later. Completed chunks remain useful evidence. |

The merged transcript/annotation tiers are still the main review surface. `chunks[]` is diagnostic job-result data; it is not persisted into the STT cache.

## Re-running failed work

Current PARSE recovery is stage- and speaker-oriented, not a one-click "rerun chunk 3 only" button.

Use this decision path:

1. **If a batch report shows failed speakers:** click **Rerun failed** to queue only the failed speaker rows from that batch.
2. **If one stage failed for one speaker:** rerun only that stage for that speaker, not the whole batch.
3. **If a failure is localized to one time span:** use the chunk `span` to guide manual review. When the lexical interval is known, use concept-window or edited-only STT/ORTH/IPA reruns over that bounded interval.
4. **If the failure is an STT/ORTH whole-chunk OOM or decoder loop:** lower the relevant chunk size and rerun the failed stage for that speaker. Smaller chunks are the practical recovery path for now.
5. **If the output is mostly good but one lexical item is poor:** do not rerun the whole recording. Use per-lexeme rerun actions or the concept-window workflow from Annotate mode.

Practical recovery example for a fragile STT file:

```bash
PARSE_STT_DEFAULT_CHUNK_MINUTES=5 ./scripts/parse-run.sh
```

Then rerun STT for the affected speaker and inspect whether the previously failed `span` now has output.

## Performance expectations

Performance depends heavily on model choice, disk speed, CPU/GPU availability, and whether models are already downloaded/warm. Treat the numbers below as planning envelopes, not guarantees. For a new workstation, benchmark one 10-minute slice and multiply by chunk count.

| Hardware profile | 1-hour recording | 2-hour recording | 3-hour+ recording | Recommended operating style |
|---|---:|---:|---:|---|
| 16 GB RAM laptop, CPU-only or unstable GPU | Often several hours per full pipeline. | Plan for overnight work. | Split by speaker/session if possible; avoid running many speakers in one batch. | Use default or 5-minute chunks; run STT/ORTH/IPA one stage at a time; close browsers/model tools. |
| 16 GB RAM laptop with working CUDA | Often faster than CPU, but memory pressure can still appear during ORTH/IPA. | Long single-speaker runs are reasonable with careful monitoring. | Prefer one speaker at a time; watch VRAM/host memory. | Keep 10-minute chunks first; lower to 5 minutes after OOM; consider `PARSE_STT_DEVICE=cpu` if STT competes with ORTH/IPA. |
| 32–64 GB RAM workstation with CUDA | Usually practical for interactive long-file processing. | Usually practical in one session. | Still inspect chunk reports; do not assume all-green. | Keep defaults; use per-stage device overrides only when logs show a real placement issue. |
| Server/workstation with high RAM and CUDA | Best for batch runs and repeated speakers. | Good candidate for multi-speaker batches. | Monitor logs and disk usage; model/provider errors can still be data-specific. | Defaults are suitable; persistent outer worker can reduce warm-up for repeated jobs, but nested heavy-stage isolation remains. |

Important resource patterns:

- **Chunking lowers peak risk, not total work.** A three-hour file still contains three hours of audio. Chunking makes failures smaller and progress visible.
- **Smaller chunks are safer but can be slower.** Five-minute chunks double the number of provider calls compared with ten-minute chunks.
- **GPU helps throughput but does not eliminate host-memory failures.** Model load, temporary WAVs, and Python process overhead still consume RAM.
- **IPA cost follows interval count more than total WAV duration.** A three-hour recording with many word windows can make IPA expensive even though IPA does not duration-chunk.
- **First run may be slower.** Model download/import/warm-up can dominate the first chunk.

## Recommended settings by situation

| Situation | Suggested settings | Notes |
|---|---|---|
| Normal fieldwork on a capable workstation | Defaults (`10` minute STT/ORTH chunks; devices `auto`). | Best default for Khan01/Fail01-scale recordings. |
| 16 GB laptop or repeated OOM | `PARSE_STT_DEFAULT_CHUNK_MINUTES=5 PARSE_ORTH_DEFAULT_CHUNK_MINUTES=5` | Increases overhead but reduces per-call memory pressure. |
| STT is unstable on GPU | `PARSE_STT_DEVICE=cpu` | Slower, but can free GPU memory for ORTH/IPA. |
| All GPU use is unstable | `PARSE_COMPUTE_DEVICE=cpu` | Predictable fallback; expect long wall times. |
| Controlled benchmark against old behavior | `PARSE_STT_DEFAULT_CHUNK_MINUTES=0 PARSE_ORTH_DEFAULT_CHUNK_MINUTES=0` | Debug only; not recommended for fieldwork. |

## When and how to disable chunking

Disable duration chunking only when you deliberately want the old monolithic provider-call behavior.

STT only:

```bash
PARSE_STT_DEFAULT_CHUNK_MINUTES=0 ./scripts/parse-run.sh
```

ORTH only:

```bash
PARSE_ORTH_DEFAULT_CHUNK_MINUTES=0 ./scripts/parse-run.sh
```

Both STT and ORTH:

```bash
PARSE_STT_DEFAULT_CHUNK_MINUTES=0 \
PARSE_ORTH_DEFAULT_CHUNK_MINUTES=0 \
./scripts/parse-run.sh
```

Valid reasons to disable chunking:

- You are benchmarking old vs new behavior on a short, controlled recording.
- A provider bug appears only in the chunked path and you need a minimal comparison.
- The file is already very short and you want to remove even the duration gate from the experiment.

Risks:

- Higher peak memory and VRAM pressure.
- A hallucination loop can affect the whole file instead of one slice.
- A crash or timeout loses the whole stage, not just a chunk.
- Long jobs may show less granular progress.

Recommended default for almost everyone: **leave chunking enabled**.

## Academic review guidance

Automation output is evidence, not final analysis.

Before using long-file output for comparison or publication:

- Confirm that the target lexical intervals actually cover the intended prompts/responses.
- Check suspicious chunk boundaries, especially where a failed chunk is adjacent to an `ok` chunk.
- Treat `full_coverage=false`, severe IPA shrink warnings, or large empty-step counts as review blockers.
- Keep notes on reruns, chunk-size changes, and manual boundary edits so later cognate/export decisions remain auditable.

## Related docs

- [Troubleshooting long files](../troubleshooting/long-files.md)
- [Environment variables](../environment-variables.md)
- [Compute architecture](../architecture/compute.md)
- [MC-384 migration notes](../getting-started/migration.md)
- [MCP schema: compute job result shapes](../mcp-schema.md#compute-job-result-shapes)
