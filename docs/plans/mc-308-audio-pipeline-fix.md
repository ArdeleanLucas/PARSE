# MC-308: Fix audio/working symlink — restore proper copy+normalize pipeline

- **Status:** Completed for MC-308 scope; release gates still pending
- **Assignee:** @parse-builder
- **Blocks:** C5 (export verification), C6 (browser regression), C7 (legacy cleanup)
- **Priority:** Critical — data safety violation

> Execution note (2026-04-14): the live `audio/working` repair and speaker rebuild shipped in PR #43. A later review pass removed the temporary symlink-guard code and kept only the canonical `.wav` working-output helper, so this document now records the final merged scope. It does **not** claim C5/C6 signoff; those remain separate manual gates.

---

## 1. Problem

`audio/working` is a symlink pointing to the raw source recordings:

```
audio/working → /mnt/c/Users/Lucas/Thesis/Audio_Original
```

This means the "working" directory IS the originals. PARSE's data pipeline
assumes a strict separation:

```
audio/original/<Speaker>/   ← read-only source copies staged into the project
audio/working/<Speaker>/    ← normalized working copies (16-bit PCM, mono, 44.1kHz, -16 LUFS)
```

### What breaks

1. **Normalization overwrites originals.** `normalize_audio.py` reads from
   `audio/original/` and writes to `audio/working/`. With the symlink,
   writing to `audio/working/Fail01/` writes directly into
   `Audio_Original/Fail01/` — the irreplaceable field recordings.

2. **LUFS adjustment same problem.** The two-pass ffmpeg loudnorm pipeline
   in both `normalize_audio.py` and `server.py` (`_run_normalize_job`)
   writes output to `audio/working/<Speaker>/`. The symlink makes this
   destructive.

3. **Safety guards don't catch it.** `normalize_audio.py` line 287–290
   checks `source_path.resolve() == output_path.resolve()` and
   `path_is_within(output_path, original_root)`, but `audio/original/`
   resolves to a different path than `Audio_Original/`, so neither guard
   triggers.

4. **Only 1 of 6 speakers was properly staged.** `audio/original/` contains
   only `Mand01` (copied manually). The other 5 annotated speakers
   (Fail01, Fail02, Kalh01, Qasr01, Saha01) have annotations but their
   audio is served directly from `Audio_Original/` via the symlink.

### Current state

```
audio/
├── original/
│   └── Mand01/          ← only speaker properly staged (2 WAVs + CSV)
│       ├── Mand_M_1962_01.wav  (2.2 GB)
│       ├── Mand_M_1962_02.wav  (2.5 GB)
│       └── Mandali_M_1900_01 - Kaso Solav.csv
└── working → /mnt/c/Users/Lucas/Thesis/Audio_Original   ← SYMLINK (wrong)

annotations/             ← 6 speakers have annotation JSON files
├── Fail01.json
├── Fail02.json
├── Kalh01.json
├── Mand01.json
├── Qasr01.json
└── Saha01.json

source_index.json        ← references audio/working/<Speaker>/<file>.wav paths
```

### Source recordings on disk

All raw audio lives at `/mnt/c/Users/Lucas/Thesis/Audio_Original/`:

| Speaker | WAV file | Size |
|---------|----------|------|
| Fail01 | `Faili_M_1984.wav` | 3.3 GB |
| Fail02 | `SK_Faili_F_1968.wav` | 1.5 GB |
| Kalh01 | `Kalh_M_1981.wav` | 4.0 GB |
| Mand01 | `Mand_M_1962_01.wav` + `Mand_M_1962_02.wav` | 4.7 GB |
| Qasr01 | `Qasrashirin_M_1973.wav` | 7.2 GB |
| Saha01 | `Sahana_F_1978.wav` | 2.9 GB |

**Total copy size:** ~23.6 GB (originals into `audio/original/`)  
**Total working size:** ~23.6 GB (normalized copies in `audio/working/`)  
**Total disk needed:** ~47 GB additional

Each speaker also has one or more CSV files (Adobe Audition marker exports)
alongside the WAV in `Audio_Original/`.

---

## 2. Intended data flow

```
/mnt/c/Users/Lucas/Thesis/Audio_Original/<Speaker>/recording.wav
    │
    │  (1) cp — stage into project
    ▼
parse/audio/original/<Speaker>/recording.wav       ← read-only project copy
    │
    │  (2) normalize_audio.py — two-pass ffmpeg loudnorm
    ▼
parse/audio/working/<Speaker>/recording.wav        ← normalized working copy
    │                                                  16-bit PCM, mono, 44.1kHz, -16 LUFS
    │  (3) PARSE runtime reads from here
    ▼
source_index.json paths → waveform peaks → STT → annotations
```

Both `audio/original/` and `audio/working/` are gitignored (confirmed in
`.gitignore`: the line `audio` excludes the entire directory).

---

## 3. Execution plan

### Step 1: Remove the symlink

```bash
cd /home/lucas/gh/ardeleanlucas/parse
rm audio/working          # removes symlink only, not target
mkdir -p audio/working    # create real directory
```

**Verify:** `ls -la audio/` should show `working` as a directory, not a symlink.

### Step 2: Stage source audio into `audio/original/`

Copy each speaker's WAV and CSV files from `Audio_Original/` into the
project's `audio/original/<Speaker>/` directory. Mand01 is already staged.

```bash
SOURCE=/mnt/c/Users/Lucas/Thesis/Audio_Original

# Fail01
mkdir -p audio/original/Fail01
cp "$SOURCE/Fail01/Faili_M_1984.wav" audio/original/Fail01/
cp "$SOURCE/Fail01/Faili_M_1984.csv" audio/original/Fail01/

# Fail02
mkdir -p audio/original/Fail02
cp "$SOURCE/Fail02/SK_Faili_F_1968.wav" audio/original/Fail02/
cp "$SOURCE/Fail02/Faili_F_1968.csv" audio/original/Fail02/

# Kalh01
mkdir -p audio/original/Kalh01
cp "$SOURCE/Kalh01/Kalh_M_1981.wav" audio/original/Kalh01/
cp "$SOURCE/Kalh01/Kalhori_M_1900_01 - Kaso Solav.csv" audio/original/Kalh01/

# Mand01 — already staged, verify
ls -lh audio/original/Mand01/

# Qasr01
mkdir -p audio/original/Qasr01
cp "$SOURCE/Qasr01/Qasrashirin_M_1973.wav" audio/original/Qasr01/
cp "$SOURCE/Qasr01/Qasrashirin_M_1973_01 - Kaso Solav.csv" audio/original/Qasr01/

# Saha01
mkdir -p audio/original/Saha01
cp "$SOURCE/Saha01/Sahana_F_1978.wav" audio/original/Saha01/
cp "$SOURCE/Saha01/Sahana_F_1978_01 - Kaso Solav.csv" audio/original/Saha01/
```

**Time estimate:** 20–40 minutes for ~19 GB across WSL ↔ Windows filesystem.

**Verify:** Each `audio/original/<Speaker>/` should contain the WAV and CSV.
Checksums optional but recommended:

```bash
for spk in Fail01 Fail02 Kalh01 Mand01 Qasr01 Saha01; do
  echo "=== $spk ==="
  ls -lh audio/original/$spk/
done
```

### Step 3: Run normalization

Use `normalize_audio.py` to create proper working copies:

```bash
# Verify ffmpeg is available
ffmpeg -version

# Normalize all staged speakers
python python/normalize_audio.py --all --base-dir .

# Or one at a time if you want to monitor:
python python/normalize_audio.py --speaker Fail01 --base-dir .
python python/normalize_audio.py --speaker Fail02 --base-dir .
python python/normalize_audio.py --speaker Kalh01 --base-dir .
python python/normalize_audio.py --speaker Mand01 --base-dir .
python python/normalize_audio.py --speaker Qasr01 --base-dir .
python python/normalize_audio.py --speaker Saha01 --base-dir .
```

**Time estimate:** 5–15 minutes per speaker depending on file size and
whether ffmpeg runs as a Windows .exe or WSL native binary. The script
handles wslpath conversion automatically.

**Expected output:** `audio/working/<Speaker>/<file>.wav` — normalized to:
- 16-bit PCM (`s16`)
- Mono (`-ac 1`)
- 44.1 kHz (`-ar 44100`)
- -16 LUFS (two-pass loudnorm with `linear=true`)

**Verify:**

```bash
for spk in Fail01 Fail02 Kalh01 Mand01 Qasr01 Saha01; do
  echo "=== $spk ==="
  ls -lh audio/working/$spk/
done
```

### Step 4: Update `source_index.json`

The existing `source_index.json` references `audio/working/<Speaker>/<file>.wav`
paths. If the normalized filenames match the originals (they should — same
base name, `.wav` extension), the paths should still resolve correctly.

**Verify:**

```bash
python3 -c "
import json
with open('source_index.json') as f:
    data = json.load(f)
from pathlib import Path
for spk, info in data['speakers'].items():
    for wav in info['source_wavs']:
        p = Path(wav['filename'])
        exists = p.exists()
        print(f'{\"OK\" if exists else \"MISSING\"}: {wav[\"filename\"]}')
"
```

If Mand01's filename changed (it was `Mandali_M_1900_01.wav` in
source_index but the original files are `Mand_M_1962_01.wav` and
`Mand_M_1962_02.wav`), update the source_index entry manually or
re-run `python/source_index.py`.

### Step 5: Keep canonical working output paths

Keep one shared helper for the behavior that remains useful after the repair:

```python
def build_normalized_output_path(source_path: Path, working_dir: Path) -> Path:
    return working_dir / source_path.with_suffix(".wav").name
```

This ensures both normalization entry points still write canonical working
copies as `.wav`, even when the staged source recording was `.mp3` or `.flac`.

### Step 6: Verify end-to-end

1. **Start PARSE:** `parse-run` or manual launch
2. **Load a speaker in Annotate mode** — waveform should render from
   the normalized working copy
3. **Play audio** — verify playback works (range requests from
   `audio/working/<Speaker>/<file>.wav`)
4. **Check annotation alignment** — existing annotation timestamps should
   still match the audio (normalization preserves timing, only adjusts
   amplitude)
5. **Check Compare mode** — concept × speaker matrix should load with
   audio playback working across speakers
6. **Spot-check non-WAV sources** — if a staged source was `.mp3`/`.flac`,
   confirm the working copy is still emitted as `.wav`

---

## 4. Code changes (PR scope)

The data operations (Steps 1–4) are manual and happen on the local machine.
The final PR contains only the code changes that remained justified after review:

| File | Change |
|------|--------|
| `python/audio_pipeline_paths.py` | Shared `build_normalized_output_path()` helper |
| `python/server.py` | Use canonical `.wav` output-path helper in normalize jobs |
| `python/normalize_audio.py` | Use canonical `.wav` output-path helper in CLI normalization |

The temporary symlink-guard code was removed in the final cleanup pass because
it addressed a one-time setup mistake rather than an ongoing runtime feature.

---

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Disk space (~47 GB needed) | Check available space before copying: `df -h .` |
| Copy time across WSL ↔ Windows boundary | Budget 20–40 min; can run in background |
| Normalization changes audio timing | ffmpeg loudnorm preserves timing — only amplitude changes. Annotation timestamps remain valid |
| `source_index.json` path mismatch after rename | Verify in Step 4; regenerate with `source_index.py` if needed |
| Mand01 has different filenames in original vs source_index | `source_index.json` says `Mandali_M_1900_01.wav` but `audio/original/Mand01/` has `Mand_M_1962_01.wav` — may need source_index update |
| Existing annotations reference old audio paths | Annotations reference speaker names, not full paths — should be unaffected |

---

## 6. MC-308 completion criteria

- [x] `audio/working` is a real directory, not a symlink
- [x] All 6 annotated speakers have WAVs in `audio/original/<Speaker>/`
- [x] All 6 speakers have normalized WAVs in `audio/working/<Speaker>/`
- [x] `source_index.json` paths resolve to existing files
- [x] PARSE serves audio correctly (waveform renders, playback works)
- [x] Annotation timestamps still align with audio after normalization
- [x] Both normalization entry points write canonical `.wav` working copies
- [x] The stale backup symlink has been retired from the live thesis runtime

## 7. External gates still pending

- C5 LingPy export verification remains a separate manual gate.
- C6 full browser regression remains a separate manual gate.
- C7 cleanup and legacy deletion stay blocked until C5 and C6 are explicitly cleared.
