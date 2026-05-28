"""Regression tests for backend validation guidance.

These tests keep the documented backend sweep aligned with the executable test
suite. MC-419-A removed a stale workaround that excluded two ORTH cascade tests
from full-sweep validation even though current main passes them in order.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_MD = REPO_ROOT / "AGENTS.md"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ORTHO_DESELECT_WORKAROUND = (
    "not test_ortho_section_defaults_cascade_guard and not "
    "test_ortho_explicit_override_beats_defaults"
)
CANONICAL_BACKEND_SWEEP = "PYTHONPATH=python python3 -m pytest python/ -q"
CANONICAL_CI_BACKEND_SWEEP = "python -m pytest python/ -q"


def test_backend_validation_guidance_uses_full_sweep_without_ortho_deselect() -> None:
    """MC-419-A: current backend guidance must not perpetuate the old -k skip."""
    guidance = AGENTS_MD.read_text(encoding="utf-8")

    assert ORTHO_DESELECT_WORKAROUND not in guidance
    assert CANONICAL_BACKEND_SWEEP in guidance


def test_ci_workflow_uses_full_sweep_without_ortho_deselect() -> None:
    """MC-419-B: CI must not perpetuate the old -k skip either."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert ORTHO_DESELECT_WORKAROUND not in workflow
    assert CANONICAL_CI_BACKEND_SWEEP in workflow
