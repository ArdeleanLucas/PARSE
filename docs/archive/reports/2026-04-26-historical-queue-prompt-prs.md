> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../..).

# Historical queue-prompt PR audit trail — 2026-04-26

This migration started from an estimate that there were "about 10" historical queue-prompt PRs. The grounded audit found a larger coordinator queue trail:

- **Merged queue/handoff/coordinator docs PRs:** 8
- **Closed stale/superseded queue/handoff docs PRs:** 18
- **Open old-pattern queue PRs at migration time:** 3 (`#58`, `#59`, `#60`)

The point of this index is to preserve that history while moving future queueing into `.hermes/handoffs/`.

## Merged queue / handoff PRs

| PR | Title | Intended lane | Outcome |
|---|---|---|---|
| #9 | `docs: add parse-builder stage2 offset workflow prompt` | parse-builder | followed by implementation PR `#11` |
| #10 | `docs: add parse-back-end first build prompt` | parse-back-end | followed by implementation PR `#12` |
| #15 | `docs: add three-lane health coordination note` | parse-gpt | coordinator topology note during the 2026-04-26 merge wave |
| #17 | `docs: refresh parse-builder next task prompt` | parse-builder | followed by implementation PR `#19` |
| #18 | `docs: add parse-back-end next task prompt` | parse-back-end | followed by implementation PR `#21` |
| #22 | `docs: add parse-builder compute-mode audit handoff` | parse-builder | followed by implementation PR `#24` |
| #25 | `docs: add parse-builder BorrowingPanel handoff` | parse-builder | fed the later compare-contract cleanup chain (`#34`, `#38`) |
| #45 | `docs: queue Builder post-PR36 compute contract bundle` | parse-builder | followed by implementation PR `#50` |

## Closed stale / superseded queue PRs

These were useful at the time, but they no longer represent the correct live queue state.

| PR | Title | Intended lane | Final state |
|---|---|---|---|
| #5 | `docs: add parse-builder stage1 handoff prompt` | parse-builder | closed stale |
| #6 | `docs: add ParseGPT next external API slice prompt` | parse-gpt | closed stale |
| #16 | `docs: add parse-builder next task prompt` | parse-builder | superseded by newer Builder handoff |
| #20 | `docs: add parse-back-end backend health handoff v2` | parse-back-end | superseded by later backend queueing |
| #23 | `docs: parse-back-end prompt for contract parity` | parse-back-end | closed stale |
| #26 | `docs: add queued Builder configStore handoff` | parse-builder | consumed by later bundled frontend cleanup |
| #30 | `docs: Builder prompt for original UI parity audit` | parse-builder | superseded by refreshed parity prompts |
| #32 | `docs: add Builder compare contract bundle handoff` | parse-builder | superseded by current-main cleanup |
| #35 | `docs: add parse-back-end tags/export bundle handoff` | parse-back-end | superseded by later HTTP extraction work |
| #36 | `docs: queue Builder decisions contract follow-up` | parse-builder | superseded by subsequent Builder follow-ups |
| #37 | `docs: queue parse-back-end CLEF HTTP bundle` | parse-back-end | superseded by later backend slices |
| #42 | `docs: queue parse-back-end worktree hygiene cleanup` | parse-back-end | closed maintenance-only prompt |
| #44 | `docs: queue parse-back-end ORTH contract reconciliation` | parse-back-end | superseded by implementation PR `#46` |
| #47 | `docs: queue parse-back-end post-PR46 compute-offset HTTP bundle` | parse-back-end | superseded by later backend queueing |
| #48 | `docs: queue Builder post-PR45 actions-menu contract bundle` | parse-builder | superseded by later Builder queueing |
| #51 | `docs: queue parse-back-end post-PR49 lexeme-media-search HTTP bundle` | parse-back-end | consumed by implementation PR `#54` |
| #53 | `docs: queue parse-builder post-PR52 compare/config cleanup bundle` | parse-builder | superseded by newer Builder tasks |
| #56 | `docs: queue parse-back-end post-PR54 speech HTTP bundle` | parse-back-end | consumed by implementation PR `#57` |

## Open old-pattern queue PRs at migration time

| PR | Title | Intended lane | Migration action |
|---|---|---|---|
| #58 | `docs: queue parse-builder next task — ParseUI.tsx structural cracks` | parse-builder | copied into `.hermes/handoffs/parse-builder/2026-04-26-parseui-structural-cracks.md` |
| #59 | `docs: queue parse-back-end next task — chat_tools.py decomposition` | parse-back-end | copied into `.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-decomposition.md` |
| #60 | `docs: queue parse-gpt next task — sign baseline, score progress, clean coordination` | parse-gpt | copied into `.hermes/handoffs/parse-gpt/2026-04-26-baseline-scorecard-parity-handoff-cleanup.md` and superseded by the four coordinator execution PRs |
