# How long-file processing works

Long field recordings stress speech models because a single provider call can run out of memory, silently stop after a decoder loop, or hide which part of the audio failed. PARSE handles these recordings with a layered contract:

```text
recording
  -> preflight duration and workspace state
  -> chunk long STT/ORTH Tier-1 work into adjacent spans
  -> run memory-heavy full-file/full-mode stages in protected subprocesses
  -> merge successful output back into normal speaker annotations/caches
  -> report per-chunk progress and terminal result details
```

## What gets chunked
- **Full-file STT** chunks recordings longer than `PARSE_STT_DEFAULT_CHUNK_MINUTES`.
- **Full-mode ORTH** chunks Tier-1 transcription longer than `PARSE_ORTH_DEFAULT_CHUNK_MINUTES`, then runs Tier 2 once over merged output.
- **IPA** is interval-driven; it does not chunk by whole-audio duration, but destructive overwrite reruns can emit a coverage-shrink warning.

Concept-window and edited-only paths stay bounded and fast; they do not use duration chunking.

## What users see
- The job strip reports progress such as `STT chunk 2/7`.
- Batch reports can distinguish success, partial success, cancellation, and per-chunk error states.
- Persisted STT caches remain a flat merged `segments[]` list; chunk diagnostics live in job results.

## Why this matters for fieldwork
The goal is not only speed. The goal is recoverability: when a long recording fails, the user should know which span failed, what already succeeded, and whether it is safe to continue review.

Related: [Compute architecture](compute.md), [Chunking and subprocess isolation](chunking.md), [Processing long recordings](../user-guides/processing-long-recordings.md), and [Job result schema](../reference/job-results.md).
