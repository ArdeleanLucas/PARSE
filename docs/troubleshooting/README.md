# Troubleshooting common issues

Start with the symptom, then follow the linked guide.

| Symptom | First place to look |
|---|---|
| Long recording stalls, partially completes, or OOMs | [Troubleshooting long files](long-files.md) |
| API or Vite does not start | [Getting Started troubleshooting](../getting-started.md#troubleshooting) |
| GPU unexpectedly falls back to CPU | [Device selection](../architecture/device-selection.md) and [Environment variables](../reference/environment-variables.md) |
| Job result has `chunks[]`, `partial`, or `coverage_shrink_warning` | [Job result schema](../reference/job-results.md) |
| Agent/MCP automation sees an unexpected result shape | [MCP schema](../mcp/schema.md) |

When reporting a bug, include the speaker, workspace root, command or UI action, terminal job status, and any relevant job-log chunk span.
