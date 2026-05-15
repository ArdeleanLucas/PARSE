"""Tests for the duplicate concept-row read-only audit script."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "audits"))

import duplicate_concept_rows  # noqa: E402


def test_duplicate_concept_rows_audit_reports_buckets_speakers_and_orphans() -> None:
    fixture_root = pathlib.Path(__file__).resolve().parent / "tests" / "fixtures" / "audit"

    manifest = duplicate_concept_rows.build_manifest(
        concepts_csv=fixture_root / "concepts.csv",
        annotations_dir=fixture_root / "annotations",
    )

    assert "Duplicate buckets: 2" in manifest
    assert "Orphan ids: 1" in manifest
    assert "JBIL: 2" in manifest
    assert "| 79 | JBIL | `1|dog (A)`, `2|dog (B)` | 1: Qasr01 [`custom-sk-concept-list`, `confirmed`]<br>2: Qasr01 [`custom-sk-concept-list`, `problematic`] |  |" in manifest
    assert "| 102 | JBIL | `3|leaf (A)`, `4|leaf (B)` | 3: Saha01 [`custom-sk-concept-list`, `review-needed`]<br>4: Saha01 [`custom-sk-concept-list`, `problematic`] |  |" in manifest
    assert "rain" not in manifest
