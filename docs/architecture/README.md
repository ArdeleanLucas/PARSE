# Architecture notes

Architecture references for the PARSE runtime and agent-facing surfaces.

- [Compute architecture](compute.md) — compute-mode dispatch, long-file STT/ORTH chunking, subprocess isolation, device resolution, MCP result schemas, and Khan01/Fail01 incident closure.
- [Worker process architecture](worker-processes.md) — process topology for thread, per-job subprocess, persistent-worker, nested STT/ORTH/IPA isolation, chunk progress, and worker observability.
- [Environment variables](../environment-variables.md) — operator-facing `PARSE_*` runtime knobs for ports, workspace roots, chunking, subprocess timeouts, and device overrides.
