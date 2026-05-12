# <tool_name>

<!--
Canonical template for a single PARSE agent-skill doc.

Fill order:
  1. Metadata block (mechanically derivable from ChatToolSpec)
  2. One-Sentence Summary (auto-derivable from spec.description, may be trimmed)
  3. Parameters table (auto-derivable from spec.input_schema)
  4. Example Successful Call (one minimal call; complex tools may add a second)
  5. Expected Output (return shape; for stateful_job tools name the polling tool)
  6. When to Use / When NOT to Use (manual — domain judgment)
  7. Common Failure Modes & How to Recover (manual — drawn from real bugs/edge cases)
  8. Agent Reasoning Notes (manual — pipeline placement + heuristics)

Mutability values (match ChatToolSpec): read_only | mutating | stateful_job
Complexity scale: Low | Low–Medium | Medium | Medium–High | High
Estimated Tokens: rough budget for short-form + full-form versions of this doc

Delete this comment block in real skill docs.
-->

**Category:** Annotation | Comparison | Export | Project | Advanced  
**Mutability:** read_only | mutating | stateful_job  
**Supports Dry Run:** Yes | No | N/A  
**Complexity:** Low | Low–Medium | Medium | Medium–High | High  
**Estimated Tokens:** ~XXX (short) / ~XXX (full)

## One-Sentence Summary
One declarative sentence describing what the tool does. No "this tool" / "this skill" preamble. Start with a verb: "Runs...", "Reads...", "Exports...", "Detects..."

## When to Use
- Concrete situation 1 (e.g. "First processing step for newly imported audio")
- Concrete situation 2
- Concrete situation 3

## When NOT to Use
- Concrete anti-case 1 (e.g. "If high-quality manual transcripts already exist")
- Concrete anti-case 2 — including which alternative tool to reach for instead
- Concrete anti-case 3 — including any hard precondition the tool will reject

## Parameters

| Parameter | Type   | Required | Description                                    | Default      | Example                  |
|-----------|--------|----------|------------------------------------------------|--------------|--------------------------|
| speaker   | string | Yes      | Speaker identifier; must exist in workspace    | —            | `"speaker_07"`           |
| dryRun    | bool   | No       | Preview without persisting                     | `false`      | `true`                   |
| ...       | ...    | ...      | ...                                            | ...          | ...                      |

For stateful_job tools, also document the paired `*_status` tool the agent should poll.

## Expected Output
Describe the return shape in 1–3 lines. For:
- **read_only** — name the keys returned and what the agent can/can't infer from them.
- **mutating** — name the files mutated and the backup/rollback path if any.
- **stateful_job** — say "Returns `{ jobId }`. Poll with `<status_tool>` until status is `done` or `error`." Mention any artifact paths written on success.

## Example Successful Call
```json
{
  "speaker": "speaker_07",
  "dryRun": false
}
```

If the tool has a meaningful dry-run preview, add a second block showing the dry-run shape and noting "Always use `dryRun: true` first."

## Common Failure Modes & How to Recover

| Failure | Symptom | Recovery |
|---|---|---|
| Pre-condition missing | Error like `... requires Tier 1 STT first` | Run the prerequisite tool, then retry |
| Wrong input shape | Validation error | Re-inspect the live schema via the HTTP MCP bridge before retrying |
| Long-running job timeout | Job stuck `running` past expected duration | Read `job_logs` for the jobId; fall back to the lower-level tool if the macro stalls |

Use a table when there are ≥3 distinct failure modes; otherwise a short bulleted list is fine.

## Agent Reasoning Notes
Pipeline placement (what typically runs before this, what typically follows), composition hints ("often used as the first step in `run_full_annotation_pipeline`"), and any model-specific guidance (e.g. "Smaller models tend to over-call this — prefer scoped variants").

Two or three sentences max. This section is for *judgment calls*, not a re-statement of the summary.

---

<!--
Optional sections (include only if relevant for the tool):

## Side Effects
Use when the tool writes outside the obvious primary artifact (e.g. updates `source_index.json`, mutates `project.json`, refreshes a cache).

## Related Skills
- `tool_a` — usually run before this
- `tool_b` — usually run after this
- `tool_c` — alternative for case X

## Safety Notes
Use when the tool is genuinely destructive (clears data, force-overwrites without backup), or when chaining it with another tool can compound damage.
-->
