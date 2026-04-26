# parse-back-end handoff — ORTH runtime contract reconciliation

Use this PR as the task source.

Primary brief:
- `.hermes/plans/2026-04-26-parse-back-end-next-task-ortho-contract.md`

Short version:
- current runtime already hard-requires a local CT2 `ortho.model_path`
- tracked config/docs/script surfaces still describe the old HF-repo-id / VAD-off behavior
- preserve the current runtime policy
- reconcile `config/ai_config.example.json`, ORTH docs, and `scripts/generate_ortho.py`
- stay non-overlapping with PR #42 worktree cleanup and Builder PRs #41 / #43
