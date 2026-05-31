from __future__ import annotations

import json
from pathlib import Path

from migration.seed_concept_notes_from_compare_mirror import (
    run_migration,
    seed_concept_notes,
)


def test_seed_concept_notes_into_empty_enrichments() -> None:
    enrichments: dict = {}
    mirror = {"356": "HONEY — rep=B", "365": "NEW — rep=B"}
    out, result = seed_concept_notes(enrichments, mirror, now="2026-05-31T00:00:00Z")
    assert result.seeded == 2
    assert out["concept_notes"]["356"] == {"note": "HONEY — rep=B", "updated_at": "2026-05-31T00:00:00Z"}
    assert out["concept_notes"]["365"]["note"] == "NEW — rep=B"


def test_seed_skips_empty_and_blank_notes() -> None:
    out, result = seed_concept_notes({}, {"1": "", "2": "   ", "3": "real", "": "x"})
    assert result.seeded == 1
    assert result.skipped_empty == 3
    assert list(out["concept_notes"].keys()) == ["3"]


def test_seed_preserves_existing_server_edits_unless_overwrite() -> None:
    enrichments = {"concept_notes": {"356": {"note": "server edit", "updated_at": "z"}}}
    _, result = seed_concept_notes(enrichments, {"356": "mirror text"})
    assert result.seeded == 0
    assert result.skipped_existing == 1
    assert enrichments["concept_notes"]["356"]["note"] == "server edit"

    enrichments2 = {"concept_notes": {"356": {"note": "server edit", "updated_at": "z"}}}
    _, result2 = seed_concept_notes(enrichments2, {"356": "mirror text"}, overwrite=True)
    assert result2.seeded == 1
    assert enrichments2["concept_notes"]["356"]["note"] == "mirror text"


def test_seed_does_not_disturb_other_enrichment_fields() -> None:
    enrichments = {"cognate_sets": {"53": {"A": ["Qorv01"]}}, "lexeme_notes": {"Fail01": {"249": {"user_note": "men"}}}}
    out, _ = seed_concept_notes(enrichments, {"53": "BIG note"})
    assert out["cognate_sets"] == {"53": {"A": ["Qorv01"]}}
    assert out["lexeme_notes"]["Fail01"]["249"]["user_note"] == "men"
    assert out["concept_notes"]["53"]["note"] == "BIG note"


def test_run_migration_writes_backup_and_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "parse-enrichments.json").write_text(
        json.dumps({"cognate_sets": {"53": {"A": ["Qorv01"]}}}), encoding="utf-8"
    )
    (tmp_path / "parseui-compare-notes-v1.json").write_text(
        json.dumps({"356": "HONEY — rep=B"}), encoding="utf-8"
    )

    result = run_migration(tmp_path)
    assert result.seeded == 1

    enrichments = json.loads((tmp_path / "parse-enrichments.json").read_text(encoding="utf-8"))
    assert enrichments["concept_notes"]["356"]["note"] == "HONEY — rep=B"
    assert enrichments["cognate_sets"] == {"53": {"A": ["Qorv01"]}}  # untouched

    backups = list(tmp_path.glob("parse-enrichments.json.bak-pre-concept-notes-seed-*"))
    assert len(backups) == 1

    # Re-running keeps the existing entry (no duplicate seed) and makes another backup.
    result2 = run_migration(tmp_path)
    assert result2.seeded == 0
    assert result2.skipped_existing == 1
