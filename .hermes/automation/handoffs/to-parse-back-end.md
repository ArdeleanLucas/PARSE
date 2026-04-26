# parse-back-end handoff — post-PR54 speech HTTP bundle

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-back-end-next-task-post-pr54-speech-http-bundle.md`

Short version:
- this is the next backend-only successor task after the active parse-back-end implementation PR #54
- ship one fresh implementation PR from current `origin/main`
- extract the still-inline speech/annotation-assist HTTP cluster from `python/server.py`
- cover:
  - `GET /api/stt-segments/{speaker}`
  - `POST /api/normalize`
  - `POST /api/normalize/status`
  - `POST /api/stt`
  - `POST /api/stt/status`
  - `POST /api/suggest`
- preserve job-id aliasing, source-wav aliasing, callback-url pass-through, 200-empty STT cache behavior, and suggestion fallback semantics
- add direct app-layer tests plus thin server-wrapper regressions
- stay backend-only and non-overlapping with PR #54 and the active Builder lanes
