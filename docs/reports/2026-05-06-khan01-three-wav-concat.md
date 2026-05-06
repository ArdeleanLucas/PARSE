# Khan01 three-WAV concat working audio and re-import

- Date: 2026-05-06 parse-back-end execution
- Handoff: `.hermes/handoffs/parse-back-end/2026-05-06-khan01-three-wav-concat.md`
- Related PRs: [PR #278](https://github.com/ArdeleanLucas/PARSE/pull/278), [PR #279](https://github.com/ArdeleanLucas/PARSE/pull/279), [PR #280](https://github.com/ArdeleanLucas/PARSE/pull/280)
- Repo worktree: `/home/lucas/gh/worktrees/khan01-three-wav-concat`
- Live workspace: `/home/lucas/parse-workspace`
- Live API used for verification: `http://127.0.0.1:8866` (`parse-run` was already serving the current stack on alternate ports; `127.0.0.1:8766` was idle/refusing connections)

## Why

PR #279 surfaced that Khan01 had playable intervals only up to the end of the current working WAV:

```text
source_audio: audio/working/Khan01/REC00002.wav
source_audio_duration_sec: 8590.524014
concept intervals: 286
concept start range: 1271.844 -> 12665.391
past-EOA concept intervals: 102
```

The source manifest times extend beyond `REC00002.wav`, so Khan01 needed a working WAV that covers the manifest timeline. This report records the workstation-side data mutation; the repository diff is documentation-only.

## Inputs

Source WAVs under `/mnt/c/Users/Lucas/Thesis/Audio_Original/Khan01_missing/`:

| Order | File | ffprobe duration | Size |
|---:|---|---:|---:|
| 1 | `2023043001.wav` | `5214.693500s` | `2002449858` bytes |
| 2 | `20230502_khanaqini_01_02.wav` | `4325.248000s` | `1660902786` bytes |
| 3 | `REC00002.wav` | `8590.524000s` | `1237035628` bytes |
|  | sum | `18130.465500s` |  |

Manifest inspected:

```text
/mnt/c/Users/Lucas/Thesis/Audio_Processed/Khan01_process/Khan01_manifest.json
manifest items observed: 286
manifest max audio_start: 12665.391000s
manifest max audio_start + duration: 12666.575000s
source-duration sum covers manifest: true
```

Note: the handoff text described the manifest as 288 items / 286 with transcriptions. The file present during execution exposed 286 `items`; the imported annotation also has 286 concept intervals. No manifest timestamps or interval timestamps were edited.

## Pre-checks

Current canonical repo state before mutation:

```text
repo HEAD:   141b1e7
origin/main: 141b1e7
PR #278 present on main: true
PR #280 present on main: true
```

Live continuity before mutation:

```text
/api/config speaker count: 10
/api/annotations/Khan01 source_audio: audio/working/Khan01/REC00002.wav
/api/annotations/Khan01 source_audio_duration_sec: 8590.524014
/api/annotations/Khan01 concept intervals: 286
/api/annotations/Khan01 past-EOA concept intervals: 102
concepts.csv SHA256: ca44d952914b0a2e9f0ff5786862867f15dffb3f166e325fba3c52dfcf942279
```

## Backup

Backup directory created before any workspace mutation:

```text
/home/lucas/parse-workspace/annotations/backups/20260506T075618Z-khan01-three-wav-concat/
```

The handoff's basename-only `cp` pattern would collide because both `annotations/Khan01.json` and `peaks/Khan01.json` have the same basename. To keep rollback unambiguous, this execution wrote `BACKUP_MANIFEST_UNAMBIGUOUS.json` and preserved these unique backup files:

```text
annotations-Khan01.json                 2016551 bytes
annotations-Khan01.parse.json           2016551 bytes
source_index.json                          6021 bytes
project.json                                546 bytes
concepts.csv                              16231 bytes
peaks-Khan01.json                       8074696 bytes
audio-working-Khan01-REC00002.wav    757684296 bytes
```

## Concat build

Staging directory:

```text
/tmp/khan01-concat-20260506T075618Z/
```

Each input was normalized to the PARSE working format before concat:

```text
ffmpeg -i <source> -ar 44100 -ac 1 -c:a pcm_s16le <staged-normalized-file>
ffmpeg -f concat -safe 0 -i concat-list.txt -c:a pcm_s16le -ar 44100 -ac 1 Khan01_concat.wav
```

Resulting concat WAV:

```text
/tmp/khan01-concat-20260506T075618Z/Khan01_concat.wav
bytes: 1599107138
frames: 799553530
duration: 18130.465533s (302.174 min)
format: 44100 Hz, mono, PCM 16-bit
manifest max end: 12666.575000s
covers manifest: true
```

The bulky intermediate normalized files under `/tmp/khan01-concat-20260506T075618Z/normalized/` were deleted after successful import; the staged concat WAV and peaks JSON were retained temporarily as evidence.

## Anchor sanity

The handoff requested three RMS probes. Results at the exact timestamps:

| Anchor | Timestamp | Result |
|---|---:|---:|
| ONE | `1271.844s` | `LOW`, RMS `7.273` |
| JBIL 183 | `8803.690s` | `OK`, RMS `62.283` |
| Last item | `12665.000s` | `LOW`, RMS `16.111` |

Neighborhood scan over +/- 5 seconds in 0.5-second steps:

| Anchor | Best offset | Best RMS | Windows > 50 RMS |
|---|---:|---:|---:|
| ONE | `-5.0s` | `13.705` | `0 / 21` |
| JBIL 183 | `+1.0s` | `83.341` | `9 / 21` |
| Last item | `+5.0s` | `155.116` | `8 / 21` |

Per the handoff, low anchor RMS is non-blocking and should be interpreted as a place for Lucas to listen/nudge if needed. This execution did not perform any timestamp alignment edits.

## Re-import

Staged annotation JSON:

```text
/tmp/khan01-concat-20260506T075618Z/Khan01.json
source_audio: audio/working/Khan01/Khan01_concat.wav
source_audio_duration_sec: 18130.465533
concept intervals: 286
```

Fresh peaks JSON was generated with the repo `python/peaks.py` script:

```text
/tmp/khan01-concat-20260506T075618Z/Khan01.peaks.json
sample_rate=44100
pixels=1561628
bytes=11645707
```

`ParseChatTools.execute("import_processed_speaker", ...)` dry-run result:

```text
ok: true
audioDest: audio/working/Khan01/Khan01_concat.wav
annotationDest: annotations/Khan01.json
peaksDest: peaks/Khan01.json
transcriptDest: imports/legacy/Khan01/Khan01_transcriptions.csv
plan conceptCount: 281
```

The dry-run count is the number of unique importable concept IDs, not the number of intervals. The staged annotation had:

```text
concept intervals: 286
unique non-empty concept IDs: 281
missing concept IDs: 0
duplicate concept-id groups: 5
```

Duplicate groups explaining the 286 -> 281 difference:

```text
287: my wife / wife
290: my son / son
295: sister / sister
614: grass / grass
615: river / river
```

Apply result:

```text
ok: true
message: Speaker 'Khan01' imported from processed artifacts.
plan conceptCount: 281
root conceptCount after merge: 617
```

Post-import manual workspace edits allowed by the handoff:

```text
audio/working/Khan01/REC00002.wav removed: yes
source_index.json Khan01 source_wavs pruned to one primary entry:
  audio/working/Khan01/Khan01_concat.wav
```

## Live API verification after import

```text
/api/config speaker count: 10
/api/annotations/Khan01 source_audio: audio/working/Khan01/Khan01_concat.wav
/api/annotations/Khan01 source_audio_duration_sec: 18130.465533
/api/annotations/Khan01 concept intervals: 286
/api/annotations/Khan01 past-EOA concept intervals: 0
```

On-disk artifact verification:

```text
audio/working/Khan01/Khan01_concat.wav exists: true
audio/working/Khan01/Khan01_concat.wav format: 44100 Hz, mono, PCM 16-bit
audio/working/Khan01/REC00002.wav exists: false
annotations/Khan01.json source_audio: audio/working/Khan01/Khan01_concat.wav
annotations/Khan01.parse.json source_audio: audio/working/Khan01/Khan01_concat.wav
annotations/Khan01.json concept intervals: 286
annotations/Khan01.parse.json concept intervals: 286
source_index.json source_wavs count for Khan01: 1
```

`concepts.csv` stayed byte-identical through the import:

```text
before: ca44d952914b0a2e9f0ff5786862867f15dffb3f166e325fba3c52dfcf942279
after:  ca44d952914b0a2e9f0ff5786862867f15dffb3f166e325fba3c52dfcf942279
unchanged: true
```

## Regression validation

PR #278 import-tool regression:

```bash
cd /home/lucas/gh/worktrees/khan01-three-wav-concat
PARSE_PORT=18766 BLOCK_LIVE_PROCESS_ISOLATION=1 PYTHONPATH=python \
  python3 -m pytest -xvs python/ai/tools/test_speaker_import_tools.py
```

Result:

```text
15 passed, 1 warning in 0.20s
```

PR #276 API regression, run against the actual live API port exposed by current `parse-run`:

```bash
cd /home/lucas/gh/worktrees/khan01-three-wav-concat
PARSE_API_BASE_URL=http://127.0.0.1:8866 \
  npx vitest run --config vitest.integration.ts src/__tests__/apiRegression.test.ts
```

Result:

```text
Test Files  1 passed (1)
Tests       27 passed (27)
```

## Rollback path

Use the unambiguous backup manifest and files in:

```text
/home/lucas/parse-workspace/annotations/backups/20260506T075618Z-khan01-three-wav-concat/BACKUP_MANIFEST_UNAMBIGUOUS.json
```

Rollback outline:

1. Stop any active write jobs against Khan01.
2. Restore the uniquely named backup files to their original paths:
   - `annotations-Khan01.json` -> `/home/lucas/parse-workspace/annotations/Khan01.json`
   - `annotations-Khan01.parse.json` -> `/home/lucas/parse-workspace/annotations/Khan01.parse.json`
   - `source_index.json` -> `/home/lucas/parse-workspace/source_index.json`
   - `project.json` -> `/home/lucas/parse-workspace/project.json`
   - `concepts.csv` -> `/home/lucas/parse-workspace/concepts.csv`
   - `peaks-Khan01.json` -> `/home/lucas/parse-workspace/peaks/Khan01.json`
   - `audio-working-Khan01-REC00002.wav` -> `/home/lucas/parse-workspace/audio/working/Khan01/REC00002.wav`
3. Remove `/home/lucas/parse-workspace/audio/working/Khan01/Khan01_concat.wav` if rolling back fully.
4. Re-probe `/api/annotations/Khan01` and `/api/config`.

Do not hand-edit interval timestamps as part of rollback. Timestamp drift correction remains out of scope for this PR.

## Out of scope

- Per-interval timestamp drift correction.
- Khan04 source identification or import.
- Backend code changes.
- Frontend/UI changes. PR #279's banner logic is unchanged; the API state now drives Khan01's past-EOA count to zero.
