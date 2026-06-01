"""Build Compare bundle payloads for variants, survey buckets, and canonical lexemes.

Bundle ids are deterministic for a workspace: rows are read in ``concepts.csv``
order, grouped by a normalized stem (variant suffixes such as ``(A)`` removed),
then assigned ``bundle:<stem-slug>``. If two distinct stems slugify to the same
value, later first-encountered stems receive ``-2``, ``-3`` suffixes. Every
payload includes ``row_ids`` so callers can repair choices if labels change.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from canonical_lexemes import load_canonical_lexemes, load_enrichments
from concept_canonical import variant_stem, variant_suffix
from concept_source_item import read_concepts_csv_rows, row_value
from survey_overlap import concept_survey_links_for_row, load_survey_overlap_state, normalize_survey_id

_WS_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
BUCKET_SEP = "\u0000"


def _stem(label: str) -> str:
    return variant_stem(label)


def _variant_label(label: str) -> str:
    return variant_suffix(label)


def _stem_key(label: str) -> str:
    return _WS_RE.sub(" ", _stem(label).casefold()).strip()


def _slug(stem: str) -> str:
    slug = _SLUG_RE.sub("-", str(stem or "").casefold()).strip("-")
    return slug or "concept"


def _bucket_key(survey_id: str, source_item: str) -> str:
    return "{0}{1}{2}".format(survey_id, BUCKET_SEP, source_item)


def _load_project_speakers(project_root: Path) -> list[str]:
    path = Path(project_root) / "project.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    speakers = payload.get("speakers") if isinstance(payload, Mapping) else None
    if isinstance(speakers, Mapping):
        return [str(s) for s in speakers.keys() if str(s).strip()]
    if isinstance(speakers, list):
        return [str(s) for s in speakers if str(s).strip()]
    return []


def _annotation_path(project_root: Path, speaker: str) -> Path:
    annotations = Path(project_root) / "annotations"
    parse_path = annotations / f"{speaker}.parse.json"
    if parse_path.exists():
        return parse_path
    return annotations / f"{speaker}.json"


def _source_wav_from_annotation(payload: Mapping[str, Any], speaker: str) -> str:
    raw = str(payload.get("source_audio") or payload.get("source_wav") or "").strip()
    audio = payload.get("audio")
    if not raw and isinstance(audio, Mapping):
        raw = str(audio.get("source_audio") or audio.get("source_wav") or audio.get("path") or "").strip()
    source_wav = raw.replace("\\", "/").strip()
    if not source_wav:
        source_wav = f"{speaker}.wav"
    if "/" not in source_wav and not Path(source_wav).is_absolute():
        source_wav = f"audio/working/{speaker}/{source_wav}"
    return source_wav


TierIntervals = dict[str, list[dict[str, Any]]]


def _tier_intervals(tiers: object, name: str) -> list[dict[str, Any]]:
    tier = tiers.get(name) if isinstance(tiers, Mapping) else None
    intervals = tier.get("intervals") if isinstance(tier, Mapping) else None
    return [iv for iv in intervals if isinstance(iv, dict)] if isinstance(intervals, list) else []


def _intervals_for_speaker(project_root: Path, speaker: str) -> tuple[TierIntervals, str]:
    empty: TierIntervals = {"concept": [], "ortho": [], "ipa": []}
    path = _annotation_path(project_root, speaker)
    if not path.exists():
        return empty, f"audio/working/{speaker}/{speaker}.wav"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return empty, f"audio/working/{speaker}/{speaker}.wav"
    tiers = payload.get("tiers") if isinstance(payload, Mapping) else None
    source_wav = _source_wav_from_annotation(payload, speaker) if isinstance(payload, Mapping) else f"audio/working/{speaker}/{speaker}.wav"
    return {
        "concept": _tier_intervals(tiers, "concept"),
        "ortho": _tier_intervals(tiers, "ortho"),
        "ipa": _tier_intervals(tiers, "ipa"),
    }, source_wav


def _interval_concept_id(interval: Mapping[str, Any]) -> str:
    return str(interval.get("concept_id") or interval.get("conceptId") or "").strip()


def _group_by_concept_id(
    intervals: Sequence[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    missing: list[dict[str, Any]] = []
    for interval in intervals:
        cid = _interval_concept_id(interval)
        if cid:
            grouped.setdefault(cid, []).append(interval)
        else:
            missing.append(interval)
    return grouped, missing


def _seconds(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _overlap_seconds(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    left_start = _seconds(left.get("start") or left.get("start_sec"))
    left_end = _seconds(left.get("end") or left.get("end_sec"))
    right_start = _seconds(right.get("start") or right.get("start_sec"))
    right_end = _seconds(right.get("end") or right.get("end_sec"))
    return max(0.0, min(left_end, right_end) - max(left_start, right_start))


def _pick_time_overlap(
    candidates: Sequence[dict[str, Any]],
    concept_interval: Mapping[str, Any],
) -> dict[str, Any] | None:
    overlapping = [candidate for candidate in candidates if _overlap_seconds(candidate, concept_interval) > 0]
    if not overlapping:
        return None
    concept_start = _seconds(concept_interval.get("start") or concept_interval.get("start_sec"))
    return min(
        overlapping,
        key=lambda candidate: abs(_seconds(candidate.get("start") or candidate.get("start_sec")) - concept_start),
    )


def _pick_sibling(
    siblings_for_cid: Sequence[dict[str, Any]],
    all_siblings: Sequence[dict[str, Any]],
    concept_interval: Mapping[str, Any],
    concept_index: int,
) -> dict[str, Any] | None:
    # Prefer a deterministic conceptId/index match; only then fall back to
    # time overlap across the whole tier.
    if 0 <= concept_index < len(siblings_for_cid):
        return siblings_for_cid[concept_index]
    return _pick_time_overlap(all_siblings, concept_interval)


def _candidate_from_interval(
    interval: Mapping[str, Any],
    source_wav: str,
    *,
    ortho_interval: Mapping[str, Any] | None = None,
    ipa_interval: Mapping[str, Any] | None = None,
    allow_interval_transcription: bool = True,
) -> dict[str, Any]:
    ipa = (ipa_interval or {}).get("text") if ipa_interval else None
    if not ipa and allow_interval_transcription:
        ipa = interval.get("ipa") or interval.get("ipa_text")
    ortho = (ortho_interval or {}).get("text") if ortho_interval else None
    if not ortho and allow_interval_transcription:
        ortho = interval.get("ortho") or interval.get("orthography")
    return {
        "ipa": str(ipa) if ipa else None,
        "ortho": str(ortho) if ortho else "",
        "start_sec": float(interval.get("start") or interval.get("start_sec") or 0.0),
        "end_sec": float(interval.get("end") or interval.get("end_sec") or 0.0),
        "source_wav": source_wav,
    }


def _active_links(row: Mapping[str, Any], speaker: str | None, state: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    # Precedence: speaker_concept_survey_links -> speaker_choices -> global concept_survey_links -> legacy CSV columns.
    row_id = str(row_value(row, "id") or "").strip()
    if speaker:
        speaker_root = state.get("speaker_concept_survey_links") if isinstance(state, Mapping) else None
        speaker_links = speaker_root.get(speaker) if isinstance(speaker_root, Mapping) else None
        row_links = speaker_links.get(row_id) if isinstance(speaker_links, Mapping) else None
        if isinstance(row_links, Mapping) and row_links:
            return "speaker_override", {normalize_survey_id(k): str(v).strip() for k, v in row_links.items() if normalize_survey_id(k) and str(v).strip()}
        choices_root = state.get("speaker_choices") if isinstance(state, Mapping) else None
        choices = choices_root.get(speaker) if isinstance(choices_root, Mapping) else None
        chosen_survey = normalize_survey_id(choices.get(row_id)) if isinstance(choices, Mapping) else ""
        if chosen_survey:
            all_links = concept_survey_links_for_row(row, state)
            if chosen_survey in all_links:
                return "speaker_choice", {chosen_survey: all_links[chosen_survey]}
    return "global_or_legacy", concept_survey_links_for_row(row, state)


def _migration_selection(bundle: Mapping[str, Any], speaker: str, enrichments: Mapping[str, Any]) -> dict[str, Any] | None:
    overrides = enrichments.get("manual_overrides") if isinstance(enrichments, Mapping) else None
    raw = overrides.get("canonical_realizations") if isinstance(overrides, Mapping) else None
    if not isinstance(raw, Mapping):
        return None
    labels = [str(bundle.get("label") or ""), str(bundle.get("bundle_id") or "")]
    row_ids = list(bundle.get("row_ids") or [])
    value = None
    for key in labels:
        block = raw.get(key)
        if isinstance(block, Mapping) and speaker in block:
            value = block.get(speaker)
            break
    if value is None:
        return None
    try:
        idx = int(value)
    except (TypeError, ValueError):
        return None
    if idx < 0 or idx >= len(row_ids):
        return None
    row_id = str(row_ids[idx])
    for bucket in bundle.get("buckets") or []:
        for variant in bucket.get("variants") or []:
            if variant.get("csv_row_id") == row_id:
                return {
                    "csv_row_id": row_id,
                    "survey_id": bucket.get("survey_id", ""),
                    "source_item": bucket.get("source_item", ""),
                    "bucket_key": bucket.get("bucket_key", ""),
                    "variant_label": variant.get("variant_label", ""),
                    "realization_index": idx,
                    "source": "migration:canonical_realizations",
                }
    return None


def _selection_for_row(bundle: Mapping[str, Any], row_id: str, *, source: str, realization_index: int | None = None) -> dict[str, Any] | None:
    for bucket in bundle.get("buckets") or []:
        for variant in bucket.get("variants") or []:
            if variant.get("csv_row_id") == row_id:
                selection = {
                    "csv_row_id": row_id,
                    "survey_id": bucket.get("survey_id", ""),
                    "source_item": bucket.get("source_item", ""),
                    "bucket_key": bucket.get("bucket_key", ""),
                    "variant_label": variant.get("variant_label", ""),
                    "realization_index": 0 if realization_index is None else realization_index,
                    "source": source,
                }
                return selection
    return None


def build_compare_bundles(project_root: Path, *, speakers: Sequence[str] | None = None, bundle_id: str | None = None) -> dict[str, Any]:
    project_root = Path(project_root)
    rows = [row for row in read_concepts_csv_rows(project_root / "concepts.csv") if row.get("id") and row.get("concept_en")]
    overlap = load_survey_overlap_state(project_root)
    enrichments = load_enrichments(project_root)
    stored_canonical = load_canonical_lexemes(project_root)
    selected_speakers = list(speakers) if speakers is not None else _load_project_speakers(project_root)

    # Index each speaker's annotation ONCE, up front. Previously the load +
    # interval grouping below ran inside the per-bundle loop, so each speaker's
    # full annotation JSON was read and re-parsed once per concept group
    # (O(bundles x speakers) reparses of a handful of files). Nothing here
    # depends on the bundle, so hoisting it makes the work O(speakers) and is
    # byte-identical: the matching helpers below only read these structures.
    speaker_index: dict[str, dict[str, Any]] = {}
    for speaker in selected_speakers:
        tiers, source_wav = _intervals_for_speaker(project_root, speaker)
        by_concept: dict[str, list[dict[str, Any]]] = {}
        legacy_by_text: dict[str, list[dict[str, Any]]] = {}
        for interval in tiers["concept"]:
            cid = _interval_concept_id(interval)
            if cid:
                by_concept.setdefault(cid, []).append(interval)
            else:
                legacy_by_text.setdefault(_stem_key(str(interval.get("text") or "")), []).append(interval)
        ortho_by_concept, _ = _group_by_concept_id(tiers["ortho"])
        ipa_by_concept, _ = _group_by_concept_id(tiers["ipa"])
        speaker_index[speaker] = {
            "tiers": tiers,
            "source_wav": source_wav,
            "by_concept": by_concept,
            "legacy_by_text": legacy_by_text,
            "ortho_by_concept": ortho_by_concept,
            "ipa_by_concept": ipa_by_concept,
        }

    # Group rows into bundles by union-find. Two rows merge when they share a
    # normalized stem (variant suffixes such as "(A)") OR a cross-survey identity
    # declared in the overlap sidecar. The latter is essential: e.g. "salt"
    # (KLQ 3.14) and "salt (eating)" (JBIL 139) cross-reference each other, so
    # they are one concept — but their English stems differ ("salt" vs
    # "salt (eating)"), so a stem-only grouping splits them and a speaker's
    # candidates get read from only one of the linked concept ids.
    parent: dict[str, str] = {}

    def _find(node: str) -> str:
        parent.setdefault(node, node)
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    def _union(a: str, b: str) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra

    def _id_sort_key(value: object) -> tuple[int, object]:
        text = str(value or "").strip()
        return (0, int(text)) if text.isdigit() else (1, text)

    row_by_id: dict[str, Mapping[str, Any]] = {}
    row_order: list[str] = []
    stem_rep: dict[str, str] = {}
    pair_rep: dict[tuple[str, str], str] = {}
    for row in rows:
        rid = str(row.get("id"))
        row_by_id[rid] = row
        row_order.append(rid)
        _find(rid)
        stem = _stem_key(row.get("concept_en", ""))
        if stem:
            if stem in stem_rep:
                _union(stem_rep[stem], rid)
            else:
                stem_rep[stem] = rid
        for survey_id, source_item in concept_survey_links_for_row(row, overlap).items():
            pair = (normalize_survey_id(survey_id), str(source_item or "").strip())
            if not pair[0] or not pair[1]:
                continue
            if pair in pair_rep:
                _union(pair_rep[pair], rid)
            else:
                pair_rep[pair] = rid

    groups: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for rid in row_order:
        root = _find(rid)
        if root not in groups:
            groups[root] = {"label": "", "rows": []}
            ordered_keys.append(root)
        groups[root]["rows"].append(row_by_id[rid])
    # Bundle label: prefer a clean gloss (no parenthetical clarifier), then the
    # shortest, then the lowest concept id — so a merged group shows "salt", not
    # "salt (eating)".
    for root in ordered_keys:
        rep = sorted(
            groups[root]["rows"],
            key=lambda r: ("(" in str(r.get("concept_en", "")), len(str(r.get("concept_en", ""))), _id_sort_key(r.get("id"))),
        )[0]
        groups[root]["label"] = _stem(rep.get("concept_en", "")) or rep.get("concept_en", "")

    used_slugs: dict[str, int] = {}
    built: list[dict[str, Any]] = []
    for key in ordered_keys:
        group = groups[key]
        slug = _slug(group["label"])
        used_slugs[slug] = used_slugs.get(slug, 0) + 1
        suffix = "" if used_slugs[slug] == 1 else f"-{used_slugs[slug]}"
        bid = f"bundle:{slug}{suffix}"
        bucket_map: dict[str, dict[str, Any]] = {}
        row_ids: list[str] = []
        warnings: list[str] = []
        # For a single-speaker query, bucket resolution honors that speaker's overrides.
        resolution_speaker = selected_speakers[0] if len(selected_speakers) == 1 else None
        for row in group["rows"]:
            row_id = str(row["id"])
            row_ids.append(row_id)
            _source, links = _active_links(row, resolution_speaker, overlap)
            for survey_id, source_item in links.items() or {"": ""}.items():
                key2 = _bucket_key(survey_id, source_item)
                bucket = bucket_map.setdefault(key2, {"bucket_key": key2, "survey_id": survey_id, "source_item": source_item, "variants": []})
                bucket["variants"].append({"csv_row_id": row_id, "variant_label": _variant_label(row.get("concept_en", "")), "concept_en": row.get("concept_en", "")})
        bundle = {"bundle_id": bid, "label": group["label"], "row_ids": row_ids, "buckets": list(bucket_map.values()), "candidates": {}, "canonical": {}, "warnings": warnings}
        concept_links = overlap.get("concept_survey_links") if isinstance(overlap, Mapping) else None
        bundle["concept_survey_links"] = {
            row_id: dict(concept_links.get(row_id, {}))
            for row_id in row_ids
            if isinstance(concept_links, Mapping) and concept_links.get(row_id)
        }
        speaker_choices = overlap.get("speaker_choices") if isinstance(overlap, Mapping) else None
        bundle["speaker_choices"] = {}
        if isinstance(speaker_choices, Mapping):
            for speaker, choices in speaker_choices.items():
                if not isinstance(choices, Mapping):
                    continue
                scoped = {row_id: choices[row_id] for row_id in row_ids if row_id in choices}
                if scoped:
                    bundle["speaker_choices"][str(speaker)] = scoped
        speaker_links = overlap.get("speaker_concept_survey_links") if isinstance(overlap, Mapping) else None
        bundle["speaker_concept_survey_links"] = {}
        if isinstance(speaker_links, Mapping):
            for speaker, by_row in speaker_links.items():
                if not isinstance(by_row, Mapping):
                    continue
                scoped = {row_id: dict(by_row.get(row_id, {})) for row_id in row_ids if by_row.get(row_id)}
                if scoped:
                    bundle["speaker_concept_survey_links"][str(speaker)] = scoped
        for speaker in selected_speakers:
            idx = speaker_index[speaker]
            tiers = idx["tiers"]
            source_wav = idx["source_wav"]
            by_concept = idx["by_concept"]
            legacy_by_text = idx["legacy_by_text"]
            ortho_by_concept = idx["ortho_by_concept"]
            ipa_by_concept = idx["ipa_by_concept"]
            speaker_candidates: dict[str, Any] = {}
            candidate_rows: list[str] = []
            for row in group["rows"]:
                row_id = str(row["id"])
                matches = by_concept.get(row_id, [])
                used_legacy_text_fallback = False
                if not matches:
                    legacy_matches = legacy_by_text.get(_stem_key(row.get("concept_en", "")), [])
                    if legacy_matches:
                        matches = legacy_matches
                        used_legacy_text_fallback = True
                        warnings.append(f"legacy text fallback used for {speaker} row {row_id}")
                if matches:
                    # A speaker can record several realizations (A/B/…) of one
                    # concept. Sort by start so realization_index matches the
                    # start-rank letters Annotate assigns (A = earliest).
                    matches = sorted(
                        matches,
                        key=lambda interval: _seconds(interval.get("start", interval.get("start_sec", 0.0))),
                    )
                    realizations: list[dict[str, Any]] = []
                    for concept_interval in matches:
                        cid = _interval_concept_id(concept_interval)
                        ortho_interval = (
                            _pick_sibling(ortho_by_concept.get(cid, []), tiers["ortho"], concept_interval, 0)
                            if cid
                            else None
                        )
                        ipa_interval = (
                            _pick_sibling(ipa_by_concept.get(cid, []), tiers["ipa"], concept_interval, 0)
                            if cid
                            else None
                        )
                        realizations.append(
                            _candidate_from_interval(
                                concept_interval,
                                source_wav,
                                ortho_interval=ortho_interval,
                                ipa_interval=ipa_interval,
                                allow_interval_transcription=not used_legacy_text_fallback,
                            )
                        )
                    # The row's primary candidate stays the first realization, so
                    # single-realization rows are byte-identical to before. When a
                    # speaker has 2+ realizations, every one rides along under
                    # "realizations" (each tagged with its start-rank index) so
                    # Compare can show and select B, C, … — not just the first.
                    if len(realizations) > 1:
                        for index, entry in enumerate(realizations):
                            entry["realization_index"] = index
                    candidate = dict(realizations[0])
                    if len(realizations) > 1:
                        candidate["realizations"] = realizations
                    speaker_candidates[row_id] = candidate
                    candidate_rows.append(row_id)
                else:
                    speaker_candidates[row_id] = None
            bundle["candidates"][speaker] = speaker_candidates
            manual = stored_canonical.get(bid, {}).get(speaker)
            effective = None
            if manual:
                effective = _selection_for_row(bundle, str(manual.get("csv_row_id") or ""), source=str(manual.get("source") or "manual"), realization_index=manual.get("realization_index"))
                if effective:
                    effective.update({k: v for k, v in manual.items() if k in {"selected_at", "source"}})
            if effective is None:
                effective = _migration_selection(bundle, speaker, enrichments)
            if effective is None and len(candidate_rows) == 1:
                effective = _selection_for_row(bundle, candidate_rows[0], source="default:single-candidate", realization_index=0)
            if effective is not None:
                bundle["canonical"][speaker] = effective
                if speaker_candidates.get(effective["csv_row_id"]) is None:
                    warnings.append(f"selected canonical for {speaker} has no annotation form.")
            elif len(candidate_rows) > 1:
                warnings.append(f"{speaker} has {len(candidate_rows)} candidates for {bid}; 2+ candidates, no canonical chosen")
            else:
                warnings.append(f"no annotation for {speaker} on {bid}")
        built.append(bundle)

    if bundle_id:
        built = [bundle for bundle in built if bundle["bundle_id"] == bundle_id]
    return {"bundles": built}


def effective_canonical_for_bundle(bundle: Mapping[str, Any], speaker: str) -> dict[str, Any] | None:
    selection = (bundle.get("canonical") or {}).get(speaker) if isinstance(bundle.get("canonical"), Mapping) else None
    return selection if isinstance(selection, Mapping) else None


def candidate_for_selection(bundle: Mapping[str, Any], speaker: str, selection: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not selection:
        return None
    candidates = (bundle.get("candidates") or {}).get(speaker) if isinstance(bundle.get("candidates"), Mapping) else None
    if not isinstance(candidates, Mapping):
        return None
    candidate = candidates.get(str(selection.get("csv_row_id") or ""))
    return candidate if isinstance(candidate, Mapping) else None


def _tsv(value: object) -> str:
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def build_canonical_lexemes_report_tsv(payload: Mapping[str, Any]) -> str:
    lines = ["speaker\tbundle_id\tbundle_label\tcsv_row_id\tsurvey_id\tsource_item\tvariant_label\tipa\tortho\tsource"]
    for bundle in payload.get("bundles", []) if isinstance(payload, Mapping) else []:
        speakers = sorted((bundle.get("candidates") or {}).keys())
        for speaker in speakers:
            selection = effective_canonical_for_bundle(bundle, speaker)
            candidate = candidate_for_selection(bundle, speaker, selection)
            if selection:
                row = [
                    speaker,
                    bundle.get("bundle_id", ""),
                    bundle.get("label", ""),
                    selection.get("csv_row_id", ""),
                    selection.get("survey_id", ""),
                    selection.get("source_item", ""),
                    selection.get("variant_label", ""),
                    candidate.get("ipa", "") if candidate else "",
                    candidate.get("ortho", "") if candidate else "",
                    selection.get("source", ""),
                ]
            else:
                row = [speaker, bundle.get("bundle_id", ""), bundle.get("label", ""), "", "", "", "", "", "", "BLANK"]
            lines.append("\t".join(_tsv(cell) for cell in row))
    return "\n".join(lines) + "\n"
