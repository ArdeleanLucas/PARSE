# MC-363 — Concept-windows ORTH 95% UI stall

## Problem

When the user runs full-pipeline ORTH with `run_mode=concept-windows`, the UI
header pill freezes on **"ORTHO concept window N/N — 95%"** for 10–20 minutes
even though the worker is doing real work the entire time. Only after a long
silence does it jump straight to **"Pipeline complete — 100%"**.

Empirical timeline from a Khan03 / 271-window run captured during diagnosis:

```
18:36:07Z  ORTHO concept window 271/271     progress=95.0
            ── 16m 28s of silence ──
18:52:35Z  Pipeline complete                 progress=99.0
18:52:35Z  Released job resource lock        progress=100.0
18:52:35Z  Compute complete                  progress=100.0
```

Root cause: after the per-window inference loop in
`_run_step_on_concept_windows` finishes,
`_compute_speaker_ortho_concept_windows` runs Tier-2 forced alignment over
all matched windows via `_align_partial_ortho_words` →
`_ortho_tier2_align_to_words` → `ai.forced_align.align_segments`. That call
chain has no progress emission and on thesis-corpus WAVs takes the better
part of 20 minutes.

The frontend keeps polling `/api/jobs/active` and
`/api/compute/full_pipeline/status` at 1Hz (correctly — the job IS still
running) so the access log fills with thousands of identical lines and the
UI looks frozen. Job state and results are correct on completion; the bug
is purely observability.

## Fix

Two coordinated changes:

1. **`align_segments` now accepts a `progress_callback`** (`Optional[Callable[[int, int], None]]`).
   The callback fires once per segment with `(done, total)`. Any exception
   raised by the callback is swallowed — progress is observability-only and
   must not abort alignment.

2. **`_compute_speaker_ortho_concept_windows` rebudgets the bar** so the
   silent Tier-2 phase has visible progress headroom:

   | Phase | Old | New |
   |---|---|---|
   | Per-window inference loop | 10% → 95% | 10% → 70% |
   | Tier-2 alignment announcement | (none) | 70% "Aligning ortho_words (Tier-2)" |
   | Per-segment Tier-2 ticks | (none) | 70% → 90% (callback-driven) |
   | Annotation write | (none) | 92% "Writing annotation" |
   | Concept-windows complete | (none) | 95% "ORTH concept-windows complete (N/M)" |
   | Pipeline complete (full_pipeline tail) | 99% | 99% (unchanged) |

   `_run_step_on_concept_windows` gained a `progress_max: float = 95.0`
   keyword so other callers (STT / IPA concept-windows, which have no
   Tier-2 follow-up) keep their historical 95% cap; only the ORTH callsite
   passes `progress_max=70.0`.

The progress callback is plumbed through:

```
_compute_speaker_ortho_concept_windows
  └─ _align_partial_ortho_words(progress_callback=…)
       └─ _ortho_tier2_align_to_words(progress_callback=…)
            └─ align_segments(progress_callback=…)   ← per-segment tick
```

## Verification

| Gate | Result |
|---|---|
| `pytest python/ai/test_forced_align.py python/server_routes/test_annotate_compute_pad.py …` | 26 passed |
| `pytest python/` (full backend) | 1371 passed |
| `python3 -m py_compile` on changed files | clean |
| `git diff --check` | clean |

New tests assert RED→GREEN behavior:

- `test_align_segments_emits_progress_callback_per_segment` — verifies
  `(1,3),(2,3),(3,3)` ticks for a 3-segment input.
- `test_align_segments_progress_callback_exceptions_are_swallowed` — a
  raising callback does not abort alignment.
- `test_run_step_on_concept_windows_honors_progress_max` — when
  `progress_max=70.0` is passed, the loop's max emission is ≤70.0.
- `test_compute_speaker_ortho_concept_windows_emits_tier2_and_write_progress` —
  the loop end, Tier-2 announcement, per-segment ticks, write phase, and
  final 95% concept-windows-complete event all fire in order with the
  expected percentages.

## Out of scope

- Reducing frontend poll cadence. The 1Hz polling is independently
  reasonable; the visible problem was the frozen pill, which this PR fixes.
  WS streaming exists for `job.progress` but the FE doesn't subscribe yet —
  that's a follow-up.
- IPA / STT concept-windows progress budgets are unchanged. They have no
  silent Tier-2 follow-up; their 10..95% per-window envelope is fine.
