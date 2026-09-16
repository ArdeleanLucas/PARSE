---
name: hermes-profile-skill-sync
description: Sync selected Hermes profile-local skills from one profile to another with backups and post-sync verification.
version: 1.0.0
author: ParseGPT
license: MIT
metadata:
  hermes:
    tags: [hermes, skills, profiles, sync, backup, verification]
    related_skills: [hermes-agent]
---

# Hermes Profile Skill Sync

Use this skill when one Hermes profile needs the same local skills as another profile. Hermes skills can be profile-local under `~/.hermes/profiles/<name>/skills`, so a profile like `parse-builder` may not automatically inherit custom skills installed for `parse-gpt`.

## When to Activate

Activate this skill when:
- A user asks to pass skills from one Hermes agent/profile to another
- A target profile is missing custom local skills that exist in a source profile
- Two Hermes profiles need matched workflow guidance before parallel work

## Workflow

### Phase 1: Verify source and target profiles

**Steps:**
1. Run `hermes profile list` and confirm both profiles exist.
2. Inspect the target profile's installed skills with `hermes --profile <target> skills list`.
3. Check whether the relevant skill directories exist under:
   - `~/.hermes/profiles/<source>/skills`
   - `~/.hermes/profiles/<target>/skills`
4. Re-run `hermes --profile <target> skills list` before assuming any claim that a skill is missing; a running agent session may be stale even when the profile inventory is already correct.
5. For each target skill, determine whether it is missing or stale.

**Checks before moving on:**
- [ ] Source profile exists
- [ ] Target profile exists
- [ ] Target skill inventory was inspected
- [ ] Candidate skills to install/update are identified

### Phase 2: Diff the actual profile-local skill files

**Steps:**
1. Compare `SKILL.md` hashes between source and target for each candidate skill.
2. Treat `MISSING` on target as an install.
3. Treat differing hashes as an update.
4. Record the exact skill directories to sync.

**Checks before moving on:**
- [ ] Each candidate skill has a source path
- [ ] Install vs update status is known
- [ ] Hash comparison was captured before writing

### Phase 3: Back up stale target copies

**Steps:**
1. Create a timestamped backup root such as:
   - `~/.hermes/profiles/<target>/skills_backups/YYYYMMDD-HHMMSS-<slug>`
2. For each target skill directory that will be overwritten, copy the entire existing directory into the backup root.
3. Do not skip backups for updates just because the files are “only docs”; local skills are durable agent memory.

**Checks before moving on:**
- [ ] Backup root exists
- [ ] Every overwritten skill dir was copied
- [ ] Backup path is recorded for the final report

### Phase 4: Sync the skill directories

**Steps:**
1. Copy each selected skill directory from the source profile into the target profile with directory-level overwrite semantics.
2. Preserve the category path, e.g. `parse/...`, `software-development/...`, `workflows/...`.
3. Sync the whole skill directory, not just `SKILL.md`, in case the skill has linked files later.

**Checks before moving on:**
- [ ] All selected skill directories were copied
- [ ] Category paths were preserved
- [ ] No unrelated profile files were modified

### Phase 5: Re-verify target recognition and parity

**Steps:**
1. Re-run `hermes --profile <target> skills list` and confirm the synced skills are recognized.
2. Recompute hashes for the copied `SKILL.md` files.
3. Confirm source and target hashes now match for all selected skills.
4. Report installs, updates, and the backup snapshot path.

**Checks before completing:**
- [ ] Target profile lists the synced skills
- [ ] Hash parity is confirmed
- [ ] Backup path is included in the report
- [ ] Any logging/closeout requirements were completed

## Quality Checklist

Before completing this workflow:
- [ ] Verified that Hermes skill storage is profile-local for this task
- [ ] Backed up overwritten target skills
- [ ] Synced full skill directories, not partial files
- [ ] Re-verified with both skill listing and file-hash parity

## Example

### parse-gpt → parse-builder PARSE refactor handoff

A PARSE parallel-work setup required passing refactor skills from `parse-gpt` to `parse-builder`.

Observed result:
- `parse-builder` existed but lacked `parse-react-shell-refactor-planning`, `parse-react-shell-refactor-execution`, and `parse-repo-modular-refactor-planning`
- it also had stale copies of `parse-react-vite-pivot`, `parse-repo-state-cleanup`, `parse-pr-workflow`, and `dual-agent-parallel-development`
- the stale target copies were backed up under `~/.hermes/profiles/parse-builder/skills_backups/20260425-181803-parse-refactor-sync`
- after syncing, `hermes --profile parse-builder skills list` recognized all target skills and SHA256 parity checks matched the source profile

## Anti-patterns

Avoid these when using this skill:
- ❌ Assuming Hermes profiles automatically share local skills
- ❌ Overwriting target skills without a backup snapshot
- ❌ Copying only `SKILL.md` when the skill may later depend on linked files
- ❌ Claiming sync success without re-running `hermes --profile <target> skills list`

## Integration

This skill works well with:
- `hermes-agent`
- `daily-log-after-each-job`
