#!/usr/bin/env python3
"""Compute PARSE Compare enrichments via LingPy LexStat.

Example:
    python cognate_compute.py --annotations-dir ./annotations --concepts concepts.json --threshold 0.60 --output enrichments.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, TypedDict


DEFAULT_THRESHOLD = 0.60
DEFAULT_SIL_CONFIG = Path(__file__).resolve().parents[2] / "config" / "sil_contact_languages.json"
PREFERRED_CONTACT_LANGUAGES = ("ar", "fa")
FALLBACK_BOUNDARY_CHARS: Set[str] = {" ", "-", "_", ".", "|", "/"}
FALLBACK_ONSET_ALTERNATIONS: Tuple[Tuple[str, str], ...] = (
    ("k", "g"),
    ("q", "g"),
    ("t", "d"),
    ("p", "b"),
)
FALLBACK_CODA_DELETIONS: Tuple[str, ...] = ("k", "g", "q", "t", "d", "p", "b")
FALLBACK_MAX_VARIANTS = 32


@dataclass
class ConceptSpec:
    concept_id: str
    label: str = ""
    contact_forms: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class FormRecord:
    speaker: str
    concept_id: str
    concept_label: str
    ipa: str
    ortho: str
    start_sec: float
    end_sec: float


class SimilarityScore(TypedDict):
    score: Optional[float]
    has_reference_data: bool


def _warn(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


def _error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_ipa(value: Any) -> str:
    text = _normalize_space(value).lower()
    if text.startswith("/") and text.endswith("/") and len(text) >= 2:
        text = text[1:-1].strip()
    if text.startswith("[") and text.endswith("]") and len(text) >= 2:
        text = text[1:-1].strip()
    return text


def _parse_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _split_concept_text(raw_text: Any) -> Tuple[str, str]:
    text = _normalize_space(raw_text)
    if not text:
        return ("", "")

    if ":" in text:
        left, right = text.split(":", 1)
        return (_normalize_space(left), _normalize_space(right))

    return (text, "")


def _normalize_concept_key(raw_value: Any) -> str:
    text = _normalize_space(raw_value)
    if not text:
        return ""

    if text.startswith("#"):
        text = _normalize_space(text[1:])

    if ":" in text:
        text = _normalize_space(text.split(":", 1)[0])

    return text


def _concept_sort_key(concept_id: str) -> Tuple[int, float, str]:
    text = _normalize_concept_key(concept_id)
    try:
        return (0, float(text), text)
    except ValueError:
        return (1, float("inf"), text)


def _concept_out_value(concept_id: str) -> Any:
    normalized = _normalize_concept_key(concept_id)
    try:
        number = float(normalized)
    except ValueError:
        return normalized

    if number.is_integer():
        return int(number)
    return normalized


def _dedupe_non_empty_strings(values: Iterable[Any]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []

    for value in values:
        text = _normalize_space(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)

    return out


def _extract_forms(value: Any) -> List[str]:
    if isinstance(value, str):
        return _dedupe_non_empty_strings([value])

    if isinstance(value, list):
        return _dedupe_non_empty_strings(value)

    if isinstance(value, dict):
        candidates: List[Any] = []
        for key in ("form", "forms", "ipa", "orth", "orthography", "value", "variants", "refs"):
            if key in value:
                candidates.append(value.get(key))

        flattened: List[Any] = []
        for candidate in candidates:
            if isinstance(candidate, list):
                flattened.extend(candidate)
            else:
                flattened.append(candidate)

        return _dedupe_non_empty_strings(flattened)

    return []


def _best_overlap_text(start_sec: float, end_sec: float, intervals: Sequence[Mapping[str, Any]]) -> str:
    best_text = ""
    best_overlap = 0.0

    for interval in intervals:
        cand_start = _parse_float(interval.get("start"))
        cand_end = _parse_float(interval.get("end"))

        overlap = min(end_sec, cand_end) - max(start_sec, cand_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_text = _normalize_space(interval.get("text"))

    return best_text if best_overlap > 0 else ""


def _intervals_for_tier(annotation_data: Mapping[str, Any], tier_name: str) -> List[Dict[str, Any]]:
    tiers = annotation_data.get("tiers")
    if not isinstance(tiers, dict):
        return []

    tier_data = tiers.get(tier_name)
    if not isinstance(tier_data, dict):
        lower_name = tier_name.lower()
        for key, value in tiers.items():
            if isinstance(key, str) and key.lower() == lower_name and isinstance(value, dict):
                tier_data = value
                break

    if not isinstance(tier_data, dict):
        return []

    intervals = tier_data.get("intervals")
    if not isinstance(intervals, list):
        return []

    return [interval for interval in intervals if isinstance(interval, dict)]


def _speaker_from_annotation(path: Path, annotation_data: Mapping[str, Any]) -> str:
    speaker = _normalize_space(annotation_data.get("speaker"))
    if speaker:
        return speaker

    suffix = ".parse.json"
    if path.name.endswith(suffix):
        return path.name[: -len(suffix)]

    return path.stem


def _parse_annotation_file(path: Path) -> List[FormRecord]:
    annotation_data = _load_json(path)
    if not isinstance(annotation_data, dict):
        _warn(f"Ignoring non-object annotation file: {path}")
        return []

    speaker = _speaker_from_annotation(path, annotation_data)
    concept_intervals = _intervals_for_tier(annotation_data, "concept")
    ipa_intervals = _intervals_for_tier(annotation_data, "ipa")
    ortho_intervals = _intervals_for_tier(annotation_data, "ortho")

    by_concept: Dict[str, FormRecord] = {}

    for concept_interval in concept_intervals:
        start_sec = _parse_float(concept_interval.get("start"))
        end_sec = _parse_float(concept_interval.get("end"))
        if end_sec < start_sec:
            continue

        concept_id, concept_label = _split_concept_text(concept_interval.get("text"))
        concept_id = _normalize_concept_key(concept_id)
        if not concept_id:
            continue

        ipa_text = _best_overlap_text(start_sec, end_sec, ipa_intervals)
        ipa_norm = _normalize_ipa(ipa_text)
        if not ipa_norm:
            continue

        ortho_text = _best_overlap_text(start_sec, end_sec, ortho_intervals)
        candidate = FormRecord(
            speaker=speaker,
            concept_id=concept_id,
            concept_label=concept_label,
            ipa=ipa_norm,
            ortho=_normalize_space(ortho_text),
            start_sec=start_sec,
            end_sec=end_sec,
        )

        existing = by_concept.get(concept_id)
        if existing is None or candidate.start_sec < existing.start_sec:
            by_concept[concept_id] = candidate

    return [by_concept[key] for key in sorted(by_concept.keys(), key=_concept_sort_key)]


def load_annotations(annotations_dir: Path) -> Tuple[Dict[str, List[FormRecord]], List[str]]:
    if not annotations_dir.exists():
        raise FileNotFoundError(f"Annotations directory not found: {annotations_dir}")
    if not annotations_dir.is_dir():
        raise ValueError(f"Annotations path is not a directory: {annotations_dir}")

    forms_by_concept: Dict[str, List[FormRecord]] = {}
    speakers: Set[str] = set()

    files = sorted(annotations_dir.glob("*.parse.json"))
    if not files:
        _warn(f"No *.parse.json annotation files found in {annotations_dir}")

    for path in files:
        try:
            records = _parse_annotation_file(path)
        except Exception as exc:
            _warn(f"Failed to parse annotation file {path}: {exc}")
            continue

        for record in records:
            speakers.add(record.speaker)
            forms_by_concept.setdefault(record.concept_id, []).append(record)

    for concept_id, records in forms_by_concept.items():
        records.sort(key=lambda item: (item.speaker, item.start_sec, item.end_sec))
        deduped: Dict[str, FormRecord] = {}
        for record in records:
            existing = deduped.get(record.speaker)
            if existing is None or record.start_sec < existing.start_sec:
                deduped[record.speaker] = record
        forms_by_concept[concept_id] = [deduped[speaker] for speaker in sorted(deduped.keys())]

    return forms_by_concept, sorted(speakers)


def _row_to_concept_spec(row: Mapping[str, Any], row_index: int, language_codes: Optional[Set[str]] = None) -> Optional[ConceptSpec]:
    concept_id = _normalize_concept_key(
        row.get("id")
        or row.get("concept_id")
        or row.get("conceptId")
        or row.get("concept")
        or str(row_index + 1)
    )
    if not concept_id:
        return None

    label = _normalize_space(
        row.get("label")
        or row.get("concept_en")
        or row.get("english")
        or row.get("gloss")
        or row.get("name")
    )

    contact_forms: Dict[str, List[str]] = {}

    raw_contact_forms = row.get("contact_forms")
    if isinstance(raw_contact_forms, dict):
        for code, raw_forms in raw_contact_forms.items():
            code_text = _normalize_space(code).lower()
            if not code_text:
                continue
            forms = _extract_forms(raw_forms)
            if forms:
                contact_forms[code_text] = forms

    codes_to_check: Set[str] = set(language_codes or set())
    if not codes_to_check:
        codes_to_check = {"ar", "fa", "ckb", "tr"}

    for code in sorted(codes_to_check):
        if code in contact_forms:
            continue
        if code in row:
            forms = _extract_forms(row.get(code))
            if forms:
                contact_forms[code] = forms

    return ConceptSpec(concept_id=concept_id, label=label, contact_forms=contact_forms)


def _load_concepts_from_csv(path: Path, language_codes: Optional[Set[str]] = None) -> List[ConceptSpec]:
    concepts: List[ConceptSpec] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []

        for row_index, row in enumerate(reader):
            if not isinstance(row, dict):
                continue
            spec = _row_to_concept_spec(row, row_index, language_codes)
            if spec:
                concepts.append(spec)

    return concepts


def load_concepts(path: Path, language_codes: Optional[Set[str]] = None) -> List[ConceptSpec]:
    if not path.exists():
        raise FileNotFoundError(f"Concept list file not found: {path}")

    if path.suffix.lower() == ".csv":
        concepts = _load_concepts_from_csv(path, language_codes)
    else:
        raw = _load_json(path)
        entries: List[Any] = []

        if isinstance(raw, list):
            entries = raw
        elif isinstance(raw, dict):
            if isinstance(raw.get("concepts"), list):
                entries = raw["concepts"]
            elif isinstance(raw.get("concepts"), dict):
                entries = list(raw["concepts"].values())
            elif isinstance(raw.get("list"), list):
                entries = raw["list"]
            elif isinstance(raw.get("items"), list):
                entries = raw["items"]
            else:
                entries = list(raw.values())

        concepts = []
        for row_index, entry in enumerate(entries):
            if isinstance(entry, (str, int, float)):
                concept_id, label = _split_concept_text(entry)
                concept_id = _normalize_concept_key(concept_id)
                if concept_id:
                    concepts.append(ConceptSpec(concept_id=concept_id, label=label))
                continue

            if isinstance(entry, dict):
                spec = _row_to_concept_spec(entry, row_index, language_codes)
                if spec:
                    concepts.append(spec)

    seen_ids: Set[str] = set()
    deduped: List[ConceptSpec] = []
    for concept in concepts:
        concept_id = _normalize_concept_key(concept.concept_id)
        if not concept_id or concept_id in seen_ids:
            continue
        seen_ids.add(concept_id)
        deduped.append(
            ConceptSpec(
                concept_id=concept_id,
                label=concept.label,
                contact_forms={code: _dedupe_non_empty_strings(forms) for code, forms in concept.contact_forms.items()},
            )
        )

    deduped.sort(key=lambda item: _concept_sort_key(item.concept_id))
    return deduped


def _append_contact_ref(
    target: Dict[str, Dict[str, List[str]]],
    concept_key: Any,
    language_code: str,
    raw_forms: Any,
) -> None:
    concept_id = _normalize_concept_key(concept_key)
    if not concept_id:
        return

    forms = _extract_forms(raw_forms)
    if not forms:
        return

    by_lang = target.setdefault(concept_id, {})
    existing = by_lang.setdefault(language_code, [])
    by_lang[language_code] = _dedupe_non_empty_strings(existing + forms)


def load_contact_language_data(path: Path) -> Tuple[List[str], Dict[str, Dict[str, List[str]]]]:
    if not path.exists():
        _warn(f"Contact language config not found: {path}")
        return (list(PREFERRED_CONTACT_LANGUAGES), {})

    raw = _load_json(path)
    if not isinstance(raw, dict):
        _warn(f"Contact language config is not an object: {path}")
        return (list(PREFERRED_CONTACT_LANGUAGES), {})

    language_codes = [code for code, data in raw.items() if isinstance(code, str) and isinstance(data, dict)]
    language_codes = sorted(set(language_codes))

    preferred = [code for code in PREFERRED_CONTACT_LANGUAGES if code in language_codes]
    selected_languages = preferred or language_codes or list(PREFERRED_CONTACT_LANGUAGES)

    refs_by_concept: Dict[str, Dict[str, List[str]]] = {}

    global_concepts = raw.get("concepts")
    if isinstance(global_concepts, dict):
        for concept_key, concept_payload in global_concepts.items():
            if not isinstance(concept_payload, dict):
                continue
            for language_code, raw_forms in concept_payload.items():
                code = _normalize_space(language_code).lower()
                if not code:
                    continue
                _append_contact_ref(refs_by_concept, concept_key, code, raw_forms)

    for language_code, payload in raw.items():
        if not isinstance(language_code, str) or not isinstance(payload, dict):
            continue

        code = language_code.strip().lower()
        for key in ("forms", "concepts", "lexicon"):
            scoped = payload.get(key)
            if not isinstance(scoped, dict):
                continue
            for concept_key, raw_forms in scoped.items():
                _append_contact_ref(refs_by_concept, concept_key, code, raw_forms)

    return (selected_languages, refs_by_concept)


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    if len(left) > len(right):
        left, right = right, left

    prev = list(range(len(right) + 1))
    curr = [0] * (len(right) + 1)

    for i in range(1, len(left) + 1):
        curr[0] = i
        for j in range(1, len(right) + 1):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev

    return prev[len(right)]


def _is_boundary_char(char: str) -> bool:
    return char in FALLBACK_BOUNDARY_CHARS


def _iter_onset_substitution_variants(form: str) -> Iterable[str]:
    for source, target in FALLBACK_ONSET_ALTERNATIONS:
        for left, right in ((source, target), (target, source)):
            if not left or left == right:
                continue

            max_start = len(form) - len(left) + 1
            for start_idx in range(max_start):
                if not form.startswith(left, start_idx):
                    continue
                if start_idx > 0 and not _is_boundary_char(form[start_idx - 1]):
                    continue
                yield form[:start_idx] + right + form[start_idx + len(left) :]


def _iter_coda_deletion_variants(form: str) -> Iterable[str]:
    for idx, char in enumerate(form):
        if char not in FALLBACK_CODA_DELETIONS:
            continue

        if idx == 0 or _is_boundary_char(form[idx - 1]):
            continue
        if idx + 1 < len(form) and not _is_boundary_char(form[idx + 1]):
            continue

        yield form[:idx] + form[idx + 1 :]


def _fallback_variants(form: str) -> List[str]:
    normalized = _normalize_ipa(form)
    if not normalized:
        return [""]

    variants: Set[str] = {normalized}
    queue: List[str] = [normalized]

    while queue and len(variants) < FALLBACK_MAX_VARIANTS:
        current = queue.pop(0)
        candidates = list(_iter_onset_substitution_variants(current))
        candidates.extend(_iter_coda_deletion_variants(current))

        for candidate in candidates:
            candidate_norm = _normalize_ipa(candidate)
            if candidate_norm in variants:
                continue
            variants.add(candidate_norm)
            queue.append(candidate_norm)
            if len(variants) >= FALLBACK_MAX_VARIANTS:
                break

    return sorted(variants, key=lambda value: (len(value), value))


def _normalized_distance_for_forms(left: str, right: str) -> float:
    if not left and not right:
        return 0.0
    if not left or not right:
        return 1.0

    distance = _levenshtein_distance(left, right)
    denominator = max(len(left), len(right), 1)
    return min(1.0, distance / float(denominator))


def _normalized_edit_distance(left: str, right: str) -> float:
    left_variants = _fallback_variants(left)
    right_variants = _fallback_variants(right)

    best_distance = 1.0
    for left_variant in left_variants:
        for right_variant in right_variants:
            candidate_distance = _normalized_distance_for_forms(left_variant, right_variant)
            if candidate_distance < best_distance:
                best_distance = candidate_distance
                if best_distance <= 0.0:
                    return 0.0

    return best_distance


def _resolve_contact_refs(
    concept: ConceptSpec,
    refs_by_concept: Mapping[str, Mapping[str, List[str]]],
) -> Dict[str, List[str]]:
    refs: Dict[str, List[str]] = {}

    by_id = refs_by_concept.get(concept.concept_id)
    if isinstance(by_id, dict):
        for language_code, forms in by_id.items():
            refs[language_code] = _dedupe_non_empty_strings(forms)

    for language_code, forms in concept.contact_forms.items():
        existing = refs.get(language_code, [])
        refs[language_code] = _dedupe_non_empty_strings(existing + forms)

    return refs


def _group_label(index: int) -> str:
    if index < 26:
        return chr(ord("A") + index)
    return f"G{index + 1}"


def _compute_cognate_sets_with_lingpy(
    forms_by_concept: Mapping[str, Sequence[FormRecord]],
    concepts: Sequence[ConceptSpec],
    threshold: float,
) -> Dict[str, Dict[str, List[str]]]:
    try:
        from lingpy import LexStat  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "LingPy is not installed. Install it with: pip install lingpy"
        ) from exc

    rows: List[Tuple[str, str, str, str]] = []
    for concept in concepts:
        concept_id = concept.concept_id
        concept_label = concept.label or f"concept_{concept_id}"
        for record in forms_by_concept.get(concept_id, []):
            rows.append((record.speaker, concept_label, record.ipa, concept_id))

    if not rows:
        return {}

    lex_data: Dict[int, List[str]] = {0: ["doculect", "concept", "ipa"]}
    index_meta: Dict[int, Tuple[str, str]] = {}

    for row_index, (speaker, concept_label, ipa_form, concept_id) in enumerate(rows, start=1):
        lex_data[row_index] = [speaker, concept_label, ipa_form]
        index_meta[row_index] = (concept_id, speaker)

    lexstat = LexStat(lex_data, check=False)
    lexstat.get_scorer()
    lexstat.cluster(method="lexstat", threshold=float(threshold), ref="cogid")

    raw_sets: Dict[str, Dict[str, Set[str]]] = {}
    for row_index, (concept_id, speaker) in index_meta.items():
        cogid_value = str(lexstat[row_index, "cogid"])
        by_cogid = raw_sets.setdefault(concept_id, {})
        by_cogid.setdefault(cogid_value, set()).add(speaker)

    output: Dict[str, Dict[str, List[str]]] = {}
    for concept_id, by_cogid in raw_sets.items():
        cogid_keys = sorted(by_cogid.keys(), key=lambda item: (_concept_sort_key(item), item))
        groups: Dict[str, List[str]] = {}
        for idx, cogid_key in enumerate(cogid_keys):
            label = _group_label(idx)
            groups[label] = sorted(by_cogid[cogid_key])
        output[concept_id] = groups

    return output


def compute_similarity_scores(
    forms_by_concept: Mapping[str, Sequence[FormRecord]],
    concepts: Sequence[ConceptSpec],
    contact_languages: Sequence[str],
    refs_by_concept: Mapping[str, Mapping[str, List[str]]],
) -> Dict[str, Dict[str, Dict[str, SimilarityScore]]]:
    similarity: Dict[str, Dict[str, Dict[str, SimilarityScore]]] = {}

    for concept in concepts:
        concept_id = concept.concept_id
        records = forms_by_concept.get(concept_id, [])
        if not records:
            continue

        refs_for_concept = _resolve_contact_refs(concept, refs_by_concept)
        concept_scores: Dict[str, Dict[str, SimilarityScore]] = {}

        for record in records:
            speaker_scores: Dict[str, SimilarityScore] = {}
            for language_code in contact_languages:
                refs = refs_for_concept.get(language_code, [])
                has_reference_data = bool(refs)
                if has_reference_data:
                    distance = min(_normalized_edit_distance(record.ipa, ref) for ref in refs)
                    score: Optional[float] = round(float(distance), 3)
                else:
                    score = None
                speaker_scores[language_code] = {
                    "score": score,
                    "has_reference_data": has_reference_data,
                }

            concept_scores[record.speaker] = speaker_scores

        similarity[concept_id] = concept_scores

    return similarity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LingPy LexStat and build PARSE enrichments JSON.")
    parser.add_argument("--annotations-dir", required=True, type=Path, help="Directory with *.parse.json files")
    parser.add_argument("--concepts", required=True, type=Path, help="Concept list JSON/CSV")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="LexStat threshold (default: 0.60)")
    parser.add_argument("--output", required=True, type=Path, help="Output enrichments JSON path")
    parser.add_argument(
        "--sil-config",
        type=Path,
        default=DEFAULT_SIL_CONFIG,
        help="Path to sil_contact_languages.json",
    )
    parser.add_argument(
        "--contact-languages",
        default="",
        help="Optional comma-separated language codes override (e.g. ar,fa)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        contact_languages_from_config, refs_by_concept = load_contact_language_data(args.sil_config)

        contact_languages_override = [
            token.strip().lower()
            for token in str(args.contact_languages or "").split(",")
            if token.strip()
        ]
        contact_languages = contact_languages_override or contact_languages_from_config

        concepts = load_concepts(args.concepts, language_codes=set(contact_languages))
        forms_by_concept, speakers = load_annotations(args.annotations_dir)

        if not concepts:
            concept_ids = sorted(forms_by_concept.keys(), key=_concept_sort_key)
            concepts = [ConceptSpec(concept_id=concept_id, label="") for concept_id in concept_ids]

        cognate_sets = _compute_cognate_sets_with_lingpy(forms_by_concept, concepts, args.threshold)
        similarity = compute_similarity_scores(
            forms_by_concept=forms_by_concept,
            concepts=concepts,
            contact_languages=contact_languages,
            refs_by_concept=refs_by_concept,
        )

    except RuntimeError as exc:
        _error(str(exc))
        return 1
    except Exception as exc:
        _error(f"Cognate computation failed: {exc}")
        return 1

    output_payload = {
        "computed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "config": {
            "contact_languages": list(contact_languages),
            "speakers_included": speakers,
            "concepts_included": [_concept_out_value(spec.concept_id) for spec in concepts],
            "lexstat_threshold": round(float(args.threshold), 3),
        },
        "cognate_sets": cognate_sets,
        "similarity": similarity,
        "borrowing_flags": {},
        "manual_overrides": {},
    }

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "[INFO] Wrote enrichments for {0} concepts and {1} speakers to {2}".format(
            len(output_payload["config"]["concepts_included"]),
            len(output_payload["config"]["speakers_included"]),
            output_path,
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
