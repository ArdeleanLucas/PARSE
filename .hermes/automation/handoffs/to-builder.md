# To parse-builder

Status: queued_after_pr26

Current instruction:
- Finish PR #27 first unless Lucas explicitly resequences you: https://github.com/TarahAssistant/PARSE-rebuild/pull/27
- Then do PR #26: https://github.com/TarahAssistant/PARSE-rebuild/pull/26
- After that, work from `.hermes/plans/2026-04-26-parse-builder-next-task-cognate-controls-save-hardening.md`.
- Keep this slice frontend-only and stay out of parse-back-end PR #23: https://github.com/TarahAssistant/PARSE-rebuild/pull/23

Grounded state:
- Current rebuild `origin/main`: `0d78bb8` — `test(compare): harden compute semantics regressions (#28)`
- Next queued Builder slice after PR #26: harden `src/components/compare/CognateControls.tsx` save semantics, remove the obsolete `enrichmentStore.save not yet implemented` fallback assumption, add regression tests, and keep the UI visually identical to the original (no UI re-imagining).
