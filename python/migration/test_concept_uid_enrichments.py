from __future__ import annotations

import json
from pathlib import Path

from migration.concept_uid_enrichments import (
    expand_uid_keys_for_legacy_read,
    migrate_uid_enrichment_keys,
    promote_legacy_uid_keys,
)


def _seed_workspace(ws: Path, enrichments: dict) -> None:
    (ws / "concepts.csv").write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "52,salt,3.14,KLQ,52\n"
        "352,salt (eating),139,JBIL,352\n"
        "90,water,7.4,KLQ,90\n",
        encoding="utf-8",
    )
    (ws / "survey-overlap.json").write_text(
        json.dumps(
            {
                "version": 1,
                "concept_survey_links": {
                    "52": {"jbil": "139"},
                    "352": {"klq": "3.14"},
                },
            }
        ),
        encoding="utf-8",
    )
    (ws / "parse-enrichments.json").write_text(
        json.dumps(enrichments, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _full_enrichments() -> dict:
    return {
        "cognate_sets": {"52": {"A": ["Saha01"]}},
        "similarity": {"352": {"Saha01": {"ar": {"score": 0.7}}}},
        "borrowing_flags": {"bundle:salt": {"Saha01": "Arabic loan"}},
        "concept_notes": {"52": {"note": "concept-level note"}},
        "manual_overrides": {
            "speaker_flags": {"352": {"Khan02": True}},
            "cognate_decisions": {"c-52": {"decision": "accepted"}},
            "concept_merges": {"52": ["352", "90"]},
            "canonical_lexemes": {
                "bundle:salt": {
                    "Saha01": {"csv_row_id": "352", "source": "manual"}
                }
            },
            "unrelated": {"52": "must stay because block is not concept-keyed"},
        },
        "lexeme_notes": {"Saha01": {"352": {"user_note": "check realization"}}},
    }


def test_uid_migration_dry_run_reports_without_writing(tmp_path: Path) -> None:
    _seed_workspace(tmp_path, _full_enrichments())
    before = (tmp_path / "parse-enrichments.json").read_text(encoding="utf-8")

    report = migrate_uid_enrichment_keys(tmp_path, execute=False)

    assert (tmp_path / "parse-enrichments.json").read_text(encoding="utf-8") == before
    assert report["mode"] == "dry-run"
    assert report["legacy_keys_migrated_total"] >= 8
    assert report["backup_written"] is None
    moved = {(entry["block"], entry["old_key"], entry["new_key"]) for entry in report["decision_keys_migrated"]}
    assert ("cognate_sets", "52", "c-52") in moved
    assert ("canonical_lexemes", "bundle:salt", "c-52") in moved
    assert ("lexeme_notes", "352", "c-52") in moved


def test_uid_migration_apply_rekeys_every_decision_shape_and_is_idempotent(tmp_path: Path) -> None:
    _seed_workspace(tmp_path, _full_enrichments())

    report = migrate_uid_enrichment_keys(tmp_path, execute=True)
    migrated = json.loads((tmp_path / "parse-enrichments.json").read_text(encoding="utf-8"))
    second = migrate_uid_enrichment_keys(tmp_path, execute=True)

    assert report["mode"] == "execute"
    assert report["backup_written"]
    assert (tmp_path / report["backup_written"]).exists()
    assert second["decision_keys_migrated"] == []
    assert second["backup_written"] is None
    assert migrated["cognate_sets"] == {"c-52": {"A": ["Saha01"]}}
    assert migrated["similarity"] == {"c-52": {"Saha01": {"ar": {"score": 0.7}}}}
    assert migrated["borrowing_flags"] == {"c-52": {"Saha01": "Arabic loan"}}
    assert migrated["concept_notes"] == {"c-52": {"note": "concept-level note"}}
    assert migrated["manual_overrides"]["speaker_flags"] == {"c-52": {"Khan02": True}}
    assert migrated["manual_overrides"]["cognate_decisions"] == {"c-52": {"decision": "accepted"}}
    assert migrated["manual_overrides"]["concept_merges"] == {"c-52": ["c-52", "c-90"]}
    assert migrated["manual_overrides"]["canonical_lexemes"] == {
        "c-52": {"Saha01": {"csv_row_id": "352", "source": "manual"}}
    }
    assert migrated["manual_overrides"]["unrelated"] == {"52": "must stay because block is not concept-keyed"}
    assert migrated["lexeme_notes"] == {"Saha01": {"c-52": {"user_note": "check realization"}}}


def test_promote_legacy_uid_keys_keeps_legacy_data_visible_before_apply(tmp_path: Path) -> None:
    _seed_workspace(tmp_path, {"manual_overrides": {"speaker_flags": {"52": {"Saha01": True}}}})
    payload = json.loads((tmp_path / "parse-enrichments.json").read_text(encoding="utf-8"))

    promoted = promote_legacy_uid_keys(tmp_path, payload)

    assert promoted == [{"block": "speaker_flags", "old_key": "52", "new_key": "c-52"}]
    assert payload["manual_overrides"]["speaker_flags"] == {"c-52": {"Saha01": True}}


def test_expand_uid_keys_for_legacy_read_supports_row_id_readers(tmp_path: Path) -> None:
    _seed_workspace(tmp_path, {"cognate_sets": {"c-52": {"A": ["Saha01"]}}})
    payload = json.loads((tmp_path / "parse-enrichments.json").read_text(encoding="utf-8"))

    expanded = expand_uid_keys_for_legacy_read(tmp_path, payload)

    assert expanded["cognate_sets"]["c-52"] == {"A": ["Saha01"]}
    assert expanded["cognate_sets"]["52"] == {"A": ["Saha01"]}
    assert expanded["cognate_sets"]["352"] == {"A": ["Saha01"]}
