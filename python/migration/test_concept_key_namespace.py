from __future__ import annotations

import json
from pathlib import Path

from migration.concept_key_namespace import (
    _canonical_key,
    build_remap,
    build_remap_for_workspace,
    migrate,
    promote_safe_legacy_keys,
    scan_legacy_keys,
)


def _concepts_csv(ws: Path) -> Path:
    # Faithful slice of the real corpus: a dotted-key SAFE group (step-son,
    # KLQ 2.26), an integer-key AMBIGUOUS group (you (pl.), JBIL 322 == leaf's
    # id), and the colliding singleton (leaf, id 322).
    path = ws / "concepts.csv"
    path.write_text(
        "id,concept_en,source_item,source_survey,custom_order\n"
        "322,leaf,102,JBIL,\n"
        "520,you (pl.),322,JBIL,\n"
        "561,you are teaching,322,JBIL,\n"
        "38,step-son,2.26,KLQ,\n"
        "606,step-son son of husband,2.26,KLQ,\n"
        "607,step-son son of wife,2.26,KLQ,\n"
        "54,water,7.4,KLQ,\n",
        encoding="utf-8",
    )
    return path


def _write_workspace(ws: Path, enrichments: dict) -> None:
    _concepts_csv(ws)
    (ws / "parse-enrichments.json").write_text(
        json.dumps(enrichments, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_canonical_key_picks_min_numeric_member() -> None:
    assert _canonical_key(["520", "561"]) == "520"
    assert _canonical_key(["606", "38", "607"]) == "38"
    assert _canonical_key(["concept-b", "concept-a"]) == "concept-b"  # non-numeric: first seen


def test_build_remap_classifies_safe_vs_ambiguous(tmp_path: Path) -> None:
    _write_workspace(tmp_path, {})
    remap = build_remap(tmp_path / "concepts.csv")
    # SAFE: dotted source_item never equals an integer csv id.
    assert remap["2.26"]["new_key"] == "38"
    assert remap["2.26"]["classification"] == "SAFE"
    # AMBIGUOUS: source_item "322" is also leaf's csv id.
    assert remap["322"]["new_key"] == "520"
    assert remap["322"]["classification"] == "AMBIGUOUS"
    assert remap["322"]["collides_with_id"] == "322"


def test_dry_run_writes_nothing_but_reports(tmp_path: Path) -> None:
    _write_workspace(tmp_path, {"manual_overrides": {"speaker_flags": {"2.26": {"S1": True}}}})
    before = (tmp_path / "parse-enrichments.json").read_text(encoding="utf-8")
    report = migrate(tmp_path, execute=False)
    assert (tmp_path / "parse-enrichments.json").read_text(encoding="utf-8") == before
    assert report["mode"] == "dry-run"
    assert {t["old_key"] for t in report["decision_keys_migrated"]} == {"2.26"}


def test_execute_rekeys_safe_preserves_singletons_and_unicode(tmp_path: Path) -> None:
    _write_workspace(tmp_path, {
        "manual_overrides": {
            "speaker_flags": {"2.26": {"S1": True}, "54": {"S2": True}},
            "cognate_sets": {"2.26": {"A": ["S1"]}},
            "concept_merges": {"2.26": ["527"]},
            "lexeme_notes": {"x": "realization /ʒɪ̃/ — ئاو"},
        }
    })
    report = migrate(tmp_path, execute=True)
    raw = (tmp_path / "parse-enrichments.json").read_text(encoding="utf-8")
    enr = json.loads(raw)
    mo = enr["manual_overrides"]

    assert sorted(mo["speaker_flags"]) == ["38", "54"]      # 2.26 -> 38; singleton 54 kept
    assert sorted(mo["cognate_sets"]) == ["38"]
    assert mo["concept_merges"] == {"38": ["527"]}          # key AND value handled
    assert "ʒɪ̃" in raw and "\\u" not in raw                 # non-ASCII preserved
    assert raw.endswith("\n")
    assert report["backup_written"] and report["backup_written"].startswith("parse-enrichments.json.bak-")


def test_execute_leaves_ambiguous_in_place(tmp_path: Path) -> None:
    _write_workspace(tmp_path, {"manual_overrides": {"cognate_sets": {"322": {"A": ["S1"]}}}})
    report = migrate(tmp_path, execute=True)
    enr = json.loads((tmp_path / "parse-enrichments.json").read_text(encoding="utf-8"))
    # The shared "322" slot is NOT moved; it is reported for manual triage.
    assert "322" in enr["manual_overrides"]["cognate_sets"]
    assert report["decision_keys_migrated"] == []
    assert {a["key"] for a in report["decision_keys_ambiguous_left_in_place"]} == {"322"}


def test_idempotent(tmp_path: Path) -> None:
    _write_workspace(tmp_path, {"manual_overrides": {"speaker_flags": {"2.26": {"S1": True}}}})
    migrate(tmp_path, execute=True)
    second = migrate(tmp_path, execute=True)
    assert second["decision_keys_migrated"] == []
    assert second["verification_ok"] is True


def test_promote_safe_legacy_keys_promotes_safe_leaves_ambiguous(tmp_path: Path) -> None:
    remap = build_remap(_concepts_csv(tmp_path))
    enr = {"manual_overrides": {
        "speaker_flags": {"2.26": {"S1": True}, "54": {"S2": True}},  # 2.26 SAFE, 54 singleton
        "cognate_sets": {"322": {"A": ["S1"]}},                        # 322 AMBIGUOUS (== leaf id)
        "concept_merges": {"2.26": ["527"]},
    }}
    promos = promote_safe_legacy_keys(enr, remap)
    mo = enr["manual_overrides"]
    assert sorted(mo["speaker_flags"]) == ["38", "54"]          # 2.26 -> 38; singleton kept
    assert mo["concept_merges"] == {"38": ["527"]}              # key promoted
    assert mo["cognate_sets"] == {"322": {"A": ["S1"]}}         # AMBIGUOUS untouched
    assert {p["old_key"] for p in promos} == {"2.26"}


def test_promote_merges_into_existing_new_key(tmp_path: Path) -> None:
    remap = build_remap(_concepts_csv(tmp_path))
    enr = {"manual_overrides": {"speaker_flags": {"2.26": {"S1": True}, "38": {"S2": True}}}}
    promote_safe_legacy_keys(enr, remap)
    assert enr["manual_overrides"]["speaker_flags"]["38"] == {"S2": True, "S1": True}


def test_scan_legacy_keys_reports_pending(tmp_path: Path) -> None:
    remap = build_remap(_concepts_csv(tmp_path))
    enr = {"manual_overrides": {"cognate_sets": {"322": {"A": []}, "54": {}}}}
    found = scan_legacy_keys(enr, remap)
    assert found == [{"block": "cognate_sets", "key": "322", "classification": "AMBIGUOUS"}]


def test_build_remap_for_workspace_caches_and_handles_missing(tmp_path: Path) -> None:
    assert build_remap_for_workspace(tmp_path) == {}     # no concepts.csv yet
    _write_workspace(tmp_path, {})
    first = build_remap_for_workspace(tmp_path)
    assert build_remap_for_workspace(tmp_path) is first  # cached by mtime


def test_load_enrichments_promotes_safe_keys_at_read_time(tmp_path: Path) -> None:
    # End-to-end: the central loader applies the read-time safety net.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from canonical_lexemes import load_enrichments

    _write_workspace(tmp_path, {"manual_overrides": {
        "speaker_flags": {"2.26": {"S1": True}},
        "cognate_sets": {"322": {"A": ["S1"]}},
    }})
    loaded = load_enrichments(tmp_path)
    mo = loaded["manual_overrides"]
    assert "38" in mo["speaker_flags"] and "2.26" not in mo["speaker_flags"]  # SAFE promoted
    assert mo["cognate_sets"] == {"322": {"A": ["S1"]}}                       # AMBIGUOUS untouched
