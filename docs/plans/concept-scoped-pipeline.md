# Concept-Scoped Pipeline Contract and Shipped Status

- **Status:** Shipped on `main` for concept-windowed / edited-only pipeline reruns
- **Coordinator docs:** PR #190 and PR #193
- **Frontend implementation:** PR #191
- **Backend + MCP implementation:** PR #192
- **Language-safety follow-up:** PR #196
- **Context:** PR #189 carries the preceding offset-wording and MCP `shiftedConcepts` work; that behavior is also shipped.

## Why this exists

PARSE needs a stable contract for rerunning STT, ORTH, and IPA on concept-sized windows instead of whole-speaker audio. The user workflow is: retime a small set of concepts, then rerun the pipeline for all concept windows or only the concepts already marked as manually adjusted. This document is now the shipped contract reference rather than an active multi-lane coordination plan. After PR #215, scoped row refresh is explicitly advisory: compute completion must still trigger a speaker-annotation reload from disk so persisted IPA/ORTH/STT/BND intervals become canonical in the UI.

## Shipped HTTP request-body contract

Pipeline endpoint request body uses **snake_case**:

```jsonc
{
  "speakers": [...],
  "steps": [...],
  "overwrites": {...},
  "refine_lexemes": true,
  "run_mode": "full", // "full" | "concept-windows" | "edited-only"
  "concept_ids": ["1", "2"] // optional, only meaningful for non-full modes
}
```

Contract rules:

- `run_mode` is optional for backward compatibility.
- When `run_mode` is omitted, the server defaults to `"full"`.
- `"full"` preserves whole-speaker behavior.
- `"concept-windows"` runs the selected step set over concept-tier windows.
- `"edited-only"` runs the selected step set only over concept-tier rows where `manuallyAdjusted === true`.
- `concept_ids` optionally narrows non-`"full"` runs; if omitted, `"concept-windows"` implies all concept-tier rows and `"edited-only"` implies the manually adjusted subset.
- When `run_mode != "full"`, the response payload includes `affected_concepts`: a list of `{ concept_id: str, start: number, end: number }` for the concepts processed. The frontend uses this for scoped post-run refresh (`applyConceptScopedRefresh`); a missing or empty list falls back to a full annotation reload.
- When `run_mode === "full"` or is absent, the response shape remains backwards-compatible with pre-#192 behavior.
- `edited-only` with no matching edited concepts returns a structured no-op (`no_op: true`, `jobId: null`, `affected_concepts: []`) instead of starting an empty background job.
- The field name is `run_mode` on the wire; frontend TypeScript may expose `runMode` internally, but must serialize to `run_mode`.

## Shipped MCP / ChatToolSpec contract

`run_full_annotation_pipeline` remains the MCP-visible workflow entrypoint and now exposes:

| Parameter | Shape | Required | Notes |
|---|---|---:|---|
| `run_mode` | enum: `"full"`, `"concept-windows"`, `"edited-only"` | No | Defaults to `"full"`; determines whether the run is whole-speaker or concept-scoped. |
| `concept_ids` | `list[str]` | No | Optional explicit scope for non-`"full"` modes. |

Under this contract, concept scope is real execution scope. `concept_ids` is not reporting-only metadata.

## Language and prompt-safety contract

PR #196 tightened the ORTH/STT behavior for concept-window short clips:

- PARSE does **not** seed Whisper with English concept IDs or gloss labels as `initial_prompt` for concept-window clips; after PR #216, those clips may still inherit the built-in Southern Kurdish Arabic-script ORTH decoder prime unless the config explicitly sets `"initial_prompt": ""`.
- Transcription language resolves from payload first, then `annotation.metadata.language_code`.
- If neither source supplies language, PARSE warns to stderr before allowing Whisper auto-detect.
- The resolved ORTH language applies to full/concept-window ORTH and short-clip refine calls.

## Terminology lock

- Use **concept** for per-row scope in docs, UI labels, request fields, test names, and PR descriptions.
- Use **cognate** only for cross-speaker clustering / `/api/compute/cognates` output.
- Do not introduce a per-row `cognate` tag or property for this work.

## Shipped lane summary

| Lane | PR | Owner | Shipped scope |
|---|---|---|---|
| Coordination | [#190](https://github.com/ArdeleanLucas/PARSE/pull/190), [#193](https://github.com/ArdeleanLucas/PARSE/pull/193) | parse-coordinator | Locked contract, sequencing, response-contract amendment, worktree docs. |
| Frontend UI | [#191](https://github.com/ArdeleanLucas/PARSE/pull/191) | parse-front-end | Run-mode control in `TranscriptionRunModal`, edited-concepts preview, body serialization as `run_mode`, selective post-run refresh, Vitest coverage. |
| Backend + MCP | [#192](https://github.com/ArdeleanLucas/PARSE/pull/192) | parse-back-end | Python pipeline endpoint run modes, compute-step concept windows, workflow tool schema, MCP dispatch parity, public `parse_mcp` typings. |
| Safety follow-up | [#196](https://github.com/ArdeleanLucas/PARSE/pull/196) | parse-back-end | Removed English prompt seeding and added payload/annotation language fallback. |

## Regression surfaces to preserve

Backend / MCP:

- `python/test_compute_speaker_stt_concept_windows.py`
- `python/test_compute_speaker_ipa_concept_windows.py`
- `python/test_compute_speaker_ortho_refine_lexemes.py`
- `python/test_compute_speaker_ortho_concept_windows_initial_prompt.py`
- `python/test_compute_speaker_ortho_language_fallback.py`
- `python/test_compute_speaker_stt_language_fallback.py`
- `python/test_server_compute_offset_http.py`
- `python/adapters/test_mcp_adapter.py`
- `python/packages/parse_mcp/tests/test_workflow_typings.py`

Frontend:

- `src/components/shared/__tests__/TranscriptionRunModal.test.tsx`
- `src/hooks/__tests__/useBatchPipelineJob.test.ts`
- `src/hooks/__tests__/useParseUIPipeline.test.ts`

## Drift checks

A future PR has contract drift if it changes any of the following without a coordinator doc update:

- request-body field name away from `run_mode`
- enum values away from `"full"`, `"concept-windows"`, `"edited-only"`
- default away from `"full"` when omitted
- response field `affected_concepts`
- no-op shape for empty `edited-only` runs
- MCP entrypoint name `run_full_annotation_pipeline`
- MCP parameter names `run_mode` or `concept_ids`
- terminology from concept-scoped reruns to per-row cognates

## Amendment history

- 2026-04-29 PR #190: created the locked coordinator contract.
- 2026-04-29 PR #191: shipped frontend run-mode UI/serialization/selective refresh.
- 2026-04-29 PR #192: shipped backend/MCP/public-package support.
- 2026-04-29 PR #193: added `affected_concepts` to the response contract after confirming both implementation lanes shipped consistently.
- 2026-04-29 PR #196: removed English concept/gloss `initial_prompt` seeding and added metadata-language fallback for safer short-clip transcription.
- 2026-04-30 PR #215: made scoped row refresh advisory; every completed compute still reloads the speaker annotation from disk so persisted tier writes remain canonical.
- 2026-04-30 PR #216: added the built-in Southern Kurdish Arabic-script ORTH decoder prime for omitted `initial_prompt` configs while preserving explicit empty-string opt-out.
- 2026-04-30 PR #217: made the frontend run preview mode-aware for IPA so concept-window / edited-only cells can be runnable despite stale full-mode `ipa.can_run=false` when ORTH/concept-tier presence is observable.
