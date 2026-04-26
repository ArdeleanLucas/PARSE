# To parse-builder

Status: queued_next

Current instruction:
- Finish the current Builder slice in PR #25 first unless Lucas explicitly resequences you.
- Then work from `.hermes/plans/2026-04-26-parse-builder-next-task-configstore-update.md`.
- Keep this next slice frontend-only and stay out of parse-back-end PR #23: https://github.com/TarahAssistant/PARSE-rebuild/pull/23

Grounded state:
- Current rebuild `origin/main`: `5cf12ca` — `feat(compare): make compute payload semantics explicit (#24)`
- Current Builder task PR: https://github.com/TarahAssistant/PARSE-rebuild/pull/25
- Next queued Builder slice: implement `src/stores/configStore.ts::update()` using the existing typed `updateConfig()` client helper, remove the stale stub/TODO, and add regression tests.
