# PARSE documentation

Welcome to the PARSE documentation hub. The pages are grouped by how people usually approach the workstation: start it, understand the core concepts, run fieldwork, look up reference details, and then contribute safely.

## Getting started
- [Quick Start](getting-started.md) — install, configure, and launch PARSE.
- [Installation](installation.md) — compact setup checklist for new machines.
- [First full pipeline run](getting-started/first-pipeline.md) — a guided first end-to-end STT → ORTH → IPA run.

## Core concepts
- [Compute architecture](architecture/compute.md) — worker system, progress model, and long-file safeguards.
- [Long-file processing](architecture/long-file-processing.md) — why PARSE splits and protects long recordings.
- [Chunking and subprocess isolation](architecture/chunking.md) — how chunks and protected worker processes fit together.
- [Device selection](architecture/device-selection.md) — CPU/GPU resolution for STT, ORTH, and IPA.

## User guides
- [Processing long recordings](user-guides/processing-long-recordings.md)
- [Best practices for fieldwork](user-guides/best-practices.md)
- [Troubleshooting](troubleshooting/)

## Reference
- [Environment variables](reference/environment-variables.md)
- [MCP schema](mcp/schema.md)
- [Job result schema](reference/job-results.md)
- [Configuration options](reference/configuration.md)

## Development
- [Development guide](development/)
- [Contributing](../CONTRIBUTING.md)
- [Architecture decisions](development/architecture-decisions/)
- [Release notes](release-notes/)

Historical reports, plans, and archive material remain available under `docs/reports/`, `docs/plans/`, and `docs/archive/`, but the sections above are the preferred navigation path for new readers.
