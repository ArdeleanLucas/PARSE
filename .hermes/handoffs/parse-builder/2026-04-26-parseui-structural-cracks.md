---
agent: parse-builder
queued_by: parse-gpt
queued_at: 2026-04-26T15:41:00Z
status: queued
related_prs:
  - 58
  - 61
---

# Next task — ParseUI structural cracks

## Goal
Reduce `src/ParseUI.tsx` further without changing workstation behavior.

## Why this is next
`ParseUI.tsx` is still 4,404 LoC on rebuild current-main and remains one of the largest frontend pressure points.

## Grounded context
- rebuild current-main: `f9aa3db1aad1d77078c9105cd8b5e5254c066338`
- oracle current-main: `0951287a812609068933ba22711a8ecd97765f38`
- open implementation PR at queue time: `#61` (`refactor(parseui): extract AI chat panel`)

## Specific task
Work the next behavior-preserving extraction slices from `ParseUI.tsx` with paired tests, keeping UI parity with the oracle React workstation.

## Validation
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `npm run build`
- browser smoke for Annotate / Compare / Tags / AI chat
