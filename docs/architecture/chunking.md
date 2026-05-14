# Chunking and subprocess isolation

Chunking and subprocess isolation are the two safety rails behind PARSE long-file processing.

- **Chunking** answers: "Which part of the recording are we working on now?"
- **Subprocess isolation** answers: "If model work crashes, can the backend survive and report what happened?"

## Chunking: smaller work units, same speaker timeline

Chunking does not create separate speakers and it does not change your source audio. It gives the model smaller time spans to process.

```text
three-hour recording
  chunk 1  00:00-10:00
  chunk 2  10:00-20:00
  chunk 3  20:00-30:00
  ...
  chunk 18 02:50-03:00
```

When a stage finishes, successful chunk output is merged back onto the original timeline. In Annotate mode, you review normal speaker tiers, not a pile of chunk files.

### Why chunks help

| Without chunks | With chunks |
|---|---|
| One model call can run for hours. | Progress advances span by span. |
| One bad region can ruin the whole stage. | A bad region is named by start/end time. |
| Failures often look opaque. | Reports show `ok`, `error`, or `cancelled` per chunk. |
| Reruns are tempting but expensive. | You can target the failed span or stage. |

## Subprocess isolation: protect the server from heavy model work

Some speech/model failures are not polite Python exceptions. They can run out of memory, stall, or crash a process. For risky full-file/full-mode work, PARSE runs the heavy stage in a protected child process.

```text
PARSE backend stays alive
  -> starts protected child process
       -> loads model
       -> processes STT / ORTH / IPA
       -> writes result or structured error
  -> backend reads result and updates job status
```

If the child process fails, the goal is for the parent backend to keep running and return a useful job error instead of disappearing.

## Current practical contract

| Work type | Path PARSE uses | What you should expect |
|---|---|---|
| Full-file STT on a long recording | Chunked + subprocess isolated | Visible chunk progress and per-chunk result details. |
| Full-mode ORTH on a long recording | Chunked Tier 1 + subprocess isolated | Rough transcription chunks, then one alignment pass over merged output. |
| Full-mode IPA | Subprocess isolated | Interval-driven work; no whole-audio duration chunks. |
| Concept-window or edited-only rerun | Fast bounded path | No duration chunks; use this for fixing local problems. |

## Practical rule of thumb

Leave chunking enabled for normal fieldwork. Lower chunk size when memory or decoder-loop failures repeat. Disable chunking only for controlled debugging where you deliberately want the old single-call behavior.

Related: [Compute architecture](compute.md), [Worker process architecture](worker-processes.md), [Environment variables](../reference/environment-variables.md), and [Processing long recordings](../user-guides/processing-long-recordings.md).
