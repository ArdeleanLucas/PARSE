---
agent: parse-gpt
queued_by: lucas
queued_at: 2026-04-27
status: executing
---

# PARSE parity harness Round 2 coverage extension

## Goal
Extend `parity/harness/` from the Round 1 import/export scaffold to full Round 2 contract coverage.

## Required additions

- close every `allowlist.yaml` TODO with either implementation or an explicit permanent reason
- add canonicalization rules for float rounding, stable list sorting, UUID masking, path relativization, and timestamp masking
- add one sequential operation script per contract surface in the same fixture
- cover:
  - CSV concept import
  - speaker onboard
  - CLEF config + fetch
  - batch transcription run
  - LingPy + NEXUS export with cognate decisions made
  - tag merge
  - enrichment / lexeme note save-load
- add failure-mode assertions for:
  - invalid annotation save
  - missing speaker
  - malformed CLEF config
  - export with empty wordlist
- add sign-off template under `parity/harness/SIGNOFF.md`

## Acceptance target

A fresh `python -m parity.harness.runner` against oracle main vs rebuild main reports either zero unallowlisted diffs or a precise residual list traceable to real in-flight parity drift.
