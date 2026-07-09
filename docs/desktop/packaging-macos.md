# macOS packaging pipeline (Gate B)

This is the CI-driven pipeline that turns PARSE into a downloadable, installable
macOS app: it freezes the Python backend into a self-contained runtime and
assembles a `.dmg` (and `.zip`) via electron-builder. Everything runs on a real
Apple-silicon macOS runner — the freeze needs the heavy ML stack installed, so
local builds are not the path here.

## What the pipeline does

1. Builds the React frontend (`npm run build` → `dist/`).
2. Installs the backend deps (`python/requirements.txt`) plus PyInstaller on
   Python 3.12 (3.13+ is blocked — `server.py` imports the stdlib `cgi` module).
3. Captures a deterministic dependency lock (`pip freeze`) from the real macOS
   build and uploads it as an artifact.
4. Freezes `python/server.py` into a **onedir** bundle at
   `dist/parse-backend/parse-backend` using `packaging/parse-backend.spec`.
5. Smoke-tests the frozen backend: launches it with `PARSE_DESKTOP=1
   PARSE_API_PORT=8799`, polls `GET /api/health` for up to 60s, and fails the
   job if it never becomes healthy. This proves the freeze actually runs.
6. Runs electron-builder (`desktop/electron-builder.yml`) to produce an
   **unsigned** arm64 `.dmg` + `.zip`, bundling the frozen backend under the
   app's `Contents/Resources/backend/`.

## How to trigger it

The workflow runs automatically on every push to the
`desktop-stage3-packaging-macos` branch, and can be run manually:

```bash
gh workflow run desktop-macos.yml
```

## Where the artifacts land

Uploaded as GitHub Actions build artifacts on the run:

- `parse-desktop-macos-arm64` — the `.dmg` and `.zip` installers.
- `requirements-lock-macos-py312` — `python/requirements.lock.macos-py312.txt`,
  the resolved dependency lock from the real macOS/py3.12 build.
- `frozen-backend-smoke-log` — stdout/stderr of the frozen backend's boot.

## Freeze strategy

- **onedir, not onefile.** onefile re-unpacks to a temp dir on every launch
  (slow) and routinely breaks torch/ctranslate2 dynamic-library resolution.
  onedir ships a real directory the Electron app can spawn directly.
- The spec uses `collect_all(...)` for the native-heavy stack (`torch`,
  `torchaudio`, `transformers`, `faster_whisper`, `ctranslate2`, `silero_vad`,
  `phonemizer`, `soundfile`, and their tokenizer/hub dependencies) and
  `collect_submodules(...)` for the first-party `python/` packages that are
  reached by dynamic dispatch (route modules, provider registries, MCP adapters).
- Missing hidden imports are expected on early CI runs. Add a package to
  `COLLECT_ALL_PACKAGES` or a module string to `EXTRA_HIDDEN_IMPORTS` in
  `packaging/parse-backend.spec` and re-push to iterate.
- Models are **not** bundled here. STT (Whisper) + IPA (wav2vec2) weights are a
  later increment.

## Known follow-up: wiring main.js to the frozen backend

`desktop/main.js` currently spawns `python3 python/server.py` from the repo. When
packaged, the frozen backend lives at:

```
${process.resourcesPath}/backend/parse-backend
```

Making `main.js` resolve and spawn that path (with `PARSE_DESKTOP=1` and an
ephemeral `PARSE_API_PORT`, and a `chdir` into the project/workspace so
`_project_root()` resolves) is a **deliberate stacked change** — it is not part
of this packaging PR because it must land on top of other in-flight main.js work.
Until that lands, the produced `.app` bundles the backend but the shell still
uses its dev/scaffold spawn path.

## Gate C TODO: signing + notarization

This pipeline produces an **unsigned** build (the workflow exports
`CSC_IDENTITY_AUTO_DISCOVERY=false` and no signing identity is referenced).
Code signing with a Developer ID certificate, `hardenedRuntime`, and Apple
notarization/stapling are Gate C and are intentionally out of scope here. A
Gate C follow-up adds the signing identity/secrets and the notarize step to
`desktop/electron-builder.yml` and this workflow.
