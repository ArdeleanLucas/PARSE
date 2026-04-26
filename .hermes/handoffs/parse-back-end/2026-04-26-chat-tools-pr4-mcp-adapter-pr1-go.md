---
agent: parse-back-end
queued_by: parse-gpt
queued_at: 2026-04-26
status: ready-now
source_of_truth_pr: 102
execution_order:
  - chat_tools PR 4 pre-research
  - chat_tools PR 4 implementation
  - mcp_adapter PR 1 (env_config.py)
related_prs:
  - 83
  - 91
  - 100
  - 102
  - 120
related_docs:
  - .hermes/handoffs/parse-back-end/2026-04-26-chat-tools-pr4-and-mcp-adapter-pr1.md
  - .hermes/handoffs/parse-back-end/2026-04-26-mcp-adapter-architecture-audit.md
  - docs/reports/2026-04-26-rebuild-progress-scorecard-late-refresh.md
---

# parse-back-end GO signal — chat_tools PR 4, then mcp_adapter PR 1

## One-sentence directive
Use **PR #102 as the governing spec**, do **not** re-derive the task, and open the work in this order: **(1) chat_tools PR 4 pre-research docs PR, (2) chat_tools PR 4 implementation PR, (3) mcp_adapter PR 1 `env_config.py` implementation PR**.

## Why the first PR is pre-research, not implementation

Lucas added an explicit gate for this lane:

- if a target is **over 500 LoC**, and
- PR #102 **does not already contain grounded current line ranges + LoC estimates**

then the first PR must be a **docs-only pre-research PR** in the same pattern as PR #83.

That gate applies to **chat_tools PR 4**. PR #102 gives the grouped-domain shape (`compare_tools.py`, `enrichment_tools.py`, `export_tools.py`) and ordering, but it does **not** pin current exact line ranges or a current family-size estimate on the post-PR-120 `origin/main` tree. So the first execution PR is the pre-research pass.

That gate does **not** apply to **mcp_adapter PR 1**: the `env_config.py` seam already has a grounded architecture audit in `.hermes/handoffs/parse-back-end/2026-04-26-mcp-adapter-architecture-audit.md`, and that slice is already framed as a low-risk ~150–250 LoC extraction.

## First PR to open

**Open this PR first:**

- **Type:** docs-only pre-research PR
- **Topic:** `chat_tools PR 4`
- **Suggested title:** `docs(chat_tools): PR 4 pre-research for compare/enrichment/export bundles`

### Required outputs for that pre-research PR

1. A new handoff doc under `.hermes/handoffs/parse-back-end/` for PR 4 pre-research.
2. Grounded current line ranges in `python/ai/chat_tools.py` for the PR 4 family on the branch's actual `origin/main` base.
3. A grouped-module recommendation using the PR #102 spec as the default shape:
   - `python/ai/tools/compare_tools.py`
   - `python/ai/tools/enrichment_tools.py`
   - `python/ai/tools/export_tools.py`
4. A current LoC estimate for each family/module and predicted net reduction in `chat_tools.py`.
5. A test-surface map naming the exact backend suites to extend or preserve.

### Success criterion for the pre-research PR

It should leave the implementation agent with the same quality bar PR #83 gave PR #91: a grounded, reviewable extraction map rather than a vague "final bundle" instruction.

## Then: implementation order

### PR 2 for the lane — chat_tools PR 4 implementation

Implement the extraction exactly from the pre-research PR + PR #102 spec. Keep the grouped-module / thin-wrapper pattern established by PRs #68, #91, #108, #111, and #120.

### PR 3 for the lane — mcp_adapter PR 1 (`env_config.py`)

After chat_tools PR 4 lands, execute the `env_config.py` slice from the existing MCP adapter architecture audit.

Hard rule remains unchanged:

- **do not touch FastMCP private API mutation** in this PR
- that seam stays deferred to a later dedicated handoff

## Non-negotiable guards for every PR in this lane

### Repo / branch / PR-target guards

- work from the rebuild lane only: `TarahAssistant/PARSE-rebuild`
- use `--repo TarahAssistant/PARSE-rebuild` on every `gh pr create`
- branch from fresh `origin/main`

### Mergeability freshness guard

Before claiming any PR is `MERGEABLE`, `CLEAN`, `DIRTY`, or `CONFLICTING`, run:

```bash
git fetch origin --quiet --prune
gh pr view <N> --repo TarahAssistant/PARSE-rebuild --json mergeable,mergeStateStatus,baseRefOid,headRefOid
```

Do not report cached status from memory.

### Screenshot convention

If you include screenshots in PR descriptions or comments, use **markdown links only**.

- acceptable: `[annotate smoke screenshot](https://...)`
- not acceptable: inline image embeds / markdown image syntax

### Mandatory closeout after each PR

After **each** PR in this lane:

1. update the MC item
2. update the daily log
3. update the rebuild progress scorecard

This applies to the pre-research PR as well as the two implementation PRs.

## Current coordinator ack

The first parse-back-end execution PR this handoff authorizes is:

**`docs(chat_tools): PR 4 pre-research for compare/enrichment/export bundles`**
