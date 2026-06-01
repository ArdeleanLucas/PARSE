from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from concept_identity import (
    CONCEPT_IDENTITY_FILENAME,
    compute_auto_components,
    identity_payload,
    load_concept_identity,
)
from survey_overlap import SURVEY_OVERLAP_FILENAME

FIELDNAMES = ["id", "concept_en", "source_item", "source_survey", "custom_order"]


def _seed_concepts(root: pathlib.Path, rows: list[dict[str, str]]) -> None:
    with (root / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})


def _seed_overlap(root: pathlib.Path, concept_survey_links: dict[str, dict[str, str]]) -> None:
    (root / SURVEY_OVERLAP_FILENAME).write_text(
        json.dumps({"version": 1, "concept_survey_links": concept_survey_links}),
        encoding="utf-8",
    )


def _seed_identity_overrides(root: pathlib.Path, concepts: list[dict]) -> None:
    (root / CONCEPT_IDENTITY_FILENAME).write_text(
        json.dumps({"version": 1, "concepts": concepts}), encoding="utf-8"
    )


def _concept_for(identity, row_id: str):
    uid = identity.uid_for_row(row_id)
    return next((c for c in identity.concepts if c.uid == uid), None)


# --------------------------------------------------------------------------- #
def test_cross_survey_link_consolidates_one_concept(tmp_path):
    """green: KLQ 5.4 (row 91) <-> JBIL 177 (row 385) become one concept."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "91", "concept_en": "green (grass)", "source_item": "5.4", "source_survey": "KLQ"},
            {"id": "385", "concept_en": "green", "source_item": "177", "source_survey": "JBIL"},
        ],
    )
    _seed_overlap(tmp_path, {"91": {"jbil": "177"}, "385": {"klq": "5.4"}})

    identity = load_concept_identity(tmp_path)

    assert identity.uid_for_row("91") == identity.uid_for_row("385")
    concept = _concept_for(identity, "91")
    assert concept.members == ["91", "385"]
    assert concept.origin == "auto"
    assert concept.label == "green"  # cleanest gloss wins over "green (grass)"


def test_shared_source_item_without_link_stays_separate(tmp_path):
    """A paradigm sharing one survey item (JBIL 319) must NOT merge."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "517", "concept_en": "I", "source_item": "319", "source_survey": "JBIL"},
            {"id": "558", "concept_en": "i am teaching", "source_item": "319", "source_survey": "JBIL"},
            {"id": "601", "concept_en": "Im a teacher", "source_item": "319", "source_survey": "JBIL"},
        ],
    )
    _seed_overlap(tmp_path, {})

    identity = load_concept_identity(tmp_path)

    uids = {identity.uid_for_row(r) for r in ("517", "558", "601")}
    assert len(uids) == 3  # three distinct singleton concepts


def test_singleton_concept_without_links(tmp_path):
    """to fly (row 122, no links) is its own single-survey concept."""
    _seed_concepts(
        tmp_path,
        [{"id": "122", "concept_en": "to fly", "source_item": "7.12", "source_survey": "KLQ"}],
    )
    _seed_overlap(tmp_path, {})

    identity = load_concept_identity(tmp_path)

    assert len(identity.concepts) == 1
    assert identity.concepts[0].members == ["122"]


def test_transitive_three_survey_chain(tmp_path):
    """A<->B and B<->C (A not directly linked to C) still form one concept."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "10", "concept_en": "x", "source_item": "1", "source_survey": "KLQ"},
            {"id": "20", "concept_en": "x", "source_item": "2", "source_survey": "JBIL"},
            {"id": "30", "concept_en": "x", "source_item": "3", "source_survey": "EXT"},
        ],
    )
    # KLQ<->JBIL and JBIL<->EXT, but KLQ is never linked to EXT directly.
    _seed_overlap(
        tmp_path,
        {"10": {"jbil": "2"}, "20": {"klq": "1", "ext": "3"}, "30": {"jbil": "2"}},
    )

    identity = load_concept_identity(tmp_path)

    assert identity.uid_for_row("10") == identity.uid_for_row("30")
    assert _concept_for(identity, "10").members == ["10", "20", "30"]


def test_manual_split_overrides_closure(tmp_path):
    """snow/ice: closure merges all 4; a manual split yields two characters."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "44", "concept_en": "snow", "source_item": "3.4", "source_survey": "KLQ"},
            {"id": "144", "concept_en": "snow", "source_item": "123", "source_survey": "JBIL"},
            {"id": "45", "concept_en": "ice", "source_item": "123", "source_survey": "JBIL"},
            {"id": "617", "concept_en": "ice", "source_item": "3.5", "source_survey": "KLQ"},
        ],
    )
    _seed_overlap(
        tmp_path,
        {"44": {"jbil": "123"}, "144": {"klq": "3.4"}, "45": {"klq": "3.5"}, "617": {"jbil": "123"}},
    )

    # Without overrides the closure over-merges all four.
    rows_state = json.loads((tmp_path / SURVEY_OVERLAP_FILENAME).read_text())
    from concept_identity import _concept_rows  # noqa: PLC0415

    comps = compute_auto_components(_concept_rows(tmp_path), rows_state)
    assert ["44", "45", "144", "617"] in comps

    # Linguist splits snow from ice.
    _seed_identity_overrides(
        tmp_path,
        [
            {"uid": "c-snow", "label": "snow", "members": ["44", "144"], "origin": "manual:split"},
            {"uid": "c-ice", "label": "ice", "members": ["45", "617"], "origin": "manual:split"},
        ],
    )

    identity = load_concept_identity(tmp_path)

    assert identity.uid_for_row("44") == "c-snow"
    assert identity.uid_for_row("45") == "c-ice"
    assert identity.uid_for_row("44") != identity.uid_for_row("45")
    snow = _concept_for(identity, "44")
    assert snow.members == ["44", "144"] and snow.origin == "manual:split"


def test_orphan_member_ids_are_reconciled(tmp_path):
    """Override members that no longer exist in concepts.csv are dropped."""
    _seed_concepts(
        tmp_path,
        [{"id": "91", "concept_en": "green", "source_item": "5.4", "source_survey": "KLQ"}],
    )
    _seed_overlap(tmp_path, {})
    _seed_identity_overrides(
        tmp_path,
        [{"uid": "c-green", "label": "green", "members": ["91", "9999"], "origin": "manual:merge"}],
    )

    identity = load_concept_identity(tmp_path)

    green = _concept_for(identity, "91")
    assert green.members == ["91"]  # "9999" dropped, not retained
    assert identity.uid_for_row("9999") is None


def test_new_row_falls_into_its_component_on_load(tmp_path):
    """A row absent from any override is auto-placed (reconcile-on-load)."""
    _seed_concepts(
        tmp_path,
        [
            {"id": "91", "concept_en": "green (grass)", "source_item": "5.4", "source_survey": "KLQ"},
            {"id": "385", "concept_en": "green", "source_item": "177", "source_survey": "JBIL"},
            {"id": "500", "concept_en": "sky", "source_item": "9.9", "source_survey": "KLQ"},
        ],
    )
    _seed_overlap(tmp_path, {"91": {"jbil": "177"}, "385": {"klq": "5.4"}})
    # Override only describes green; "sky" is new and undescribed.
    _seed_identity_overrides(
        tmp_path,
        [{"uid": "c-green", "label": "green", "members": ["91", "385"], "origin": "manual:merge"}],
    )

    identity = load_concept_identity(tmp_path)

    assert identity.uid_for_row("500") is not None
    assert _concept_for(identity, "500").members == ["500"]
    assert identity.uid_for_row("91") == "c-green"


def test_identity_payload_round_trips(tmp_path):
    _seed_concepts(
        tmp_path,
        [
            {"id": "91", "concept_en": "green (grass)", "source_item": "5.4", "source_survey": "KLQ"},
            {"id": "385", "concept_en": "green", "source_item": "177", "source_survey": "JBIL"},
        ],
    )
    _seed_overlap(tmp_path, {"91": {"jbil": "177"}, "385": {"klq": "5.4"}})

    identity = load_concept_identity(tmp_path)
    payload = identity_payload(identity)

    assert payload["version"] == 1
    assert payload["concepts"][0]["members"] == ["91", "385"]
    # Writing the payload back as overrides reproduces the same grouping.
    _seed_identity_overrides(tmp_path, payload["concepts"])
    reloaded = load_concept_identity(tmp_path)
    assert reloaded.uid_for_row("91") == reloaded.uid_for_row("385")
