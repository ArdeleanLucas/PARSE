# Runtime Paths Foundation (MC-247)

## Purpose

This change introduces an **isolated runtime path/config foundation** for future desktop packaging (Electron + local Python backend), without changing current runtime behavior.

No existing execution path is wired to these helpers yet.

---

## Why this is needed

During backend/config inspection, the current codebase still contains path assumptions that are fine for local repo usage but fragile for packaged desktop apps:

- `python/server.py` resolves project files from `Path.cwd()` (`_project_root()`), so behavior depends on launch directory.
- `python/ai/provider.py` defaults to config via `Path(__file__).resolve().parents[2] / "config" / "ai_config.json"`.
- Core files (`parse-enrichments.json`, `source_index.json`, `config/*.json`) are currently assumed under the repo root.
- Historical scripts/docs include machine-specific absolute examples (e.g., `C:/...`).

For packaged macOS/Windows/Linux apps, runtime state should live in user app directories, not in hardcoded/repo-relative locations.

---

## New files

### 1) `python/shared/app_paths.py`

Cross-platform directory resolver for:

- `data_dir`
- `config_dir`
- `cache_dir`
- `log_dir`
- `models_dir`
- `temp_dir`

It provides:

- `AppPaths` dataclass (resolved directories + helpers)
- `PathOverrides` dataclass (optional overrides)
- `resolve_app_paths(...)`
- `load_env_path_overrides(...)`
- `path_overrides_from_mapping(...)`
- `merge_path_overrides(...)`

#### Platform defaults (when no overrides are set)

- **Windows**
  - Config: `%APPDATA%/<Org>/<App>/config`
  - Data/cache/logs: `%LOCALAPPDATA%/<Org>/<App>/{data|cache|logs}`
- **macOS**
  - Data/config: `~/Library/Application Support/<App>/{data|config}`
  - Cache: `~/Library/Caches/<App>`
  - Logs: `~/Library/Logs/<App>`
- **Linux (XDG)**
  - Data: `$XDG_DATA_HOME/<app_slug>` (fallback `~/.local/share/<app_slug>`)
  - Config: `$XDG_CONFIG_HOME/<app_slug>` (fallback `~/.config/<app_slug>`)
  - Cache: `$XDG_CACHE_HOME/<app_slug>` (fallback `~/.cache/<app_slug>`)
  - Logs: `$XDG_STATE_HOME/<app_slug>/logs` (fallback `~/.local/state/<app_slug>/logs`)

`models_dir` defaults to `<data_dir>/models` (or `<runtime_root>/models` when a root override is used).
`temp_dir` defaults to `<runtime_root>/tmp` or `tempfile.gettempdir()/app_slug`.

#### Override support

Environment variables (prefix defaults to `PARSE`):

- Root: `PARSE_RUNTIME_ROOT` (aliases: `PARSE_APP_ROOT`, `PARSE_PORTABLE_ROOT`)
- Per-dir:
  - `PARSE_DATA_DIR`
  - `PARSE_CONFIG_DIR`
  - `PARSE_CACHE_DIR`
  - `PARSE_LOG_DIR` (`PARSE_LOGS_DIR` alias)
  - `PARSE_MODELS_DIR` (`PARSE_MODEL_DIR` alias)
  - `PARSE_TEMP_DIR` (`PARSE_TMP_DIR` alias)

If `PARSE_RUNTIME_ROOT` is set, defaults become:

- `<root>/data`, `<root>/config`, `<root>/cache`, `<root>/logs`, `<root>/models`, `<root>/tmp`

---

### 2) `python/shared/runtime_config.py`

Higher-level runtime config loader that combines:

1. hardcoded defaults,
2. optional JSON runtime config file,
3. env overrides.

It provides:

- `RuntimeConfig` dataclass
- `load_runtime_config(...)`
- `build_backend_environment(...)`

`build_backend_environment(...)` emits a consistent env block so Electron can launch the Python backend with the same resolved directories.

#### Optional runtime config file

Can be passed directly or via `PARSE_RUNTIME_CONFIG`.

Expected shape:

```json
{
  "app": {
    "name": "PARSE",
    "slug": "parse",
    "organization": "ArdeleanLucas"
  },
  "runtime": {
    "environment": "desktop-dev",
    "project_root": "/path/to/repo"
  },
  "paths": {
    "root": "~/PARSE-Portable",
    "models": "./models"
  }
}
```

---

## How this supports Electron + Python later

### Electron side (future wiring)

- Resolve or choose an app runtime root (e.g., from `app.getPath("userData")` or a portable folder).
- Export env overrides (`PARSE_*_DIR`) when spawning Python.
- Optionally provide `PARSE_RUNTIME_CONFIG` for profile-based launches.

### Python backend side (future wiring)

- Load runtime config once at process startup.
- Use resolved paths instead of `Path.cwd()` for writable runtime assets.
- Keep repository files (source code, static assets) separate from user/runtime state.

---

## Non-goals in this task

- No wiring into `python/server.py` yet.
- No changes to existing endpoint behavior.
- No migration of existing files/data in this PR.

This is a foundation layer only, designed to unblock safe desktop packaging work in follow-up tasks.
