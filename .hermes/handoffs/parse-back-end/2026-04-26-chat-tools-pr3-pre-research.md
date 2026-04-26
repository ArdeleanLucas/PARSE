---
agent: parse-back-end
queued_by: parse-gpt
queued_at: 2026-04-26
status: completed-pre-research
related_prs:
  - 59
  - 68
  - 83
  - 91
  - 93
  - 95
---

# chat_tools PR 3 pre-research — offset / import / memory bundles

## TL;DR

Post-PR-91 `python/ai/chat_tools.py` is **4850 LoC** on rebuild `origin/main` (`b561475`). The PR 3 family is much larger than the older rough estimate suggested: the **spec blocks + handlers + family-local helpers total ~1925 gross lines** before adding back thin wrappers/imports. A single `import_tools.py` would be **~956 gross lines** and is not reviewable. The most honest implementation plan is **3 implementation PRs** using **4 modules**:

1. **PR 3A** — `tag_import_tools.py` + `memory_tools.py` (combined gross ~599; lowest risk)
2. **PR 3B** — `speaker_import_tools.py` (gross ~630; highest side-effect risk, but coherent)
3. **PR 3C** — offset family in one PR, preferably as **two modules** inside that PR:
   - `offset_detection_tools.py`
   - `offset_apply_tools.py`

If Lucas insists on exactly `offset_tools.py`, `import_tools.py`, `memory_tools.py`, the grounded line map says that shape is less reviewable than the split above.

## Working environment

```bash
$ pwd
/home/lucas/gh/tarahassistant/PARSE-rebuild

$ git remote -v
origin  git@github.com:TarahAssistant/PARSE-rebuild.git (fetch)
origin  git@github.com:TarahAssistant/PARSE-rebuild.git (push)
```

PR-create reminder for this lane:

```bash
gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...
```

## Ground truth checked first

- **PR #91 merged** at `55f8226` into rebuild `main`
- current rebuild `origin/main` while researching: `b561475`
- **PR #93 merged** and is the operative handoff source
- current `chat_tools.py` line count:
  - `4850`

## Target tools and exact post-PR-91 line map

### Spec lines in `python/ai/chat_tools.py`

| Tool | Spec lines | Spec LoC |
|---|---:|---:|
| `detect_timestamp_offset` | 532-559 | 28 |
| `detect_timestamp_offset_from_pair` | 560-602 | 43 |
| `apply_timestamp_offset` | 603-716 | 114 |
| `import_tag_csv` | 717-738 | 22 |
| `prepare_tag_import` | 739-818 | 80 |
| `onboard_speaker_import` | 819-886 | 68 |
| `import_processed_speaker` | 887-953 | 67 |
| `parse_memory_read` | 954-979 | 26 |
| `parse_memory_upsert_section` | 980-1026 | 47 |

### Handler lines in `python/ai/chat_tools.py`

| Tool | Handler lines | Handler LoC |
|---|---:|---:|
| `detect_timestamp_offset` | 2817-2931 | 115 |
| `detect_timestamp_offset_from_pair` | 2933-3057 | 125 |
| `apply_timestamp_offset` | 3168-3239 | 72 |
| `import_tag_csv` | 3928-4055 | 128 |
| `prepare_tag_import` | 4057-4134 | 78 |
| `import_processed_speaker` | 4397-4514 | 118 |
| `onboard_speaker_import` | 4516-4636 | 121 |
| `parse_memory_read` | 4679-4751 | 73 |
| `parse_memory_upsert_section` | 4753-4840 | 88 |

## Helper coupling audit

### Offset family helpers

| Helper | Lines | LoC | Used by |
|---|---:|---:|---|
| `_annotation_path_for_speaker` | 3241-3248 | 8 | all 3 offset tools |
| `_collect_offset_anchor_intervals` | 3250-3282 | 33 | `detect_timestamp_offset` |
| `_shift_annotation_intervals` | 3284-3334 | 51 | `apply_timestamp_offset` |
| `_format_offset_detect_payload` | 3059-3133 | 75 | both detect tools |
| `_find_concept_interval` | 3135-3166 | 32 | `detect_timestamp_offset_from_pair` |

**Assessment:** strongly cohesive. These should move with the offset family.

**Special note:** `detect_timestamp_offset` keeps an in-handler import of `compare.offset_detect` pieces. Preserve that local import pattern in the extracted module so optional import failures still surface as `ChatToolExecutionError` with the same message shape.

### Tag import helpers

| Helper | Lines | LoC | Used by |
|---|---:|---:|---|
| `_load_project_concepts` | 3890-3907 | 18 | `import_tag_csv`, `prepare_tag_import`, processed-import concept reconciliation |

**Assessment:** small and safe. Can move into tag-import module if speaker-import also imports it from the new module, or leave it on `ParseChatTools` if you want to minimize cross-module imports.

**Important coupling note:** `import_tag_csv` currently ends by calling `self._tool_prepare_tag_import(...)`. After extraction, it should call the shared module helper directly — analogous to the `stt_word_level_start -> tool_stt_start()` rule from PR 2.

### Speaker import helpers

| Helper | Lines | LoC | Used by |
|---|---:|---:|---|
| `_display_readable_path` | 3909-3914 | 6 | speaker import + memory tools |
| `_resolve_onboard_source` | 4140-4164 | 25 | `onboard_speaker_import`, `import_processed_speaker` |
| `_resolve_processed_json_source` | 4166-4172 | 7 | `import_processed_speaker` |
| `_resolve_processed_csv_source` | 4174-4180 | 7 | `import_processed_speaker` |
| `_extract_concepts_from_annotation` | 4182-4268 | 87 | `import_processed_speaker` |
| `_write_concepts_csv` | 4270-4288 | 19 | `import_processed_speaker` |
| `_write_project_json_for_processed_import` | 4290-4331 | 42 | `import_processed_speaker` |
| `_write_source_index_for_processed_import` | 4333-4395 | 63 | `import_processed_speaker` |

**Assessment:** this is the heaviest side-effect cluster in the remaining monolith. It is still coherent as one speaker-import family, but it is **not** review-honest to cram it together with tag import inside one `import_tools.py`.

### Memory helpers

| Helper | Lines | LoC | Used by |
|---|---:|---:|---|
| `_memory_normalize_heading` | 4642-4644 | 3 | both memory tools |
| `_memory_match_section` | 4646-4652 | 7 | both memory tools |
| `_memory_split_sections` | 4654-4669 | 16 | both memory tools |
| `_memory_read_raw` | 4671-4677 | 7 | both memory tools |
| `_display_readable_path` | 3909-3914 | 6 | memory + speaker import |

**Assessment:** very self-contained aside from the tiny `_display_readable_path` overlap. Either:
- keep `_display_readable_path` on `ParseChatTools` and let the module call `tools._display_readable_path(...)`, or
- introduce a tiny shared utility later if duplication becomes annoying.

## Grounded module sizing

These are **gross** sizes = specs + handlers + family-local helpers, before subtracting wrapper replacements in `chat_tools.py`.

| Candidate module / family | Spec | Handlers | Helpers | Gross total |
|---|---:|---:|---:|---:|
| `offset` family | 185 | 312 | 199 | **696** |
| `tag_import` family | 102 | 206 | 18 | **326** |
| `speaker_import` family | 135 | 239 | 256 | **630** |
| `memory` family | 73 | 161 | 39 | **273** |
| hypothetical single `import_tools.py` | — | — | — | **956** |

## Recommendation: implementation shape

### Recommended modules

- `python/ai/tools/tag_import_tools.py`
  - `import_tag_csv`
  - `prepare_tag_import`
- `python/ai/tools/speaker_import_tools.py`
  - `onboard_speaker_import`
  - `import_processed_speaker`
- `python/ai/tools/memory_tools.py`
  - `parse_memory_read`
  - `parse_memory_upsert_section`
- `python/ai/tools/offset_detection_tools.py`
  - `detect_timestamp_offset`
  - `detect_timestamp_offset_from_pair`
- `python/ai/tools/offset_apply_tools.py`
  - `apply_timestamp_offset`

### Why not exactly `offset_tools.py` / `import_tools.py` / `memory_tools.py`?

Because the grounded post-PR-91 numbers say:
- `import_tools.py` would be **~956 gross lines** → not reviewable
- `offset_tools.py` would be **~696 gross lines** → above the soft ceiling

That means the old rough heuristic from PR #93 (`4850 -> ~4150`) is now clearly too conservative / too coarse for planning. The family footprint is larger than it looked before the post-PR-91 audit.

## Recommended PR sequence

### PR 3A — `tag_import_tools.py` + `memory_tools.py`

**Why first:** combined gross size is about **599**, right at the review ceiling but still honest; behavior is lower-risk than speaker import and offset mutation.

Move:
- `import_tag_csv`
- `prepare_tag_import`
- `parse_memory_read`
- `parse_memory_upsert_section`
- family-local helpers (`_memory_*`; likely `_load_project_concepts`)

Special rule:
- `import_tag_csv` should call the extracted `tool_prepare_tag_import(...)` helper directly, not `self._tool_prepare_tag_import(...)`.

### PR 3B — `speaker_import_tools.py`

**Why second:** highest side-effect risk (copies files, mutates `source_index.json`, `project.json`, `concepts.csv`, and imported annotations).

Move:
- `onboard_speaker_import`
- `import_processed_speaker`
- their helper family

Honest note:
- gross size is **~630**, slightly above the soft ceiling. That is still acceptable **if** the PR stays narrowly scoped to this one family and you avoid incidental cleanup.

### PR 3C — offset family

**Why third:** the offset family is coherent but still substantial. Keep it in one PR, but split the module shape internally for reviewability.

Move:
- `detect_timestamp_offset`
- `detect_timestamp_offset_from_pair`
- `apply_timestamp_offset`
- their helper family

Recommended internal split:
- `offset_detection_tools.py`
- `offset_apply_tools.py`

If Lucas strongly prefers a single `offset_tools.py`, flag honestly in the PR body that the module lands at **~696 gross lines**.

## Test surface map

### Existing tests already covering the PR 3 family

#### Offset family
- `python/test_offset_manual_pairs.py`
  - direct coverage for `detect_timestamp_offset_from_pair`
- `python/test_offset_apply_protected.py`
  - direct coverage for `apply_timestamp_offset`
  - also checks the `manuallyAdjusted` protection behavior
- `python/adapters/test_mcp_adapter.py`
  - safety metadata for `apply_timestamp_offset`

#### Memory family
- `python/ai/test_parse_memory_tool.py`
  - direct coverage for `parse_memory_read`
  - direct coverage for `parse_memory_upsert_section`
- `python/ai/test_chat_turn_priming.py`
  - integration coverage because `parse-memory.md` is auto-injected into chat turn priming

#### Speaker import family
- `python/ai/test_parse_memory_tool.py`
  - despite the filename, this file already contains direct tests for:
    - `onboard_speaker_import`
    - `import_processed_speaker`
  - this is a coupling smell in the current test layout, but it does mean behavior is pinned already
- `python/adapters/test_mcp_adapter.py`
  - safety metadata assertions for both write tools

### Current coverage gaps to close in implementation

#### Tag import family — biggest gap
There is **no dedicated direct unit suite** for:
- `import_tag_csv`
- `prepare_tag_import`

Current visibility is mostly indirect / adapter-level. Add a new direct test file, e.g.:
- `python/ai/tools/test_tag_import_tools.py`

#### Bundle parity guard for PR 3
Add:
- `python/ai/test_chat_tool_bundle_extract_pr3.py`

It should mirror PR 1 / PR 2 parity tests and assert:
- exported name sets == spec keys
- exported name sets == handler keys
- extracted tool names still appear in `ParseChatTools(...).tool_names()`

#### Duplicate-spec guard update
Extend:
- `python/adapters/test_mcp_adapter.py::test_no_duplicate_tool_specs_or_handlers`

to include the PR 3 tools, especially:
- `detect_timestamp_offset`
- `detect_timestamp_offset_from_pair`
- `apply_timestamp_offset`
- `prepare_tag_import`
- `onboard_speaker_import`
- `parse_memory_read`
- `parse_memory_upsert_section`

## MCP / contract notes

All 9 PR 3 tools are currently in `DEFAULT_MCP_TOOL_NAMES`, and these 6 are write-allowed:
- `apply_timestamp_offset`
- `import_tag_csv`
- `prepare_tag_import`
- `onboard_speaker_import`
- `import_processed_speaker`
- `parse_memory_upsert_section`

That means PR 3 is **not** an internal-only refactor. The MCP/default surface must stay stable:
- tool names unchanged
- metadata unchanged
- default MCP count unchanged at **36**

## Honest LoC expectation

The old rough estimate in PR #93 (`4850 -> ~4150`) is too conservative once you actually map the file.

Grounded post-PR-91 footprint:
- gross candidate family total ≈ **1925 lines**
- wrappers/imports will stay in `chat_tools.py`, so the net drop will be smaller
- but the net reduction is still likely **well above** the older 600–800 heuristic

Conservative expectation:
- **substantial** monolith reduction, likely far below `4150`
- exact endpoint depends on how much of the helper family stays on `ParseChatTools`

Practical planning takeaway:
- choose module boundaries for reviewability first
- do **not** anchor implementation planning to the older `~4150` guess

## Suggested implementation-file checklist

Expected new files across the PR 3 execution sequence:
- `python/ai/tools/tag_import_tools.py`
- `python/ai/tools/speaker_import_tools.py`
- `python/ai/tools/memory_tools.py`
- `python/ai/tools/offset_detection_tools.py`
- `python/ai/tools/offset_apply_tools.py`
- `python/ai/test_chat_tool_bundle_extract_pr3.py`
- `python/ai/tools/test_tag_import_tools.py`
- `python/ai/tools/test_speaker_import_tools.py`
- `python/ai/tools/test_memory_tools.py`
- `python/ai/tools/test_offset_tools.py` (or split by detection/apply)

## Validation to require during implementation

At minimum for the implementation PR(s):

```bash
PYTHONPATH=python python3 -m pytest python/ -q
npm run test -- --run
./node_modules/.bin/tsc --noEmit
git diff --check
```

Also keep the runtime smoke from PR 2:
- branch-local `/docs`
- browser console clean
- `/api/mcp/exposure`
- `/api/mcp/tools`
- confirm MCP count stays `36`

## Bottom line

PR 3 is ready for implementation planning, but the grounded line map says the honest shape is:
- **3 implementation PRs**
- **4–5 extracted modules**
- start with **tag import + memory**
- isolate **speaker import**
- keep **offset detection/apply** together at the PR level but likely split at the module level
