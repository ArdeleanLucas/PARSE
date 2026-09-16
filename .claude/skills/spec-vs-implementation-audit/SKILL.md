---
name: spec-vs-implementation-audit
description: >
  Systematic audit of a codebase against its design spec — find broken API connections,
  schema mismatches, missing files, and unimplemented planned features. Produces a
  structured report with severity ratings and clarifying questions for the user.
tags: [audit, spec, pipeline, bugs, api, schema, report]
triggers:
  - "review the pipeline"
  - "look for problems/bugs/broken connections"
  - "audit the codebase against the plan"
  - "does the code match the spec"
  - "find what's missing or broken"
---

# Spec vs Implementation Audit

Use when asked to review a codebase for correctness against a design doc, spec, or plan.
The goal is a **complete structured bug report** — not fixes, just findings + questions.

---

## Phase 1 — Load the Spec

Read all authoritative planning documents **before touching any code**:

1. Primary spec/plan (e.g., `PROJECT_PLAN.md`, `SPEC.md`, `ARCHITECTURE.md`)
2. Interface contracts (e.g., `INTERFACES.md`, `API.md`, `SCHEMA.md`)
3. Build protocol / coding standards (e.g., `CODING.md`, `AGENTS.md`)
4. Any lessons-learned files (e.g., `tasks/lessons.md`)

Extract and note:
- All planned API endpoints (routes, methods, expected payloads)
- All data schemas (file formats, field names, types)
- All planned files (modules, configs, scripts)
- All planned events / inter-module communication contracts
- Any items explicitly marked `[PLANNED]`, `TBD`, or `TODO`

---

## Phase 2 — Inventory What Exists

```bash
# List all source files with modification dates
ls -la python/ python/ai/ python/compare/ js/shared/ js/annotate/ js/compare/

# Check for missing planned files
for f in "path/to/expected/file.py" ...; do
  [ -f "$f" ] && echo "EXISTS: $f" || echo "MISSING: $f"
done
```

---

## Phase 3 — Cross-Reference API Routes

**Extract server-side routes:**
```bash
grep -n "request_path ==" python/server.py | grep -o '"[^"]*"' | sort -u
# Or for Express/Flask:
grep -n "app\.\(get\|post\|put\|delete\)" server.js | sort -u
```

**Extract client-side calls:**
```bash
grep -roh "/api/[a-z/_-]*" js/ | sort -u
```

**Compare the two lists** — every client call must have a server handler. Flag:
- Routes called by JS but missing in server → **BROKEN** (404 at runtime)
- Routes in server but never called → possible dead code
- Routes with mismatched HTTP methods

**PARSE-specific pattern — JS endpoint constants:**
In PARSE, JS modules often declare API routes as named constants at the top of the file.
These are the most reliable extraction target — they represent intentional contracts:

```bash
# Find all JS API constant declarations
grep -rn "const API_\|'/api/\|\"/api/" /mnt/c/Users/Lucas/parse_v2/js/ | \
  grep -v "//.*api" | sort -u

# Check each against server.py handlers
grep -n "request_path ==" /mnt/c/Users/Lucas/parse_v2/python/server.py | \
  grep -o '"[^"]*"' | sort -u
```

A route in the first list but absent from the second is a **silent wiring failure** —
the feature appears to exist in the UI but 404s at runtime with no error logged.
This pattern is distinct from planned-but-not-built features: the JS was already written,
meaning the route was expected, not deferred. Treat these as bugs, not gaps.

---

## Phase 4 — Check Data Schemas

For each data file format in the spec:

1. Read the spec schema definition
2. Read an actual file from disk: `head -N actual_file.json`
3. Compare field names, nesting, required vs optional fields

Common mismatches to look for:
- Field name differences (`speaker` vs `speakerId`, `start` vs `start_sec`)
- Missing required fields (e.g., `duration_sec`, `version`)
- Extra fields that downstream consumers won't expect
- File naming convention mismatches (e.g., `.json` on disk vs `.parse.json` in code)

---

## Phase 5 — Check File Naming Conventions

```bash
# Example: if plan says *.parse.json but disk has *.json
ls annotations/        # what's there
grep -n "FILENAME_SUFFIX\|glob\|parse.json" python/server.py   # what code expects
```

Pay special attention to:
- **Read vs write paths** — server may read legacy format but write canonical format, creating two files
- **Glob patterns** — compute pipelines that discover files via glob will miss legacy-named files silently

---

## Phase 6 — Check Dependencies

```bash
pip show lingpy faster-whisper some-library 2>/dev/null | head -3
```

Verify that libraries referenced in code are actually installed in the runtime environment.

---

## Phase 7 — Write the Report

Structure:

```
### 🟢 What Is Working
[Table: Area | Status]

### 🔴 Bugs & Broken Connections
#### BUG N — [Short name] (severity: 🔴/🟡/🟢)
- What the spec says
- What the code actually does
- Impact (which features break, how silently)

### 🟡 Design Gaps / Missing Features
[Table: Gap | Plan Reference | Status]

### 🔵 Clarifying Questions
[Numbered list — ask about ambiguities that affect fix priority]
```

**Severity guide:**
- 🔴 = feature completely broken / silent data loss
- 🟡 = partially broken or degraded UX
- 🟢 = minor / cosmetic / future concern

---

## Verifying AI Agent Claims

When the subject of the audit is work claimed complete by another AI agent (Gemini, Codex, etc.), add these steps **before Phase 2**:

### Check supervisor / system logs first
```bash
# OpenClaw supervisor reports log agent failures with high detail
ls ~/.openclaw/workspace/system/hermes-supervisor/reports/ | sort | tail -5
grep -i "parse\|phase\|complete\|fail\|mcp" <latest-report>.md
```
Look for the pattern: *"emitted a confident completion summary after multiple unresolved tool/schema/env failures"* — this is a common failure mode. If found, treat every claim in the agent's report as unverified until you run the code yourself.

### Async SDK pitfalls
Some SDK methods that look synchronous are actually coroutines. Always try the call in a basic script and check the return type before iterating:

```python
# WRONG — silently produces TypeError: 'coroutine' object is not iterable
tools = [t.name for t in server.list_tools()]

# CORRECT — FastMCP.list_tools() is async
import asyncio
async def check():
    tools = await server.list_tools()
    return [t.name for t in tools]
asyncio.run(check())
```
This applies to FastMCP and any other async-first SDK (e.g., asyncpg, aiohttp clients).

### Grep false-positives from docstrings
When checking for banned patterns (e.g., raw `.is_relative_to()` calls), grep will match occurrences inside docstrings and comments:

```bash
# This incorrectly flags the docstring: """...replacement for Path.is_relative_to()..."""
grep -n "\.is_relative_to(" file.py

# Correct: filter out lines that are string/comment content
grep -n "\.is_relative_to(" file.py | grep -v '""".*is_relative_to\|#.*is_relative_to\|'"'"'.*is_relative_to'"'"
```
Always read the flagged line in context before reporting it as a defect.

### Test state corruption
Smoke tests that write to real project files (e.g., `project.json`) can corrupt state for subsequent tests in the same run. Symptoms: a conflict-detection test returns `success` when it should return `conflict` because a prior test wrote the key with the same value.

Fix pattern:
1. Use temp files or isolated test fixtures, not the live project root
2. Restore any modified files immediately after each sub-test
3. If a protected field was overwritten by a test, restore it before the next assertion:

```python
import json, pathlib
path = pathlib.Path('project.json')
data = json.loads(path.read_text(encoding='utf-8'))
if data.get('project_id') == 'test-artifact':
    data['project_id'] = 'original-value'
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
```

---

## Pitfalls

- **Silent failures are the worst bugs** — a 404 that the UI swallows, a glob that returns empty, a schema mismatch that produces `undefined` — these are harder to spot than crashes. Look for them specifically.
- **Read paths vs write paths** — a server may successfully *read* old-format files but *write* new-format files, creating a split. Check both.
- **`[PLANNED]` markers in interfaces** — these are legitimate gaps, not bugs. Separate them clearly from actual broken connections.
- **Don't fix while auditing** — the report is the deliverable. Propose fixes only after the user confirms scope and priority.
- **Ask clarifying questions at the end** — the audit will surface ambiguities about intent (is this a bug or a design decision?). Always end with a numbered question list.
