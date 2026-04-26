# parse-back-end handoff — post-PR49 lexeme-notes + spectrogram/search HTTP bundle

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-back-end-next-task-post-pr47-lexeme-media-search-http-bundle.md`

Short version:
- PR #49 is the active parse-back-end implementation lane
- the next parse-back-end task after that is the backend-only **lexeme-notes + spectrogram/search HTTP** bundle
- extract the remaining inline lexeme/media/search routes from `python/server.py` into app-layer HTTP helpers
- preserve current multipart/query/binary response semantics
- add dedicated backend route-level tests and keep OpenAPI honest
- stay backend-only and non-overlapping with PRs #49, #48, #42, #41, #43, and #36
