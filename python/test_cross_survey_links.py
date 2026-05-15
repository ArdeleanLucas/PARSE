from __future__ import annotations

import shutil
from pathlib import Path

from cross_survey_links import (
    apply_cross_survey_link_patch,
    compute_cross_survey_link_patch,
    patch_from_cross_survey_link_summary,
)
from survey_overlap import load_survey_overlap_state, update_survey_overlap_state

FIXTURE = Path(__file__).parent / "test_fixtures" / "cross_survey_links_workspace"


def copy_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE, workspace)
    return workspace


def by_concept(entries: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(entry["concept_id"]): entry for entry in entries}


def write_minimal_workspace(
    tmp_path: Path,
    *,
    concepts_csv: str,
    reference_csv: str,
    survey_overlap_json: str | None = None,
) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "concepts.csv").write_text(concepts_csv, encoding="utf-8")
    (workspace / "reference.csv").write_text(reference_csv, encoding="utf-8")
    if survey_overlap_json is not None:
        (workspace / "survey-overlap.json").write_text(survey_overlap_json, encoding="utf-8")
    return workspace


def test_compute_cross_survey_link_patch_adds_single_word_twin(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    additions = by_concept(summary["would_add"])
    assert additions["1"]["links"] == {"klq": "1.5"}
    assert by_concept(summary["matched"])["1"]["reference_links"] == {"jbil": "10", "klq": "1.5"}


def test_compute_cross_survey_link_patch_skips_multiword_by_default(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n2,big stone,20,JBIL,1\n",
        reference_csv="source,id,lexeme\nJBIL,20,big stone\nKLQ,2.5,big stone\n",
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    skipped = by_concept(summary["skipped_multiword"])
    assert skipped["2"]["concept_en"] == "big stone"
    assert skipped["2"]["reason"] == "single_word_only"


def test_compute_cross_survey_link_patch_conflicts_on_legacy_primary_mismatch(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    conflict = by_concept(summary["conflicts"])["3"]
    assert conflict["reason"] == "legacy_primary_mismatch"
    assert conflict["legacy_primary"] == {"survey": "jbil", "source_item": "30"}
    assert conflict["reference_primary"] == {"survey": "jbil", "source_item": "31"}
    assert "3" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_does_not_duplicate_existing_sidecar_link(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    assert "4" in by_concept(summary["matched"])
    assert "4" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_flags_reference_ambiguous(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n1,stone,50,JBIL,1\n",
        reference_csv=(
            "source,id,lexeme\n"
            "JBIL,50,stone\n"
            "KLQ,5.0,stone\n"
            "KLQ,5.1,stone\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    conflict = by_concept(summary["conflicts"])["1"]
    assert conflict["reason"] == "reference_ambiguous"
    assert conflict["reference_conflicts"] == [
        {"survey": "klq", "first_source_item": "5.0", "conflicting_source_item": "5.1"}
    ]
    assert "1" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_flags_existing_sidecar_mismatch(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n1,stone,50,JBIL,1\n",
        reference_csv="source,id,lexeme\nJBIL,50,stone\nKLQ,5.0,stone\n",
        survey_overlap_json='{ "concept_survey_links": { "1": { "klq": "9.9" } } }\n',
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    conflict = by_concept(summary["conflicts"])["1"]
    assert conflict["reason"] == "existing_sidecar_mismatch"
    assert conflict["sidecar_mismatches"] == [
        {"survey": "klq", "existing_source_item": "9.9", "reference_source_item": "5.0"}
    ]
    assert "1" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_empty_workspace_returns_empty_lists(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.csv"
    reference_path.write_text("source,id,lexeme\nJBIL,1,one\nKLQ,1.1,one\n", encoding="utf-8")

    summary = compute_cross_survey_link_patch(tmp_path / "empty", reference_path)

    assert summary == {"matched": [], "would_add": [], "conflicts": [], "skipped_multiword": []}


def test_cross_survey_link_patch_is_idempotent_after_sidecar_update(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")
    patch = patch_from_cross_survey_link_summary(summary)

    update_survey_overlap_state(workspace, {"concept_survey_links": patch})
    second = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    assert patch == {"1": {"klq": "1.5"}, "2": {"klq": "2.5"}, "5": {"klq": "5.0"}}
    assert second["would_add"] == []


def test_apply_replace_resets_concept_survey_links_before_write(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    update_survey_overlap_state(
        workspace,
        {
            "concept_survey_links": {"99": {"jbil": "999"}},
            "speaker_choices": {"speaker-a": {"1": "jbil"}},
            "speaker_concept_survey_links": {"speaker-a": {"1": {"jbil": "10"}}},
        },
    )
    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    diff = apply_cross_survey_link_patch(workspace, summary, replace=True)
    state = load_survey_overlap_state(workspace)

    assert diff["replace_mode"] is True
    assert diff["added"] == {"1": {"klq": "1.5"}, "2": {"klq": "2.5"}, "4": {"klq": "5.5"}, "5": {"klq": "5.0"}}
    assert state["concept_survey_links"] == {"1": {"klq": "1.5"}, "2": {"klq": "2.5"}, "4": {"klq": "5.5"}, "5": {"klq": "5.0"}}
    assert state["speaker_choices"] == {"speaker-a": {"1": "jbil"}}
    assert state["speaker_concept_survey_links"] == {"speaker-a": {"1": {"jbil": "10"}}}


def test_apply_replace_writes_full_matched_patch_not_just_would_add(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv=(
            "id,concept_en,source_item,source_survey,custom_order\n"
            "1,nose,10,JBIL,1\n"
            "2,father,20,JBIL,2\n"
            "3,hair,30,JBIL,3\n"
            "4,stone,40,JBIL,4\n"
            "5,salt,50,JBIL,5\n"
        ),
        reference_csv=(
            "source,id,lexeme\n"
            "JBIL,10,nose\n"
            "KLQ,1.5,nose\n"
            "JBIL,20,father\n"
            "KLQ,2.5,father\n"
            "JBIL,30,hair\n"
            "KLQ,3.5,hair\n"
            "JBIL,40,stone\n"
            "KLQ,4.5,stone\n"
            "JBIL,50,salt\n"
            "KLQ,5.5,salt\n"
        ),
        survey_overlap_json=(
            '{"concept_survey_links":{"1":{"klq":"1.5"},"2":{"klq":"2.5"},'
            '"3":{"klq":"3.5"},"4":{"klq":"4.5"},"5":{"klq":"5.5"}}}\n'
        ),
    )
    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    assert len(summary["matched"]) == 5
    assert summary["would_add"] == []

    diff = apply_cross_survey_link_patch(workspace, summary, replace=True)
    state = load_survey_overlap_state(workspace)

    expected = {
        "1": {"klq": "1.5"},
        "2": {"klq": "2.5"},
        "3": {"klq": "3.5"},
        "4": {"klq": "4.5"},
        "5": {"klq": "5.5"},
    }
    assert diff["replace_mode"] is True
    assert diff["added"] == expected
    assert state["concept_survey_links"] == expected


def test_apply_replace_strips_legacy_primary_from_full_patch(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n1,father,2.1,KLQ,1\n",
        reference_csv="source,id,lexeme\nKLQ,2.1,father\nJBIL,72,father\n",
    )
    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    diff = apply_cross_survey_link_patch(workspace, summary, replace=True)
    state = load_survey_overlap_state(workspace)

    assert diff["added"] == {"1": {"jbil": "72"}}
    assert state["concept_survey_links"] == {"1": {"jbil": "72"}}


def test_apply_replace_skips_concepts_with_empty_post_strip_links(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n1,father,2.1,KLQ,1\n",
        reference_csv="source,id,lexeme\nKLQ,2.1,father\n",
        survey_overlap_json='{"concept_survey_links":{"stale":{"jbil":"999"}}}\n',
    )
    summary = {
        "matched": [
            {
                "concept_id": "1",
                "concept_en": "father",
                "legacy_primary": {"survey": "klq", "source_item": "2.1"},
                "reference_links": {"klq": "2.1"},
            }
        ],
        "would_add": [],
        "conflicts": [],
        "skipped_multiword": [],
    }

    diff = apply_cross_survey_link_patch(workspace, summary, replace=True)
    state = load_survey_overlap_state(workspace)

    assert diff["added"] == {}
    assert state["concept_survey_links"] == {}


def test_apply_merge_path_unchanged_after_full_patch_addition(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    update_survey_overlap_state(workspace, {"concept_survey_links": {"1": {"klq": "1.5"}, "99": {"jbil": "999"}}})
    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    assert "1" in by_concept(summary["matched"])
    assert "1" not in by_concept(summary["would_add"])

    diff = apply_cross_survey_link_patch(workspace, summary, replace=False)
    state = load_survey_overlap_state(workspace)

    assert diff["replace_mode"] is False
    assert "1" not in diff["added"]
    assert state["concept_survey_links"]["1"] == {"klq": "1.5"}
    assert state["concept_survey_links"]["99"] == {"jbil": "999"}


def test_apply_merge_preserves_stale_concept_survey_links(tmp_path: Path) -> None:
    workspace = copy_workspace(tmp_path)
    update_survey_overlap_state(workspace, {"concept_survey_links": {"99": {"jbil": "999"}}})
    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    diff = apply_cross_survey_link_patch(workspace, summary, replace=False)
    state = load_survey_overlap_state(workspace)

    assert diff["replace_mode"] is False
    assert state["concept_survey_links"]["99"] == {"jbil": "999"}
    assert state["concept_survey_links"]["4"] == {"klq": "5.5"}


def test_compute_cross_survey_link_patch_matches_stripped_parens_when_exact_misses(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv=(
            "id,concept_en,source_item,source_survey,custom_order\n"
            "385,green,177,JBIL,1\n"
            "52,salt,139,JBIL,2\n"
        ),
        reference_csv=(
            "source,id,lexeme\n"
            "JBIL,177,green\n"
            "KLQ,5.4,green (grass)\n"
            "JBIL,139,salt\n"
            "KLQ,3.14,salt (eating)\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    additions = by_concept(summary["would_add"])
    assert additions["385"]["links"] == {"klq": "5.4"}
    assert additions["52"]["links"] == {"klq": "3.14"}


def test_compute_cross_survey_link_patch_matches_variant_workspace_concept_via_stripped_form(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n1,hair (A),1.1,KLQ,1\n",
        reference_csv=(
            "source,id,lexeme\n"
            "JBIL,32,hair\n"
            "KLQ,1.1,hair (collective)\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    additions = by_concept(summary["would_add"])
    assert additions["1"]["links"] == {"jbil": "32"}
    assert by_concept(summary["matched"])["1"]["reference_links"] == {"jbil": "32", "klq": "1.1"}


def test_compute_cross_survey_link_patch_prefers_bare_when_stripped_collides_in_reference(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n136,father (A),72,JBIL,1\n",
        reference_csv=(
            "source,id,lexeme\n"
            "JBIL,72,father\n"
            "KLQ,2.1,father\n"
            "KLQ,2.3,father (vocative)\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    additions = by_concept(summary["would_add"])
    assert additions["136"]["links"] == {"klq": "2.1"}
    assert by_concept(summary["matched"])["136"]["reference_links"] == {"jbil": "72", "klq": "2.1"}
    assert summary["conflicts"] == []


def test_compute_cross_survey_link_patch_rejects_when_no_bare_among_collisions(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n7,X (whatever),1,JBIL,1\n",
        reference_csv=(
            "source,id,lexeme\n"
            "JBIL,1,X\n"
            "KLQ,1.0,X (a)\n"
            "KLQ,1.1,X (b)\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    conflict = by_concept(summary["conflicts"])["7"]
    assert conflict["reason"] == "stripped_match_ambiguous"
    assert conflict["stripped_key"] == "x"
    assert "7" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_parenthetical_workspace_skipped_when_primary_mismatches_bare_canonical(
    tmp_path: Path,
) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n7,father (vocative),2.3,KLQ,1\n",
        reference_csv=(
            "source,id,lexeme\n"
            "JBIL,72,father\n"
            "KLQ,2.1,father\n"
            "KLQ,2.3,father (vocative)\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    conflict = by_concept(summary["conflicts"])["7"]
    assert conflict["reason"] == "legacy_primary_mismatch"
    assert conflict["legacy_primary"] == {"survey": "klq", "source_item": "2.3"}
    assert conflict["reference_primary"] == {"survey": "klq", "source_item": "2.1"}
    assert conflict["reference_links"] == {"jbil": "72", "klq": "2.1"}
    assert "7" not in by_concept(summary["would_add"])


def test_compute_cross_survey_link_patch_preserves_exact_match_when_both_bare_present(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv="id,concept_en,source_item,source_survey,custom_order\n8,father,2.1,KLQ,1\n",
        reference_csv=(
            "source,id,lexeme\n"
            "KLQ,2.1,father\n"
            "KLQ,2.3,father (vocative)\n"
            "JBIL,72,father\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    additions = by_concept(summary["would_add"])
    assert additions["8"]["links"] == {"jbil": "72"}
    assert by_concept(summary["matched"])["8"]["reference_links"] == {"jbil": "72", "klq": "2.1"}
    assert summary["conflicts"] == []


def test_compute_cross_survey_link_patch_strips_nested_commas_inside_parens(tmp_path: Path) -> None:
    workspace = write_minimal_workspace(
        tmp_path,
        concepts_csv=(
            "id,concept_en,source_item,source_survey,custom_order\n"
            "9,\"hard (like a stone, opposite of soft 'nerm')\",4.18,KLQ,1\n"
        ),
        reference_csv=(
            "source,id,lexeme\n"
            "KLQ,4.18,hard (something)\n"
            "JBIL,172,hard\n"
        ),
    )

    summary = compute_cross_survey_link_patch(workspace, workspace / "reference.csv")

    additions = by_concept(summary["would_add"])
    assert additions["9"]["links"] == {"jbil": "172"}
    assert by_concept(summary["matched"])["9"]["reference_links"] == {"jbil": "172", "klq": "4.18"}
