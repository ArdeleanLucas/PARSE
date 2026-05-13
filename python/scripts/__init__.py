"""One-shot PARSE maintenance scripts.

This package also extends its import path to the repository-level ``scripts/``
directory so existing tests/imports such as ``scripts.backfill_source_item`` keep
working when ``PYTHONPATH=python`` resolves this package first.
"""

from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]
_repo_scripts = Path(__file__).resolve().parents[2] / "scripts"
if _repo_scripts.is_dir():
    repo_scripts_str = str(_repo_scripts)
    if repo_scripts_str not in __path__:
        __path__.append(repo_scripts_str)
