---
agent: parse-gpt
queued_by: parse-gpt
queued_at: 2026-04-26T15:41:00Z
status: queued
related_prs:
  - 60
---

# Next task — baseline + scorecard + parity + handoff cleanup

## Goal
Close the outstanding coordinator-only documentation and parity gaps that issue/queue PR `#60` identified.

## Specific task
1. sign the Phase 0 baseline against current oracle/rebuild SHAs
2. publish a 2026-04-26 scorecard with independent axes
3. record the first Saha01 Annotate parity evidence pass
4. migrate queueing into `.hermes/handoffs/`

## Validation
- gate evidence committed under `.hermes/reports/`
- scorecard doc populated with concrete numbers
- parity evidence includes per-flow artifacts
- AGENTS + audit trail updated for the new handoff convention
