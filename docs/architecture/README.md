# Architecture notes

Architecture references for the PARSE runtime and agent-facing surfaces.

- [Compute architecture](compute.md) — worker mental model, compute-mode dispatch, long-file STT/ORTH chunking, subprocess isolation, device resolution, MCP result schemas, and Khan01/Fail01 incident closure.
- [How long-file processing works](long-file-processing.md) — user-readable model of long-recording safeguards and partial recovery.
- [Chunking and subprocess isolation](chunking.md) — focused explanation of chunk spans, protected child processes, and current stage behavior.
- [Device selection](device-selection.md) — CPU/GPU resolution order and practical override guidance.
- [Worker process architecture](worker-processes.md) — process topology for thread, per-job subprocess, persistent-worker, nested STT/ORTH/IPA isolation, chunk progress, and worker observability.
- [Cognate sets → phylogenetic matrix](cognate-sets-and-matrix.md) — how committed cognate decisions become the LingPy/NEXUS matrix: effective-set resolution, COGID assignment, the fold-by-concept invariant, why `cognate_sets` key-count drift is cosmetic, and what is *not* read by the matrix.
- [Environment variables](../reference/environment-variables.md) — operator-facing `PARSE_*` runtime knobs for ports, workspace roots, chunking, subprocess timeouts, and device overrides.
