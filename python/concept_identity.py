"""Comparative-concept identity for PARSE.

A *comparative concept* is the unit the linguist compares and exports as one row
of the phylogenetic character matrix. It is **not** a single ``concepts.csv``
row and **not** an English label — the same meaning is frequently elicited as
several rows across surveys (e.g. ``green`` in KLQ 5.4 and JBIL 177).

This module materialises that identity from two inputs the workspace already
holds, with no data migration:

1. ``concepts.csv``           — rows = survey items (the elicitation inventory)
2. ``survey-overlap.json``    — ``concept_survey_links`` = the linguist's curated
                                "this row is the same concept as that survey item"
                                assertions.

Pipeline (see docs/architecture/concept-identity.md):

    compute closure(links)  ->  apply manual overrides  ->  materialised concepts

* **Closure** — rows are nodes; an *explicit cross-survey link* is an edge.
  Connected components are the auto-suggested concepts. Sharing a bare
  ``source_item`` is **not** an edge (one survey item legitimately hosts several
  glosses, e.g. a pronoun paradigm), so those rows stay separate.
* **Overrides** — the closure is only a *suggestion*. ``concept-identity.json``
  records the linguist's authoritative split/merge decisions (e.g. JBIL elicits
  snow and ice under one item; the linguist splits them into two characters).
  The algorithm never finalises identity — it proposes, the linguist disposes.

Decisions downstream (cognate sets, canonical picks, notes) key off the stable
``uid`` returned here, which is what makes "one cognate state per concept"
well-defined.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from concept_canonical import variant_stem
from concept_source_item import read_concepts_csv_rows, row_value
from survey_overlap import (
    SurveyOverlapState,
    load_survey_overlap_state,
    normalize_survey_id,
)

CONCEPT_IDENTITY_FILENAME = "concept-identity.json"

# Survey item identity = (normalised survey id, source item string).
SurveyItem = tuple[str, str]


@dataclass(frozen=True)
class ConceptRow:
    """One ``concepts.csv`` row, normalised for identity computation."""

    id: str
    label: str
    survey: str
    item: str

    @property
    def identity(self) -> SurveyItem | None:
        """The survey item this row *is*, or ``None`` for unanchored rows."""

        if self.survey and self.item:
            return (self.survey, self.item)
        return None


@dataclass
class Concept:
    """A materialised comparative concept = one character / one matrix row."""

    uid: str
    label: str
    members: list[str]  # concepts.csv row ids, sorted
    origin: str = "auto"  # "auto" | "manual:split" | "manual:merge"


@dataclass(frozen=True)
class ConceptIdentity:
    """The full materialised identity for a workspace."""

    concepts: list[Concept]
    uid_by_row: dict[str, str] = field(default_factory=dict)
    rows_by_uid: dict[str, list[str]] = field(default_factory=dict)
    # Non-fatal problems surfaced for the caller (e.g. an unreadable override
    # file, dropped unknown member ids, or a uid collision). Never silent: the
    # override file holds the linguist's authoritative decisions, so a failure
    # to apply them must be visible rather than reverting to the auto grouping
    # without a trace.
    warnings: list[str] = field(default_factory=list)

    def uid_for_row(self, row_id: object) -> str | None:
        return self.uid_by_row.get(str(row_id or "").strip())

    def members_for_uid(self, uid: str) -> list[str]:
        return list(self.rows_by_uid.get(uid, []))


# --------------------------------------------------------------------------- #
# Input normalisation
# --------------------------------------------------------------------------- #
def _concept_rows(project_root: Path) -> list[ConceptRow]:
    rows: list[ConceptRow] = []
    for raw in read_concepts_csv_rows(project_root / "concepts.csv"):
        rid = str(row_value(raw, "id") or "").strip()
        if not rid:
            continue
        rows.append(
            ConceptRow(
                id=rid,
                label=str(row_value(raw, "concept_en") or "").strip(),
                survey=normalize_survey_id(row_value(raw, "source_survey")),
                item=str(row_value(raw, "source_item") or "").strip(),
            )
        )
    return rows


def _cross_links(row_id: str, state: Mapping[str, Any]) -> list[SurveyItem]:
    """Explicit *sidecar* cross-survey links for a row (legacy CSV columns are
    the row's own identity, not a cross-link, so they are excluded)."""

    root = state.get("concept_survey_links") if isinstance(state, Mapping) else None
    links = root.get(row_id) if isinstance(root, Mapping) else None
    out: list[SurveyItem] = []
    if isinstance(links, Mapping):
        for survey, item in links.items():
            sid = normalize_survey_id(survey)
            it = str(item or "").strip()
            if sid and it:
                out.append((sid, it))
    return out


# --------------------------------------------------------------------------- #
# Closure (auto suggestion)
# --------------------------------------------------------------------------- #
class _UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, x: str) -> str:
        parent = self._parent
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def components(self) -> list[list[str]]:
        groups: dict[str, list[str]] = {}
        for item in self._parent:
            groups.setdefault(self.find(item), []).append(item)
        return list(groups.values())


def compute_auto_components(
    rows: Sequence[ConceptRow], state: Mapping[str, Any]
) -> list[list[str]]:
    """Connected components of rows under the explicit cross-link relation.

    An edge joins row ``A`` to row ``B`` iff one of ``A``'s explicit cross-survey
    links resolves to ``B``'s survey-item identity (and symmetrically). Rows that
    merely share a ``source_item`` are **not** joined.
    """

    by_id = {row.id: row for row in rows}
    identity_to_rows: dict[SurveyItem, list[str]] = {}
    for row in rows:
        ident = row.identity
        if ident is not None:
            identity_to_rows.setdefault(ident, []).append(row.id)

    uf = _UnionFind(by_id.keys())
    for row in rows:
        for target in _cross_links(row.id, state):
            for other in identity_to_rows.get(target, ()):
                uf.union(row.id, other)

    # Deterministic ordering: members sorted, components by smallest member.
    components = [_sorted_ids(group) for group in uf.components()]
    components.sort(key=lambda group: _id_sort_key(group[0]))
    return components


# --------------------------------------------------------------------------- #
# Overrides (linguist authority) + materialisation
# --------------------------------------------------------------------------- #
def _load_overrides(project_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Return ``(overrides, warnings)``. A malformed/unreadable override file
    yields a warning rather than silently discarding the linguist's splits."""

    path = project_root / CONCEPT_IDENTITY_FILENAME
    if not path.exists():
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return [], [
            f"{CONCEPT_IDENTITY_FILENAME} could not be read ({error.__class__.__name__}); "
            "manual concept splits/merges were NOT applied — falling back to the auto grouping."
        ]
    raw = payload.get("concepts") if isinstance(payload, Mapping) else None
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, Mapping):
                continue
            members = [
                str(m or "").strip()
                for m in (entry.get("members") or [])
                if str(m or "").strip()
            ]
            if not members:
                continue
            out.append(
                {
                    "uid": str(entry.get("uid") or "").strip(),
                    "label": str(entry.get("label") or "").strip(),
                    "members": members,
                    "origin": str(entry.get("origin") or "manual:merge").strip() or "manual:merge",
                }
            )
    return out, []


def _auto_label(member_ids: Sequence[str], by_id: Mapping[str, ConceptRow]) -> str:
    """Cleanest gloss among members: shortest variant-stem, tie-break lowest id."""

    best_label = ""
    best_key: tuple[int, tuple[int, str]] | None = None
    for rid in member_ids:
        row = by_id.get(rid)
        if row is None:
            continue
        stem = variant_stem(row.label) or row.label
        key = (len(stem), _id_sort_key(rid))
        if best_key is None or key < best_key:
            best_key, best_label = key, stem
    return best_label


def _auto_uid(member_ids: Sequence[str]) -> str:
    return f"c-{_sorted_ids(member_ids)[0]}" if member_ids else "c-empty"


def _unique_uid(candidate: str, used: set[str]) -> str:
    """Return ``candidate`` if free, else the first ``candidate-2``, ``-3`` … that
    is not yet taken. Guards against a manual uid colliding with an auto-derived
    one (which would otherwise overwrite a concept in the uid lookup)."""

    if candidate not in used:
        return candidate
    suffix = 2
    while f"{candidate}-{suffix}" in used:
        suffix += 1
    return f"{candidate}-{suffix}"


def materialize(
    rows: Sequence[ConceptRow],
    state: Mapping[str, Any],
    overrides: Sequence[Mapping[str, Any]],
    *,
    warnings: Sequence[str] = (),
) -> ConceptIdentity:
    """Closure → apply manual overrides → materialised, deterministic concepts."""

    by_id = {row.id: row for row in rows}
    valid_ids = set(by_id)
    notices: list[str] = list(warnings)
    used_uids: set[str] = set()

    def _add(concept_uid: str, label: str, members: list[str], origin: str) -> None:
        unique = _unique_uid(concept_uid, used_uids)
        if unique != concept_uid:
            notices.append(
                f"concept uid '{concept_uid}' collided and was renamed to '{unique}'."
            )
        used_uids.add(unique)
        concepts.append(Concept(uid=unique, label=label, members=members, origin=origin))

    # 1. Manual concepts are authoritative for the rows they claim. Drop member
    #    ids that no longer exist (reconcile-on-load: never silently keep orphans).
    claimed: set[str] = set()
    concepts: list[Concept] = []
    for entry in overrides:
        requested = [m for m in entry["members"] if m]
        unknown = [m for m in requested if m not in valid_ids]
        members = _sorted_ids(m for m in requested if m in valid_ids and m not in claimed)
        label_hint = entry["label"] or (entry["uid"] or "?")
        if unknown:
            notices.append(
                f"concept '{label_hint}' referenced {len(unknown)} unknown row id(s) "
                f"({', '.join(unknown)}); they were dropped."
            )
        if not members:
            continue
        claimed.update(members)
        _add(
            entry["uid"] or _auto_uid(members),
            entry["label"] or _auto_label(members, by_id),
            members,
            entry["origin"] or "manual:merge",
        )

    # 2. Remaining rows keep their auto grouping, minus any claimed members
    #    (a split removes some members; what's left is still an auto concept).
    for component in compute_auto_components(rows, state):
        members = [rid for rid in component if rid not in claimed]
        if not members:
            continue
        _add(_auto_uid(members), _auto_label(members, by_id), members, "auto")

    concepts.sort(key=lambda c: _id_sort_key(c.members[0]) if c.members else (1, "9" * 9))

    uid_by_row: dict[str, str] = {}
    rows_by_uid: dict[str, list[str]] = {}
    for concept in concepts:
        rows_by_uid[concept.uid] = list(concept.members)
        for rid in concept.members:
            uid_by_row[rid] = concept.uid

    return ConceptIdentity(
        concepts=concepts,
        uid_by_row=uid_by_row,
        rows_by_uid=rows_by_uid,
        warnings=notices,
    )


def load_concept_identity(
    project_root: Path,
    *,
    state: SurveyOverlapState | None = None,
) -> ConceptIdentity:
    """Top-level entry point: read inputs and return the materialised identity."""

    project_root = Path(project_root)
    rows = _concept_rows(project_root)
    overlap = state if state is not None else load_survey_overlap_state(project_root)
    overrides, warnings = _load_overrides(project_root)
    return materialize(rows, overlap, overrides, warnings=warnings)


def identity_payload(identity: ConceptIdentity) -> dict[str, Any]:
    """Serialise the full materialised identity (auto + manual) for the sidecar
    or API. Round-trips through ``_load_overrides``."""

    return {
        "version": 1,
        "concepts": [
            {
                "uid": concept.uid,
                "label": concept.label,
                "members": list(concept.members),
                "origin": concept.origin,
            }
            for concept in identity.concepts
        ],
    }


# --------------------------------------------------------------------------- #
# Deterministic id ordering (numeric-aware: "9" < "10")
# --------------------------------------------------------------------------- #
def _id_sort_key(row_id: str) -> tuple[int, object]:
    text = str(row_id or "").strip()
    return (0, int(text)) if text.isdigit() else (1, text)


def _sorted_ids(ids: Iterable[str]) -> list[str]:
    return sorted({str(i or "").strip() for i in ids if str(i or "").strip()}, key=_id_sort_key)
