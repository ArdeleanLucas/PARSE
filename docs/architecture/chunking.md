# Chunking and subprocess isolation

Chunking and subprocess isolation solve different failure modes, and PARSE uses both for robust long-file work.

## Chunking
Chunking splits a long audio stage into adjacent time spans. Each span can report its own status and error code.

```text
long recording
  chunk 1: 0s-600s
  chunk 2: 600s-1200s
  chunk 3: 1200s-1800s
```

This reduces per-call memory pressure and makes partial recovery possible.

## Subprocess isolation
Subprocess isolation runs memory-heavy full-file/full-mode stages in a protected child process. If a model call crashes, OOMs, or times out, the parent backend can serialize that failure into a job result instead of dying with the child.

```text
HTTP/API job
  outer compute launcher
    protected child process
      STT / ORTH / IPA model work
    result file + progress handoff
  terminal job snapshot
```

## Current contract
- Full-file STT: chunked by duration when long, subprocess-isolated.
- Full-mode ORTH: chunked Tier 1 when long, subprocess-isolated.
- Full-mode IPA: subprocess-isolated; interval-driven rather than duration-chunked.
- Concept-window reruns: bounded in-process paths unless the caller requests a full-file/full-mode stage.

Related: [Compute architecture](compute.md), [Worker process architecture](worker-processes.md), and [Environment variables](../reference/environment-variables.md).
