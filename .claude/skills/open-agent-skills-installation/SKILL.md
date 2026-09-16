---
name: open-agent-skills-installation
description: Install third-party open-agent skills from GitHub repos for Codex/OpenClaw, verify what a repo actually contains before installing, and confirm the canonical saved paths.
version: 1.0.0
author: ParseGPT
license: MIT
metadata:
  hermes:
    tags: [skills, codex, openclaw, github, installation, verification]
    related_skills: [codex, hermes-agent, github-repo-management]
---

# Open Agent Skills Installation

Use this skill when a user asks you to save or install skills from an external repository such as `vercel-labs/*` or another GitHub-hosted open-agent skills pack.

## Why this skill exists

External skill repos are inconsistent. Some repos are true skill packs; others are the CLI/tooling repo plus only one bundled skill. Do not assume the linked repo contains the domain skills the user expects.

## When to Activate

Activate this skill when:
- A user asks you to "save skills" or "install skills" from a GitHub repository
- You need those skills available to Codex, OpenClaw, or other open-agent-compatible runtimes
- The user expects React/TypeScript/domain skills and the linked repo may not actually be the best pack

## Workflow

### Phase 1: Inspect the source before installing

1. Use the skills CLI to list what the repo actually exposes:
   ```bash
   npx --yes skills add <repo-url-or-owner/repo> --list
   ```
2. If needed, clone or inspect the repo to confirm where `SKILL.md` files actually live.
3. Do not promise React/TypeScript/domain skills until the listing confirms them.

**Checks before moving on:**
- [ ] You know the exact skill names available in the linked repo
- [ ] You know whether the linked repo is a real skill pack or mostly tooling/CLI code

### Phase 2: Choose the correct installation target

1. Prefer global installation when the user wants the skills available for future work across projects:
   ```bash
   npx --yes skills add <repo> -g -a codex -a openclaw --skill '*' -y
   ```
2. If the linked repo is not the pack the user probably wanted, install the exact requested repo **and** the practical companion pack if it materially matches the intended domain.
3. Keep the scope narrow: install only skills, do not modify the target codebase.

**Checks before moving on:**
- [ ] Installation scope matches the request (usually global)
- [ ] Relevant agents are specified explicitly
- [ ] You have not touched the application repo itself

### Phase 3: Verify the saved inventory and paths

1. List the global skill inventory:
   ```bash
   npx --yes skills ls -g --json
   ```
2. Verify canonical storage and symlink behavior. In this environment, canonical copies are stored under:
   - `~/.agents/skills/`
   - OpenClaw commonly symlinks from `~/.openclaw/skills/` back into `~/.agents/skills/`
3. Verify representative paths with Python or shell:
   ```bash
   python3 - <<'PY'
   import os
   from pathlib import Path
   for p in [
       Path('/home/lucas/.agents/skills/find-skills'),
       Path('/home/lucas/.openclaw/skills/find-skills'),
   ]:
       print(p, p.exists(), p.is_symlink())
       if p.is_symlink():
           print('->', os.readlink(p))
   PY
   ```
4. Note that Codex may consume the universal `~/.agents/skills/` path without creating duplicates under `~/.codex/skills/`.

**Checks before finishing:**
- [ ] `skills ls -g --json` shows the installed skills
- [ ] At least one canonical `~/.agents/skills/...` path exists
- [ ] At least one OpenClaw symlink target resolves correctly when applicable

## Practical heuristics

- Always run `--list` first on unfamiliar repos.
- If the user links `vercel-labs/skills`, expect the repo to be primarily the **skills CLI** plus the bundled `find-skills` skill.
- If the user actually wants React-oriented Vercel skills, inspect/install `vercel-labs/agent-skills` as the practical companion pack.
- Use `--skill '*'` only after you have confirmed the repository contents are safe and relevant.

## Example

### Example: user asks to save Vercel and Lynx skills for future PARSE work

1. Inspect:
   ```bash
   npx --yes skills add https://github.com/vercel-labs/skills --list
   npx --yes skills add https://github.com/lynx-community/skills --list
   ```
2. Findings:
   - `vercel-labs/skills` exposed only `find-skills`
   - `lynx-community/skills` exposed 7 skills, including `lynx-typescript`
3. Install:
   ```bash
   npx --yes skills add https://github.com/vercel-labs/skills -g -a codex -a openclaw --skill '*' -y
   npx --yes skills add https://github.com/lynx-community/skills -g -a codex -a openclaw --skill '*' -y
   npx --yes skills add vercel-labs/agent-skills -g -a codex -a openclaw --skill '*' -y
   ```
4. Verify with `npx --yes skills ls -g --json` and path checks under `~/.agents/skills/` and `~/.openclaw/skills/`.

## Anti-patterns

Avoid these mistakes:
- ❌ Assuming a linked repo contains the domain skills the user expects
- ❌ Installing before checking `--list`
- ❌ Claiming Codex/OpenClaw install locations without verifying the filesystem
- ❌ Turning a skills-only request into application code changes

## Closeout

After successful installation:
1. Summarize exactly which skills were saved
2. State where they were saved
3. Mention any course correction taken because the linked repo differed from expectations
4. Update daily logs if this was part of a substantial task
