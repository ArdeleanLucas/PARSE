---
name: wsl-windows-subprocess-paths
description: >
  When WSL spawns a Windows .exe (e.g. via Hermes MCP config or subprocess),
  args and env vars must use Windows-native paths, not WSL /mnt/c/... paths.
  Covers correct path formats, os.add_dll_directory, and MCP server config.
tags: [wsl, windows, paths, mcp, subprocess, python, hermes]
---

# WSL → Windows Subprocess Path Rules

## The core problem

When WSL spawns a Windows `.exe` (Python, PowerShell, etc.), the process runs
as a **Windows process** under WSL interop. It receives arguments and env vars
as raw strings. If those strings contain WSL-format paths (`/mnt/c/...`),
Windows will interpret them as Windows UNC-style paths (`\\mnt\\c\\...`) which
don't exist — causing `FileNotFoundError`, `PermissionError (WinError 5)`, or
silent failures.

**Good:** `C:/Users/Lucas/parse_v2` or `C:\Users\Lucas\parse_v2`  
**Bad:** `/mnt/c/Users/Lucas/parse_v2` (WSL path — Windows can't resolve it)

---

## Rule 1 — The command itself uses WSL path; args/env use Windows paths

The `command` field in a subprocess config can be a WSL path (WSL resolves it
to the Windows .exe). But **args** and **env** are passed directly to the
Windows process and must be Windows-native:

```yaml
# Hermes config.yaml — MCP server entry
mcp_servers:
  parse:
    command: /mnt/c/Users/Lucas/anaconda3/envs/kurdish_asr/python.exe  # WSL path OK here
    args:
      - C:/Users/Lucas/parse_v2/python/adapters/mcp_adapter.py         # Windows path
    env:
      PARSE_PROJECT_ROOT: C:/Users/Lucas/parse_v2                       # Windows path
```

---

## Rule 2 — Forward slashes work in Windows paths

Python on Windows accepts forward slashes in `pathlib.Path` and `open()`.
Use `C:/Users/...` in YAML to avoid YAML backslash escaping headaches:

```yaml
# All of these work in Windows Python:
C:/Users/Lucas/parse_v2          # preferred in YAML
C:\Users\Lucas\parse_v2          # also works (no escaping needed in unquoted YAML)
"C:\\Users\\Lucas\\parse_v2"     # double-quoted YAML needs escaping
```

---

## Rule 3 — Environment variables used as Python Path() must be Windows paths

If a Windows Python script does `Path(os.environ["SOME_ROOT"])`, the env var
must contain a Windows path. WSL paths will appear to exist (no exception) but
silently resolve to wrong locations:

```python
# In Windows Python process:
from pathlib import Path
root = Path("/mnt/c/Users/Lucas/parse_v2")
root.exists()  # → PermissionError or False (resolves to \\mnt\\c\... on Windows)

root = Path("C:/Users/Lucas/parse_v2")
root.exists()  # → True ✓
```

---

## Rule 4 — os.add_dll_directory() dirs must exist at process start

When Windows Python spawns as a fresh process (MCP stdio, standalone script),
DLL dirs are NOT inherited from the parent WSL process. Register them at the top
of every entry-point file before any imports:

```python
import sys as _sys_pre
if _sys_pre.platform == "win32":
    import os as _os_pre, site as _site_pre
    for _sp in _site_pre.getsitepackages():
        for _sub in ("ctranslate2", "torch/lib"):
            _d = _os_pre.path.join(_sp, _sub)
            if _os_pre.path.isdir(_d):
                try:
                    _os_pre.add_dll_directory(_d)
                except (OSError, ValueError):
                    pass
    del _sys_pre, _os_pre, _site_pre, _sp, _sub, _d
else:
    del _sys_pre
```

---

## Diagnostic: confirming Windows Python can't see a WSL path

```python
# Run in the Windows Python process:
from pathlib import Path
p = Path("/mnt/c/Users/Lucas/parse_v2")
p.exists()  # PermissionError: [WinError 5] Access is denied: '\\mnt\\c\\Users\\...'
```

This confirms the path was silently mangled. Switch to `C:/Users/Lucas/parse_v2`.

---

## MCP server checklist (Hermes config.yaml)

When configuring a Windows Python MCP server from WSL Hermes:

- [ ] `command:` — WSL path to `.exe` is fine (WSL interop resolves it)
- [ ] `args:` — ALL entries must be Windows paths (`C:/...`)
- [ ] `env:` — ALL path-like values must be Windows paths (`C:/...`)
- [ ] Entry-point script — has `os.add_dll_directory()` block for CUDA DLLs
- [ ] `sys.path` manipulation in the script — uses `__file__` (resolves correctly as Windows path since it's a Windows process)

---

## Pitfalls

- **`ctranslate2.get_cuda_device_count()` lies** — returns 1 even when the CUDA
  DLL path is wrong. Actual failure happens at `WhisperModel().transcribe()`.
- **`site.getsitepackages()` in Windows Python** returns Windows paths, so
  `os.path.join(sp, "ctranslate2")` produces a correct Windows path automatically.
- **PowerShell `-Environment` parameter** doesn't exist in older PowerShell
  versions. Use `$env:VAR = "value"` before calling the command instead.
- **The `del` cleanup after the DLL block** can hit `NameError` if the loop body
  never ran (empty `getsitepackages()`). Safe to wrap in `try/except NameError`.
