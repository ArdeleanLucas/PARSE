"""Consolidated, tag-filtered cognate matrix for phylogenetic export.

This module builds the LingPy TSV / NEXUS matrix the *way PARSE's Compare view
already organizes the data*: survey-overlap duplicate concept ids (e.g. big =
``53`` and ``150``) are folded into a single canonical character instead of
emitting one character block per id.

It is a thin composition of existing PARSE pieces — it does **not** invent new
cognate logic:

- ``concept_linking.build_canonical_gloss_index`` decides which concept ids fold
  together (the same cross-survey gloss normalization the rest of PARSE uses).
- ``concept_character_audit._export_style_cognate_columns`` reads the committed
  cognate decisions in the exact shape the NEXUS exporter uses.
- A canonical group is collapsed **only** when its members are byte-identical
  (``safe_union`` in the MC-439 audit). Groups whose per-id cognate letters
  differ (``needs_recluster``) are *not* silently merged — their letters are not
  cross-comparable — and are kept separate with a warning.

Optionally restricts the matrix to a concept tag (e.g. the thesis tag
``custom-sk-concept-list``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from concept_linking import build_canonical_gloss_index
from concept_character_audit import _column_signature, _export_style_cognate_columns

from compare.cognate_compute import (
    WORDLIST_TSV_COLUMNS,
    _build_cogid_lookup,
    _concept_sort_key,
    _normalize_ipa,
    _speaker_lookup_key,
    _tokenize_ipa_for_wordlist,
    load_annotations,
)


CognateSets = Dict[str, Dict[str, List[str]]]


def tag_concept_ids(tags_payload: Any, tag_id: str) -> Set[str]:
    """Return the set of concept ids carried by ``tag_id`` in parse-tags.json.

    Accepts the list-of-tags shape (``[{id, label, concepts}, …]``) and the
    ``{"tags": [...]}`` wrapper. ``concepts`` may be a list of ids or a mapping
    keyed by id.
    """
    tags = tags_payload
    if isinstance(tags_payload, Mapping):
        tags = tags_payload.get("tags", [])
    if not isinstance(tags, list):
        return set()
    for tag in tags:
        if not isinstance(tag, Mapping):
            continue
        if str(tag.get("id") or tag.get("name") or "") != str(tag_id):
            continue
        concepts = tag.get("concepts") or []
        if isinstance(concepts, Mapping):
            return {str(k) for k in concepts.keys() if str(k).strip()}
        if isinstance(concepts, list):
            return {str(c) for c in concepts if str(c).strip()}
    return set()


def build_consolidated_cognate_sets(
    concepts_rows: Sequence[Mapping[str, Any]],
    enrichments: Mapping[str, Any],
    allowed_ids: Optional[Set[str]] = None,
) -> Tuple[CognateSets, Dict[str, Any], Dict[str, str]]:
    """Fold survey-overlap duplicate concept ids into canonical characters.

    Returns ``(consolidated_sets, meta, id_to_key)`` where:

    - ``consolidated_sets`` is keyed by canonical gloss → ``{group: [speakers]}``
      in the same shape the NEXUS/TSV builders consume.
    - ``meta`` records which glosses were collapsed and any ``needs_recluster``
      warnings.
    - ``id_to_key`` maps every (allowed) concept id to its canonical gloss key,
      so the wordlist can remap form rows to the consolidated concept.
    """
    canonical_index = build_canonical_gloss_index(concepts_rows)
    columns = _export_style_cognate_columns(enrichments)

    consolidated: CognateSets = {}
    id_to_key: Dict[str, str] = {}
    collapsed: List[Dict[str, Any]] = []
    needs_recluster: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for canonical_key in sorted(canonical_index):
        ids = [
            cid
            for cid in canonical_index[canonical_key]
            if allowed_ids is None or cid in allowed_ids
        ]
        if not ids:
            continue
        for cid in ids:
            id_to_key[cid] = canonical_key

        member_columns = [(cid, columns.get(cid, {})) for cid in ids]
        coded = [(cid, cols) for cid, cols in member_columns if cols]
        if not coded:
            # Gloss exists but has no committed cognate decision yet — it still
            # contributes forms (uncoded) to the wordlist, just no characters.
            continue

        signatures = {_column_signature(cols) for _cid, cols in coded}
        if len(signatures) == 1:
            rep_id, rep_cols = coded[0]
            consolidated[canonical_key] = {
                str(group): list(members) for group, members in rep_cols.items()
            }
            if len(coded) > 1:
                collapsed.append(
                    {"gloss": canonical_key, "ids": [cid for cid, _ in coded], "kept": rep_id}
                )
        else:
            # Per-id letters are not cross-comparable; keep them separate rather
            # than fabricate a merge. A future re-clustering pass (MC-439) is the
            # correct fix.
            needs_recluster.append(
                {"gloss": canonical_key, "ids": [cid for cid, _ in coded]}
            )
            warnings.append(
                "{0}: cognate columns differ across ids {1}; kept separate "
                "(needs re-cluster, not byte-identical).".format(
                    canonical_key, [cid for cid, _ in coded]
                )
            )
            for cid, cols in coded:
                suffixed_key = "{0}#{1}".format(canonical_key, cid)
                consolidated[suffixed_key] = {
                    str(group): list(members) for group, members in cols.items()
                }
                # Route this id's forms to its OWN character key so the wordlist
                # and the NEXUS agree. Overrides the bare canonical mapping set
                # above: divergent per-id letters are not cross-comparable, so
                # the forms must not collapse onto a shared concept column.
                id_to_key[cid] = suffixed_key

    meta = {
        "collapsed": collapsed,
        "needs_recluster": needs_recluster,
        "warnings": warnings,
        "character_count": sum(len(groups) for groups in consolidated.values()),
        "concept_count": len(consolidated),
    }
    return consolidated, meta, id_to_key


def _sorted_concept_keys(cognate_sets: Mapping[str, Any]) -> List[str]:
    return sorted(cognate_sets.keys(), key=lambda k: (_concept_sort_key(k), k))


def build_nexus_from_sets(cognate_sets: CognateSets, speakers: Sequence[str]) -> str:
    """Render a NEXUS character matrix from a consolidated cognate-set map.

    Mirrors ``ai.tools.export_tools.build_nexus_text`` character semantics
    (1 = in group, 0 = has a form for the concept but a different group,
    ? = no form for the concept) but consumes a pre-consolidated map.
    """
    speaker_set: Set[str] = {str(s) for s in speakers if str(s).strip()}
    concept_keys = [k for k in cognate_sets if cognate_sets.get(k)]
    group_members: Dict[str, Dict[str, List[str]]] = {}
    for key in concept_keys:
        groups: Dict[str, List[str]] = {}
        for group, members in cognate_sets[key].items():
            cleaned = [str(m) for m in members if str(m).strip()]
            if cleaned:
                groups[str(group)] = cleaned
                speaker_set.update(cleaned)
        if groups:
            group_members[key] = groups

    concept_keys = [k for k in concept_keys if k in group_members]
    speakers_sorted = sorted(speaker_set)

    has_form: Dict[str, Set[str]] = {}
    for key in concept_keys:
        present: Set[str] = set()
        for members in group_members[key].values():
            present.update(members)
        has_form[key] = present

    characters: List[Tuple[str, str, str]] = []
    for key in _sorted_concept_keys(group_members):
        for group in sorted(group_members[key]):
            label = "{0}_{1}".format(str(key).replace(" ", "_"), group)
            characters.append((key, group, label))

    def row_for(speaker: str) -> str:
        chars: List[str] = []
        for key, group, _label in characters:
            members = group_members[key].get(group, [])
            if speaker in members:
                chars.append("1")
            elif speaker in has_form.get(key, set()):
                chars.append("0")
            else:
                chars.append("?")
        return "".join(chars)

    lines: List[str] = ["#NEXUS", "", "BEGIN TAXA;", "    DIMENSIONS NTAX={0};".format(len(speakers_sorted))]
    if speakers_sorted:
        lines.append("    TAXLABELS")
        lines.extend("        {0}".format(sp) for sp in speakers_sorted)
        lines.append("    ;")
    lines.append("END;")
    lines.append("")
    lines.append("BEGIN CHARACTERS;")
    lines.append("    DIMENSIONS NCHAR={0};".format(len(characters)))
    lines.append('    FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";')
    if characters:
        lines.append("    CHARSTATELABELS")
        lines.append(
            ",\n".join(
                "        {0} {1}".format(idx, label)
                for idx, (_k, _g, label) in enumerate(characters, start=1)
            )
        )
        lines.append("    ;")
    lines.append("    MATRIX")
    lines.extend("        {0}    {1}".format(sp, row_for(sp)) for sp in speakers_sorted)
    lines.append("    ;")
    lines.append("END;")
    lines.append("")
    return "\n".join(lines)


def build_wordlist_rows(
    annotations_dir: Path,
    cognate_sets: CognateSets,
    id_to_key: Mapping[str, str],
    allowed_ids: Optional[Set[str]] = None,
    canonical_lexemes: Optional[Mapping[str, Any]] = None,
) -> List[Tuple[Any, ...]]:
    """Build LingPy wordlist rows remapped onto consolidated canonical concepts.

    Forms are loaded per concept id, remapped to their canonical gloss, and
    de-duplicated per (gloss, speaker) keeping the earliest. COGID is looked up
    against the consolidated cognate sets.
    """
    forms_by_concept, _speakers = load_annotations(annotations_dir)
    cogid_lookup, cogid_group_by_speaker = _build_cogid_lookup(cognate_sets)

    selected_row_by_key_speaker: Dict[Tuple[str, str], str] = {}
    if isinstance(canonical_lexemes, Mapping):
        for speaker_map in canonical_lexemes.values():
            if not isinstance(speaker_map, Mapping):
                continue
            for speaker, selection in speaker_map.items():
                if not isinstance(selection, Mapping):
                    continue
                row_id = str(selection.get("csv_row_id") or "").strip()
                if not row_id:
                    continue
                key = id_to_key.get(row_id)
                if not key:
                    continue
                selected_row_by_key_speaker[(key, _speaker_lookup_key(str(speaker)))] = row_id

    # Remap and de-dup forms onto canonical gloss keys.
    by_key_speaker: Dict[Tuple[str, str], Any] = {}
    for concept_id, records in forms_by_concept.items():
        if allowed_ids is not None and concept_id not in allowed_ids:
            continue
        key = id_to_key.get(concept_id, concept_id)
        for record in records:
            sk = _speaker_lookup_key(record.speaker)
            slot = (key, sk)
            existing = by_key_speaker.get(slot)
            selected_row_id = selected_row_by_key_speaker.get(slot)
            if existing is None:
                by_key_speaker[slot] = record
            elif selected_row_id:
                record_is_selected = str(record.concept_id) == selected_row_id
                existing_is_selected = str(existing.concept_id) == selected_row_id
                if record_is_selected and not existing_is_selected:
                    by_key_speaker[slot] = record
                elif record_is_selected == existing_is_selected and record.start_sec < existing.start_sec:
                    by_key_speaker[slot] = record
            elif record.start_sec < existing.start_sec:
                by_key_speaker[slot] = record

    forms_by_key: Dict[str, List[Any]] = {}
    for (key, _sk), record in by_key_speaker.items():
        forms_by_key.setdefault(key, []).append(record)

    rows: List[Tuple[Any, ...]] = []
    row_id = 1
    for key in _sorted_concept_keys(forms_by_key):
        concept_groups = cogid_group_by_speaker.get(key, {})
        for record in sorted(forms_by_key[key], key=lambda r: (_speaker_lookup_key(r.speaker),)):
            ipa = _normalize_ipa(record.ipa)
            if not ipa:
                continue
            tokens = _tokenize_ipa_for_wordlist(ipa)
            if not tokens:
                continue
            speaker_key = _speaker_lookup_key(record.speaker)
            group_label = concept_groups.get(speaker_key, "")
            cogid = cogid_lookup.get((key, group_label), 0) if group_label else 0
            # Use the canonical gloss as the CONCEPT value: LingPy groups by this
            # column, so a single canonical concept must carry one consistent
            # label (not the per-form annotation text, which varies by variant).
            rows.append(
                (row_id, key, record.speaker, ipa, int(cogid), " ".join(tokens), 0)
            )
            row_id += 1
    return rows


def wordlist_rows_to_tsv(rows: Sequence[Tuple[Any, ...]]) -> str:
    out = ["\t".join(WORDLIST_TSV_COLUMNS)]
    out.extend("\t".join(str(value) for value in row) for row in rows)
    return "\n".join(out) + "\n"
