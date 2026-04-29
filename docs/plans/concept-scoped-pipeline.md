# Concept-Scoped Pipeline Contract and Lane Plan

**Status:** Active coordination contract for the concept-windowed / edited-only pipeline rerun lanes  
**Coordinator branch:** `docs/concept-scoped-pipeline-coordinator`  
**Backend branch:** `feat/concept-scoped-pipeline-backend`  
**Frontend branch:** `feat/concept-scoped-pipeline-frontend`  
**Context:** [PR #189](https://github.com/ArdeleanLucas/PARSE/pull/189) carries the preceding offset-wording and MCP `shiftedConcepts` work; this plan does not reopen that scope.

## Why this exists

PARSE needs a single locked contract for rerunning STT, ORTH, and IPA on concept-sized windows instead of whole-speaker audio. The user workflow is: retime a small set of concepts, then rerun the pipeline for all concept windows or only the concepts already marked as manually adjusted. This document freezes the shared request body, lane ownership, sequencing, terminology, and test surface so parse-back-end and parse-builder can implement in parallel without contract drift.

## Locked HTTP request-body contract

Pipeline endpoint request body uses **snake_case**:

```jsonc
{
  "speakers": [...],
  "steps": [...],
  "overwrites": {...},
  "refine_lexemes": true,
  "run_mode": "full" // "full" | "concept-windows" | "edited-only"
}
```

Contract rules:

- `run_mode` is optional for backward compatibility.
- When `run_mode` is omitted, the server must default to `"full"`.
- `"full"` preserves the current whole-speaker behavior.
- `"concept-windows"` runs the selected step set over concept-tier windows.
- `"edited-only"` runs the selected step set only over concept-tier rows where `manuallyAdjusted === true`.
- When `run_mode != "full"`, the response payload gains `affected_concepts`:
  a list of `{ concept_id: str, start: number, end: number }` for the concepts
  that were processed. The frontend uses this for scoped post-run refresh
  (PR #191 → `applyConceptScopedRefresh`); a missing or empty list falls back
  to a full annotation reload.
- When `run_mode === "full"` or absent, the response shape is unchanged from
  pre-#192 behavior (backwards-compatible).
- The field name is `run_mode` on the wire; frontend TypeScript may expose `runMode` internally, but must serialize to `run_mode`.
- This contract is locked by coordinator. If either implementation lane needs to revise it, the lane must request agreement in PR comments and wait for both lanes to acknowledge before changing the shared contract.

## Locked MCP / ChatToolSpec contract

`run_full_annotation_pipeline` remains the MCP-visible workflow entrypoint. Its tool spec must gain:

| Parameter | Shape | Required | Notes |
|---|---|---:|---|
| `run_mode` | enum: `"full"`, `"concept-windows"`, `"edited-only"` | No | Defaults to `"full"`; determines whether the run is whole-speaker or concept-scoped. |
| `concept_ids` | `list[str]` | No | Optional explicit scope for non-`"full"` modes. If omitted, `"concept-windows"` implies all concept-tier rows and `"edited-only"` implies the `manuallyAdjusted` subset. |

The tool description must be rewritten so `concept_list` / `concept_ids` is no longer described as reporting-only. Under this contract, concept scope is real execution scope.

## Terminology lock

- Use **concept** for per-row scope in docs, UI labels, request fields, test names, and PR descriptions.
- Use **cognate** only for cross-speaker clustering / `/api/compute/cognates` output.
- Do not introduce a new per-row `cognate` tag or property for this work.

## Lane ownership

| Lane | Branch / PR | Owner | Scope |
|---|---|---|---|
| Backend + MCP | `feat/concept-scoped-pipeline-backend` | parse-back-end | Python pipeline endpoint, compute-step run modes, short-clip helper extraction, workflow tool schema, MCP dispatch parity, public `parse_mcp` typings. |
| Frontend UI | `feat/concept-scoped-pipeline-frontend` | parse-builder / parse-front-end | Run-mode control in the transcription modal, edited-concepts preview, body serialization as `run_mode`, selective post-run refresh, Vitest coverage. |
| Coordination | `docs/concept-scoped-pipeline-coordinator` | parse-coordinator | This locked contract, sequencing, test-surface documentation, daily PR-status comments until both implementation PRs merge. |

Coordinator does not implement the backend or frontend work in this lane and does not push to either implementation branch.

## Sequencing

1. Backend can ship and merge first once its tests and schema surface are green.
2. Frontend can open as Draft at any time against the locked request body.
3. Frontend must not merge until the backend PR is green and merged, because end-to-end behavior depends on the server honoring `run_mode`.
4. If the frontend PR opens before backend merge, keep its PR body explicit that it is UI/serialization work pending backend support.
5. Coordinator posts one status comment per day on the coordinator PR until both implementation PRs merge: backend `mergeStateStatus`, frontend `mergeStateStatus`, and contract-drift `yes` / `no`.
6. If contract drift appears, coordinator comments on both implementation PRs and tags Lucas before either lane merges.
7. No agent merges any of these PRs; Lucas retains merge control.

## Required backend / MCP test surface

Backend implementation should be test-first for the new modes. Expected tests:

- `python/test_compute_speaker_stt_concept_windows.py` — `run_mode='concept-windows'` processes concept-tier windows and writes STT results into matching concept rows only.
- `python/test_compute_speaker_ipa_concept_windows.py` — `run_mode='concept-windows'` processes concept-tier windows and writes IPA results into matching concept rows only.
- `python/test_compute_speaker_ortho_refine_lexemes.py` — extend existing ORTH short-clip coverage to prove the shared helper preserves current ORTH behavior.
- `python/test_compute_speaker_*_edited_only.py` — edited-only mode processes only concept-tier rows with `manuallyAdjusted === true`.
- `python/test_compute_speaker_*_edited_only_empty_no_op.py` — edited-only mode with no edited concepts returns a structured no-op and does not start a job.
- Existing `run_mode='full'` coverage remains green and unchanged.
- `python/adapters/test_mcp_adapter.py` — MCP dispatch parity proves `run_mode` and `concept_ids` reach `run_full_annotation_pipeline` intact and parameter schema exposure includes both fields.
- `python/packages/parse_mcp/tests` — public package typings round-trip the workflow input shape with `run_mode` and `concept_ids`.

## Required frontend test surface

Frontend implementation should cover the UI and serialization contract without screenshots:

- `TranscriptionRunModal` renders the run-mode radio / segmented control.
- In `"concept-windows"` and `"edited-only"` modes, the ORTH-only `Refine lexemes` checkbox is hidden and the whole-file `Normalize` step is hidden or disabled.
- In `"edited-only"` mode, the preview list renders manually adjusted concept rows in the documented format:
  - `#{conceptId} "{conceptName}" {start.toFixed(3)}–{end.toFixed(3)}s`
- In `"edited-only"` mode with no manually adjusted concepts, Confirm is disabled and the UI shows `No manually edited concepts on this speaker.`
- `useBatchJobStart` forwards `run_mode` for each run mode.
- A mocked selective-rerun completion event refreshes only affected concept rows; unaffected rows must not re-render.

## Drift checks

A lane has contract drift if it changes any of the following without coordinator agreement:

- request-body field name away from `run_mode`
- enum values away from `"full"`, `"concept-windows"`, `"edited-only"`
- default away from `"full"` when omitted
- endpoint response shape
- MCP entrypoint name `run_full_annotation_pipeline`
- MCP parameter names `run_mode` or `concept_ids`
- terminology from concept-scoped reruns to per-row cognates

Daily coordinator comments should report drift as `contract-drift: no` unless one of the above is observed in a lane diff.

## Amendment history

- 2026-04-29: added affected_concepts to the response contract. The original
  contract (PR #190) under-specified the response side; both implementation
  lanes (PR #191 frontend, PR #192 backend) shipped consistent with each other,
  so this is a doc-correction with no code drift.
