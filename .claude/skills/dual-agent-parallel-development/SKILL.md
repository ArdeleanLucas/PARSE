---
name: dual-agent-parallel-development
description: Plan and execute a large codebase split across two AI agents running in parallel on separate tracks, with a shared contract gate, token-efficient per-phase context files, and a merge coordinator. Use when a project is too large for one agent track and has a clean feature-area split.
tags: [planning, dual-agent, parallel, react, vite, subagent, orchestration]
related_skills: [writing-plans, subagent-driven-development, parse-react-vite-pivot]
---

# Dual-Agent Parallel Development

## When to Use

- Project has a clean feature-area split (e.g. Annotate Mode vs Compare Mode, frontend vs admin panel)
- Single agent track would take 7+ days and block on human testing at each phase
- Two agents can work independently for 3–5 days before needing to merge
- There is a well-defined shared layer (stores, API types, shared components) that must be agreed before either agent starts

**Do NOT use** for sequential work, or when tracks have heavy interdependencies that require constant coordination.

---

## Core Pattern

```
Phase 0: Shared Contract (BLOCKER — both agents wait)
    ↓
Phase A ──────────────────── Phase B (parallel, no overlap)
Track A agent + Codex        Track B agent + Flash/Pro
feat/track-a branch          feat/track-b branch
    ↓                              ↓
Track A gate tests pass      Track B gate tests pass
    ↓                              ↓
          Phase C: Merge + Integration (one agent leads)
                feat/main-pivot branch
                    ↓
              Human regression checklist
```

---

## Step 1: Identify the Split

Find the natural boundary — it must be a file-level ownership split, not a concern-level split.

**Good split:**
- `src/components/annotate/` vs `src/components/compare/`
- `src/features/billing/` vs `src/features/inventory/`

**Bad split:**
- "Agent A does state, Agent B does UI" — they'll constantly need the same files
- "Agent A does backend, Agent B does frontend" — API changes block B constantly

Write an ownership table before anything else:

```
Agent A owns: <list every file path>
Agent B owns: <list every file path>
Shared (Agent A writes, Agent B reads-only): <list>
Neither agent touches: <list>
```

---

## Step 2: Define the Shared Contract (Phase 0)

The shared contract is what both agents agree on before any feature code is written.
It must cover:

1. **Store shapes** — exact TypeScript interfaces for every shared state store.
   Write them out in full. Mark them IMMUTABLE — no agent may change without human approval.

2. **API client interface** — typed function signatures for every backend call.
   One module. One agent writes it. Other agent only calls it.

3. **Shared component list** — which primitives exist in `components/shared/`.
   Agent A (the scaffold owner) writes them. Agent B imports them, never reimplements.

4. **Build/proxy config** — Vite config, package.json, tsconfig.json — scaffold owner writes once.

**Gate test (both agents run this before starting their track):**
```bash
npm install && npm run dev     # dev server starts
curl localhost:PORT/api/health # proxy to backend confirmed
npx tsc --noEmit               # zero TypeScript errors
```
If any fail → stop, fix, retry. No feature code until all three pass.

---

## Step 3: Write Per-Agent System Prompts as Split Files

**Do NOT write one monolithic system prompt.** Split into:

```
docs/plans/{agent}/
  {agent}-core.md       # Identity, ownership table, tech stack, build order, summary rules
  phase-0.md            # Gate check, store shapes, API contract
  rules.md              # Hard rules — load with every task
  coordination.md       # When to stop, when to request, completion gate + human checklist
  b1-{component}.md     # One file per component/hook/store
  b2-{component}.md
  ...
```

**Why split:** An agent working on component B4 doesn't need B1's instructions. Loading only
`{agent}-core.md` + `rules.md` + `b4-{component}.md` saves ~80% of tokens vs the monolith.

**Core file structure (always loaded):**
1. Identity + role (2–3 sentences)
2. Project context (what does this app do — 1 paragraph)
3. Exact file ownership table (write / read-only / never touch)
4. Build order table (maps each Bx file to its component)
5. Summary rules section (dense paragraphs by domain: Backend, State, Data integrity, UI, Exports, Branch, Gate)

**Per-component file structure:**
1. Model assignment (Flash vs Pro — declare it)
2. Legacy source file to read first
3. Output file path
4. What it is (2–3 sentences)
5. Data shape it reads/writes
6. Behavior rules (bullet list)
7. Required tests (exact `describe/it` cases)
8. Run command + expected result

---

## Step 4: Harden AGENTS.md and CODING.md

Every spawned Codex agent reads `AGENTS.md` and `CODING.md` first. If these files contradict
the active plan, the agent will follow the wrong instructions.

**AGENTS.md must include:**
- Repo path on disk (for Codex `--workdir`)
- Branch names for each track
- Pointer to the agent prompt entry point (not the old monolith)
- Phase 0 described as a hard blocker, not a suggestion
- Model routing codified with exact model names

**CODING.md must include:**
- A prominent banner at the top if old instructions are archived
- Updated sub-agent rules pointing to the new plan files
- Data integrity rules (timestamps, IDs) that survive the pivot

**Check before starting work:**
```bash
grep -n "vanilla JS\|no npm\|no TypeScript\|no bundler" CODING.md
# If any hits: add archived banner at top, update sub-agent rules
```

---

## Step 5: Model Assignment

Pro models for architectural complexity. Flash for mechanical work.

| Task type | Model |
|---|---|
| Complex grid rendering, dynamic rows/cols | Pro |
| Multi-step state machines (wizards, onboarding) | Pro |
| Master-detail UIs with non-trivial interaction | Pro |
| Form inputs, display-only panels | Flash |
| Hooks with simple poll/fetch lifecycle | Flash |
| Root assembler components | Flash |
| Tests for simple components | Flash |

Declare the model at the top of each per-component file so the agent doesn't have to decide.

---

## Step 6: Completion Gates

**Each track has its own gate — never merge until it passes:**

Automated (agent verifies):
- `npm run test` — zero failures
- `npx tsc --noEmit` — zero errors
- Every component has a co-located test file

Human verification (cannot be automated):
- Audio/waveform playback (if applicable)
- Real data round-trips (save → reload → verify)
- AI pipeline end-to-end (requires GPU + live model)
- Export correctness (requires domain knowledge)
- The primary output of the project (e.g. LingPy TSV for a linguistics tool)

**Write the human checklist explicitly** in `coordination.md` as a checkbox list.
State clearly: "Track B is not done until Lucas has checked every item personally."

---

## Step 7: Phase C Merge

One agent leads. The other delivers a passing branch and stops.

```bash
git checkout -b feat/main-pivot
git merge feat/track-a
git merge feat/track-b
npm run test        # must pass
npx tsc --noEmit    # must pass
```

Expected merge conflicts: `App.tsx`, shared store files, `package.json`.
Resolve, run tests again, then proceed to integration tests.

After merge: cross-mode state isolation tests (navigate A → B → A, verify no state loss).

---

## Pitfalls

- **Store shape drift** — Agent B silently adds a field to a shared store. Gate: shapes are immutable, any change requires human approval in writing before code changes.
- **Direct fetch calls** — Agent B bypasses the API client and calls fetch() directly. Gate: rule in `rules.md` + code review checks for `fetch(` in agent-owned files.
- **AGENTS.md/CODING.md still have old instructions** — spawned Codex reads them and follows the archived plan. Fix: add archived banner to CODING.md, update AGENTS.md pointers before starting.
- **Monolith system prompt loaded every session** — burns tokens. Fix: split into per-phase files, agent loads only what the current task needs.
- **Human gate skipped** — agent declares Track B done based on automated tests passing. Fix: completion gate explicitly names the human as the verifier, not the test suite.
- **Phase 0 treated as optional** — one agent starts component work before the other has committed the scaffold. Fix: Phase 0 gate check commands are in the agent's core file; agent is instructed to stop if they fail.
