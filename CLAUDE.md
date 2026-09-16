# PARSE

Phonetic Analysis & Review Source Explorer. Browser workstation for linguistic
fieldwork: React + Vite front end in `src/`, Python backend in `python/`,
desktop packaging in `desktop/`.

Read `AGENTS.md` first. It holds the repo-target rule, the MC lane workflow and
the review conventions. This file only adds pointers.

## Commands

- `npm run check` (tsc), `npm test` (vitest), `npm run test:api`
- Python side: `pyproject.toml` and `run-parse.sh`

## Skills

- `.claude/skills/` holds the PARSE-specific agent skills: MC tasks, spec vs
  implementation audit, daily log, Whisper and CUDA fixes, WSL notes. They were
  moved here from the global Claude Code skills folder on 2026-09-16. Some
  describe the old WSL machine and may be stale; verify paths before relying on
  them.
- MCP tool docs live in `docs/agent-skills/parse-mcp-tools/`.
