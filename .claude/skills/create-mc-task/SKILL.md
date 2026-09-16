---
name: create-mc-task
description: Manage MC tasks by topic. MC-N is the parent feature; MC-N-A/B/C are the individual lanes. Create, track, and close sub-tasks; close the parent only when all lanes are done.
tags: [mission-control, parse, workflow, quick]
---

# MC Task Structure

```
MC-N          ← parent feature (one per topic/goal)
  MC-N-A      ← Lane A (e.g. parse-back-end)
  MC-N-B      ← Lane B (e.g. parse-front-end)
  MC-N-C      ← Lane C (e.g. parse-coordinator)
```

The parent MC-N is only marked done when **all** its lanes are closed.

**Board lives on the PC.** All reads/writes go via SSH.

---

## Creating a parent task (new feature/topic)

### 1 — Find the next N

```bash
ssh pc wsl -- bash -lc \
  "grep -oP '(?<=\*\*MC-)\d+(?=[\*\-])' /home/lucas/.openclaw/workspace/mc-tasks.md \
   | sort -n | tail -1"
```

Increment by 1 → that is `N`.

### 2 — Add parent to Inbox

```bash
ssh pc wsl -- bash -lc "
sed -i 's|## 📥 Inbox / To Do|## 📥 Inbox / To Do\n- [ ] **MC-N**: FEATURE TITLE 🟡|' \
  /home/lucas/.openclaw/workspace/mc-tasks.md
"
```

---

## Adding a lane sub-task

When spawning an agent lane under an existing parent MC-N:

### Determine the next lane letter

```bash
ssh pc wsl -- bash -lc \
  "grep -oP 'MC-N-\K[A-Z]' /home/lucas/.openclaw/workspace/mc-tasks.md \
   | sort | tail -1"
```

If nothing returns, next letter is `A`. Otherwise increment (A→B, B→C, etc.).

### Add the lane entry nested under the parent

```bash
ssh pc wsl -- bash -lc "
sed -i 's|- \[ \] \*\*MC-N\*\*: FEATURE TITLE 🟡|- [ ] **MC-N**: FEATURE TITLE 🟡\n  - [ ] **MC-N-L**: LANE DESCRIPTION 🟡 (@AGENT)|' \
  /home/lucas/.openclaw/workspace/mc-tasks.md
"
```

Replace `L` with the lane letter and `AGENT` with the agent name (e.g. `parse-back-end`).

---

## Embedding in prompts

Every handoff or agent prompt **must** include both IDs at the top of the body (before the XML sections):

```
MC Task: MC-N (FEATURE TITLE)
Lane:    MC-N-L
```

---

## Including in PR bodies

Every `gh pr create` for a PARSE lane **must** include the MC IDs as the first line of the PR body:

```
**MC Task:** MC-N — FEATURE TITLE / Lane MC-N-L
```

PR titles start with the lane prefix: `[MC-N-L] <type>: <subject>` (conventional-commit type after the bracket). Single-lane tasks still take a lane letter — use `-A`.

Example:

```bash
gh pr create \
  --repo ArdeleanLucas/PARSE \
  --base main \
  --title "[MC-294-A] feat: ..." \
  --body "**MC Task:** MC-294 — Concept Tag UI / Lane MC-294-A

## Summary
...
"
```

The MC ID is how PRs trace back to the board. No PARSE PR ships without it.

---

## Closing a lane (when its PR merges)

```bash
ssh pc wsl -- bash -lc "
sed -i 's|  - \[ \] \*\*MC-N-L\*\*.*|  - [x] **MC-N-L**: LANE DESCRIPTION ✅ (YYYY-MM-DD)|' \
  /home/lucas/.openclaw/workspace/mc-tasks.md
"
```

---

## Closing the parent (when all lanes are done)

Only run this after every `MC-N-*` line is `[x]`:

```bash
ssh pc wsl -- bash -lc "
sed -i 's|- \[ \] \*\*MC-N\*\*.*|- [x] **MC-N**: FEATURE TITLE ✅ (YYYY-MM-DD)|' \
  /home/lucas/.openclaw/workspace/mc-tasks.md
"
```

Then move the block into `## ✅ Recently Done`.

---

## Verify after any write

```bash
ssh pc wsl -- bash -lc \
  "grep 'MC-N' /home/lucas/.openclaw/workspace/mc-tasks.md"
```

---

## Pitfalls

- Always SSH — the board is **not** on the Mac
- `sed -i` patch only — never overwrite the whole file
- Parent entry must exist before adding lane entries
- Never close parent while any lane is still `[ ]`
- Newest parent goes at the **top** of its section
