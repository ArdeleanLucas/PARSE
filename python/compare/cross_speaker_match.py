#!/usr/bin/env python3
"""Cross-speaker concept matching for PARSE Compare mode.

Example:
    python cross_speaker_match.py --stt-output new_stt.json --annotations-dir ./annotations --output matches.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

try:
    from .phonetic_rules import apply_rules, are_phonetically_equivalent, load_rules_from_file
except ImportError:
    from phonetic_rules import apply_rules, are_phonetically_equivalent, load_rules_from_file  # type: ignore

# Tier 3 acoustic-IPA purge: the ai.provider text-to-IPA helper used to
# live here as a transliteration fallback. All text-based IPA generation
# is gone — cross-speaker matching now reads the stored acoustic IPA
# (produced by facebook/wav2vec2-xlsr-53-espeak-cv-ft) from the
# annotation JSON. The small local ``_simple_arabic_to_ipa`` helper is
# kept purely to normalise legacy Arabic-script IPA values that may
# remain in older annotations until a re-transcription pass is run.


DEFAULT_TOP_K = 5
DEFAULT_MIN_CONFIDENCE = 0.35
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "phonetic_rules.json"
REPETITION_WINDOW_SEC = 30.0
REPETITION_MIN = 2
REPETITION_MAX = 4

ARABIC_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u0640\u064B-\u065F\u0670\u06D6-\u06ED]")

SIMPLE_ARABIC_DIGRAPHS: Mapping[str, str] = {
    "\u0648\u0648": "u",
}

SIMPLE_ARABIC_TO_IPA_MAP: Mapping[str, str] = {
    "\u0627": "a",
    "\u0623": "a",
    "\u0625": "a",
    "\u0622": "a",
    "\u0628": "b",
    "\u067e": "p",
    "\u062a": "t",
    "\u062b": "s",
    "\u062c": "d\u0292",
    "\u0686": "t\u0283",
    "\u062d": "h",
    "\u062e": "x",
    "\u062f": "d",
    "\u0630": "z",
    "\u0631": "r",
    "\u0695": "r",
    "\u0632": "z",
    "\u0698": "\u0292",
    "\u0633": "s",
    "\u0634": "\u0283",
    "\u0639": "\u0295",
    "\u063a": "\u0263",
    "\u0641": "f",
    "\u06a4": "v",
    "\u0642": "q",
    "\u06a9": "k",
    "\u0643": "k",
    "\u06af": "g",
    "\u0644": "l",
    "\u06b5": "\u026b",
    "\u0645": "m",
    "\u0646": "n",
    "\u0647": "h",
    "\u06be": "h",
    "\u0629": "e",
    "\u06d5": "e",
    "\u06ce": "e",
    "\u06c6": "o",
    "\u0626": "\u0294",
    "\u0621": "\u0294",
}


@dataclass
class SegmentRecord:
    index: int
    start_sec: float
    end_sec: float
    text: str
    ipa: str
    ortho: str
    tokens: List[str]


@dataclass
class ConceptProfile:
    concept_id: str
    label: str
    ipa_forms: List[str]
    ortho_forms: List[str]
    expected_position: float


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


def _contains_arabic_script(text: str) -> bool:
    return bool(ARABIC_SCRIPT_RE.search(text))


def _strip_arabic_diacritics(text: str) -> str:
    return ARABIC_DIACRITICS_RE.sub("", text)


def _simple_arabic_to_ipa(text: str) -> str:
    normalized = str(text)
    normalized = normalized.replace("\u200c", "")
    normalized = normalized.replace("\u200d", "")

    for source, target in SIMPLE_ARABIC_DIGRAPHS.items():
        normalized = normalized.replace(source, target)

    output: List[str] = []
    for index, char in enumerate(normalized):
        if char in {"\n", "\r", "\t"}:
            output.append(" ")
            continue
        if char.isspace():
            output.append(" ")
            continue

        if char in {"\u06cc", "\u064a", "\u0649"}:
            prev_is_space = index == 0 or normalized[index - 1].isspace()
            output.append("j" if prev_is_space else "i")
            continue

        if char == "\u0648":
            prev_is_space = index == 0 or normalized[index - 1].isspace()
            output.append("w" if prev_is_space else "u")
            continue

        mapped = SIMPLE_ARABIC_TO_IPA_MAP.get(char)
        if mapped is not None:
            output.append(mapped)
            continue

        if char.isascii() and (char.isalnum() or char in "-_'"):
            output.append(char.lower())

    return _normalize_space("".join(output))


def _normalize_for_comparison(text: Any) -> str:
    value = _normalize_ipa(text)
    if not value:
        return ""

    value = _strip_arabic_diacritics(value)
    # Legacy pre-Tier-3 annotations may still hold Arabic-script strings in
    # the IPA tier. Fresh acoustic output is always Latin-script IPA, so
    # this branch is a compat layer until every speaker has been
    # re-transcribed with the wav2vec2 pipeline.
    if _contains_arabic_script(value):
        value = _simple_arabic_to_ipa(value)

    value = _strip_arabic_diacritics(value)
    return _normalize_ipa(value)


def _parse_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_concept_id(value: Any) -> str:
    text = _normalize_space(value)
    if not text:
        return ""

    if text.startswith("#"):
        text = _normalize_space(text[1:])
    if ":" in text:
        text = _normalize_space(text.split(":", 1)[0])
    return text


def _concept_sort_key(concept_id: str) -> Tuple[int, float, str]:
    normalized = _normalize_concept_id(concept_id)
    try:
        return (0, float(normalized), normalized)
    except ValueError:
        return (1, float("inf"), normalized)


def _concept_out_value(concept_id: str) -> Any:
    normalized = _normalize_concept_id(concept_id)
    try:
        number = float(normalized)
    except ValueError:
        return normalized
    if number.is_integer():
        return int(number)
    return normalized


def _split_concept_text(raw_text: Any) -> Tuple[str, str]:
    text = _normalize_space(raw_text)
    if not text:
        return ("", "")

    if ":" in text:
        left, right = text.split(":", 1)
        return (_normalize_concept_id(left), _normalize_space(right))

    return (_normalize_concept_id(text), "")


def _dedupe_strings(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()

    for value in values:
        text = _normalize_space(value)
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)

    return out


TOKEN_RE = re.compile(r"[\w\u0600-\u06FF\u0750-\u077F]+", flags=re.UNICODE)


def _tokenize(text: str) -> List[str]:
    lowered = _normalize_space(text).lower()
    if not lowered:
        return []
    return [token for token in TOKEN_RE.findall(lowered) if token]


def _pick_value(row: Mapping[str, Any], keys: Sequence[str], fallback: Any = "") -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return fallback


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


def _string_similarity(left: str, right: str) -> float:
    a = _normalize_ipa(left)
    b = _normalize_ipa(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    distance = _levenshtein_distance(a, b)
    return max(0.0, 1.0 - (distance / max(len(a), len(b), 1)))


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
        target = tier_name.lower()
        for key, value in tiers.items():
            if isinstance(key, str) and key.lower() == target and isinstance(value, dict):
                tier_data = value
                break

    if not isinstance(tier_data, dict):
        return []

    intervals = tier_data.get("intervals")
    if not isinstance(intervals, list):
        return []

    return [interval for interval in intervals if isinstance(interval, dict)]


def load_stt_segments(stt_output: Path) -> List[SegmentRecord]:
    raw = _load_json(stt_output)
    raw_segments: List[Any]

    if isinstance(raw, list):
        raw_segments = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("segments"), list):
            raw_segments = raw["segments"]
        elif isinstance(raw.get("items"), list):
            raw_segments = raw["items"]
        else:
            raw_segments = []
    else:
        raw_segments = []

    segments: List[SegmentRecord] = []
    for idx, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            continue

        start_sec = _parse_float(
            _pick_value(item, ["start", "startSec", "segment_start_sec", "from", "t0"], 0.0)
        )
        end_sec = _parse_float(
            _pick_value(item, ["end", "endSec", "segment_end_sec", "to", "t1"], start_sec)
        )
        if end_sec < start_sec:
            end_sec = start_sec

        text = _normalize_space(_pick_value(item, ["text", "transcript", "orth", "ortho"], ""))
        ipa = _normalize_ipa(_pick_value(item, ["ipa", "phonetic", "phonemic"], ""))
        ortho = _normalize_space(_pick_value(item, ["ortho", "orth", "text", "transcript"], ""))

        tokens = _tokenize(ipa) + _tokenize(text)
        tokens = _dedupe_strings(tokens)

        segments.append(
            SegmentRecord(
                index=idx,
                start_sec=start_sec,
                end_sec=end_sec,
                text=text,
                ipa=ipa,
                ortho=ortho,
                tokens=tokens,
            )
        )

    segments.sort(key=lambda item: (item.start_sec, item.end_sec, item.index))
    for new_index, segment in enumerate(segments):
        segment.index = new_index
    return segments


def infer_speaker_id(stt_output: Path) -> str:
    raw = _load_json(stt_output)

    if isinstance(raw, dict):
        candidates: List[Any] = [
            raw.get("speaker"),
            raw.get("speaker_id"),
            raw.get("speakerId"),
        ]

        metadata = raw.get("metadata")
        if isinstance(metadata, dict):
            candidates.extend(
                [
                    metadata.get("speaker"),
                    metadata.get("speaker_id"),
                    metadata.get("speakerId"),
                ]
            )

        for candidate in candidates:
            speaker_id = _normalize_space(candidate)
            if speaker_id:
                return speaker_id

    fallback = _normalize_space(stt_output.stem)
    return fallback or "unknown"


def load_concept_profiles(annotations_dir: Path) -> List[ConceptProfile]:
    if not annotations_dir.exists():
        raise FileNotFoundError(f"Annotations directory not found: {annotations_dir}")
    if not annotations_dir.is_dir():
        raise ValueError(f"Annotations path is not a directory: {annotations_dir}")

    raw_map: Dict[str, Dict[str, Any]] = {}

    files = sorted(annotations_dir.glob("*.parse.json"))
    if not files:
        _warn(f"No annotation files (*.parse.json) found in {annotations_dir}")

    for path in files:
        data = _load_json(path)
        if not isinstance(data, dict):
            continue

        concept_intervals = _intervals_for_tier(data, "concept")
        ipa_intervals = _intervals_for_tier(data, "ipa")
        ortho_intervals = _intervals_for_tier(data, "ortho")

        for concept_interval in concept_intervals:
            start_sec = _parse_float(concept_interval.get("start"))
            end_sec = _parse_float(concept_interval.get("end"))
            if end_sec < start_sec:
                continue

            concept_id, label = _split_concept_text(concept_interval.get("text"))
            concept_id = _normalize_concept_id(concept_id)
            if not concept_id:
                continue

            ipa_text = _normalize_for_comparison(_best_overlap_text(start_sec, end_sec, ipa_intervals))
            ortho_text = _normalize_space(_best_overlap_text(start_sec, end_sec, ortho_intervals))

            bucket = raw_map.setdefault(
                concept_id,
                {
                    "label": "",
                    "ipa_forms": set(),
                    "ortho_forms": set(),
                    "starts": [],
                },
            )
            if label and not bucket["label"]:
                bucket["label"] = label
            if ipa_text:
                bucket["ipa_forms"].add(ipa_text)
            if ortho_text:
                bucket["ortho_forms"].add(ortho_text)
            bucket["starts"].append(start_sec)

    if not raw_map:
        return []

    expected_order = sorted(
        raw_map.keys(),
        key=lambda cid: (
            statistics.median(raw_map[cid]["starts"]) if raw_map[cid]["starts"] else float("inf"),
            _concept_sort_key(cid),
        ),
    )
    denom = max(len(expected_order) - 1, 1)
    position_lookup = {concept_id: (idx / denom if len(expected_order) > 1 else 0.5) for idx, concept_id in enumerate(expected_order)}

    profiles: List[ConceptProfile] = []
    for concept_id in sorted(raw_map.keys(), key=_concept_sort_key):
        bucket = raw_map[concept_id]
        ipa_forms = _dedupe_strings(sorted(bucket["ipa_forms"]))
        ortho_forms = _dedupe_strings(sorted(bucket["ortho_forms"]))
        if not ipa_forms and not ortho_forms:
            continue

        profiles.append(
            ConceptProfile(
                concept_id=concept_id,
                label=_normalize_space(bucket["label"]),
                ipa_forms=ipa_forms,
                ortho_forms=ortho_forms,
                expected_position=position_lookup.get(concept_id, 0.5),
            )
        )

    return profiles


def _merge_equivalent_occurrence_groups(
    grouped_occurrences: Mapping[str, List[Tuple[int, float]]],
    rules: Sequence[Any],
) -> List[List[Tuple[int, float]]]:
    forms = [form for form in grouped_occurrences.keys() if form]
    if not forms:
        return []

    parent = list(range(len(forms)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_idx, left_form in enumerate(forms):
        for right_idx in range(left_idx + 1, len(forms)):
            right_form = forms[right_idx]
            equivalent, _ = are_phonetically_equivalent(left_form, right_form, list(rules))
            if equivalent:
                union(left_idx, right_idx)

    merged: Dict[int, List[Tuple[int, float]]] = {}
    for idx, form in enumerate(forms):
        root = find(idx)
        merged.setdefault(root, []).extend(grouped_occurrences.get(form, []))

    return list(merged.values())


def detect_repetition_boosts(segments: Sequence[SegmentRecord], rules: Sequence[Any]) -> Dict[int, float]:
    occurrences: Dict[str, List[Tuple[int, float]]] = {}

    for segment in segments:
        source_form = segment.ipa or segment.text or (segment.tokens[0] if segment.tokens else "")
        normalized_source = _normalize_for_comparison(source_form)
        canonical = apply_rules(normalized_source, list(rules)) if normalized_source else ""
        canonical = _normalize_for_comparison(canonical)
        if not canonical:
            continue
        occurrences.setdefault(canonical, []).append((segment.index, segment.start_sec))

    boosts: Dict[int, float] = {}

    for occ in _merge_equivalent_occurrence_groups(occurrences, rules):
        occ.sort(key=lambda item: item[1])
        for i in range(len(occ)):
            j = i
            while j + 1 < len(occ) and (occ[j + 1][1] - occ[i][1]) <= REPETITION_WINDOW_SEC:
                j += 1

            count = j - i + 1
            if REPETITION_MIN <= count <= REPETITION_MAX:
                boost_value = min(0.20, 0.05 * count)
                for k in range(i, j + 1):
                    segment_index = occ[k][0]
                    boosts[segment_index] = max(boosts.get(segment_index, 0.0), boost_value)

    return boosts


def _best_phonetic_score(segment: SegmentRecord, ipa_forms: Sequence[str], rules: Sequence[Any]) -> Tuple[float, str]:
    fallback_form = _normalize_for_comparison(segment.ipa or segment.text or (segment.tokens[0] if segment.tokens else ""))

    normalized_refs = _dedupe_strings(_normalize_for_comparison(ref) for ref in ipa_forms)
    if not normalized_refs:
        return (0.0, fallback_form)

    candidates_raw = [segment.ipa, segment.text, segment.ortho]
    candidates_raw.extend(segment.tokens)
    candidates = _dedupe_strings(_normalize_for_comparison(candidate) for candidate in candidates_raw)

    if not candidates:
        return (0.0, "")

    best_score = 0.0
    best_form = candidates[0]

    for candidate in candidates:
        for ref in normalized_refs:
            _, score = are_phonetically_equivalent(candidate, ref, list(rules))
            if score > best_score:
                best_score = score
                best_form = candidate

    return (best_score, best_form)


def _best_ortho_score(segment: SegmentRecord, ortho_forms: Sequence[str]) -> float:
    if not ortho_forms:
        return 0.0

    segment_values = [segment.ortho, segment.text]
    segment_values.extend(segment.tokens)
    segment_values = [value for value in (_normalize_space(v) for v in segment_values) if value]

    if not segment_values:
        return 0.0

    best = 0.0
    for value in segment_values:
        for ref in ortho_forms:
            best = max(best, _string_similarity(value, ref))
            if value == _normalize_space(ref):
                best = max(best, 1.0)
    return best


def _positional_boost(segment_index: int, total_segments: int, expected_position: float) -> float:
    if total_segments <= 1:
        return 0.08

    observed_position = segment_index / float(total_segments - 1)
    distance = abs(observed_position - expected_position)
    return max(0.0, 0.18 * (1.0 - (distance / 0.35)))


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_matches(
    segments: Sequence[SegmentRecord],
    profiles: Sequence[ConceptProfile],
    rules: Sequence[Any],
    *,
    top_k: int,
    min_confidence: float,
) -> List[Dict[str, Any]]:
    repetition_boosts = detect_repetition_boosts(segments, rules)

    output: List[Dict[str, Any]] = []
    for profile in profiles:
        candidates: List[Dict[str, Any]] = []

        for segment in segments:
            phonetic_score, best_form = _best_phonetic_score(segment, profile.ipa_forms, rules)
            ortho_score = _best_ortho_score(segment, profile.ortho_forms)

            if phonetic_score < 0.18 and ortho_score < 0.45:
                continue

            repetition_boost = repetition_boosts.get(segment.index, 0.0)
            position_boost = _positional_boost(segment.index, len(segments), profile.expected_position)

            confidence = _clamp_score((0.62 * phonetic_score) + (0.20 * ortho_score) + repetition_boost + position_boost)
            if confidence < min_confidence:
                continue

            candidate = {
                "startSec": round(segment.start_sec, 3),
                "endSec": round(segment.end_sec, 3),
                "ipa": best_form or _normalize_ipa(segment.ipa or segment.text),
                "ortho": segment.ortho or segment.text,
                "confidence": round(confidence, 3),
            }
            candidates.append(candidate)

        if not candidates:
            continue

        candidates.sort(key=lambda item: (-float(item["confidence"]), float(item["startSec"]), float(item["endSec"])))

        deduped: List[Dict[str, Any]] = []
        seen_bounds: Set[Tuple[float, float]] = set()
        for candidate in candidates:
            bounds = (float(candidate["startSec"]), float(candidate["endSec"]))
            if bounds in seen_bounds:
                continue
            seen_bounds.add(bounds)
            deduped.append(candidate)
            if len(deduped) >= top_k:
                break

        if deduped:
            output.append(
                {
                    "conceptId": _concept_out_value(profile.concept_id),
                    "candidates": deduped,
                }
            )

    output.sort(key=lambda item: _concept_sort_key(str(item.get("conceptId", ""))))
    return output


def match_cross_speaker(
    speaker_id: str,
    segments: Sequence[SegmentRecord],
    profiles: Sequence[ConceptProfile],
    rules: Sequence[Any],
    *,
    top_k: int,
    min_confidence: float,
) -> Dict[str, Any]:
    resolved_speaker = _normalize_space(speaker_id) or "unknown"
    matches_list = compute_matches(
        segments=segments,
        profiles=profiles,
        rules=rules,
        top_k=top_k,
        min_confidence=min_confidence,
    )
    return {
        "speaker": resolved_speaker,
        "matches": matches_list,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Match annotated concepts to a new speaker's STT output.")
    parser.add_argument("--stt-output", required=True, type=Path, help="STT JSON for the new speaker")
    parser.add_argument("--annotations-dir", required=True, type=Path, help="Directory with baseline *.parse.json files")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path for ranked matches")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH, help="Path to phonetic_rules.json")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Max candidates per concept (default: 5)")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE,
        help="Minimum confidence required for output candidates",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        rules = load_rules_from_file(args.rules)
        segments = load_stt_segments(args.stt_output)
        speaker_id = infer_speaker_id(args.stt_output)
        profiles = load_concept_profiles(args.annotations_dir)

        if not segments:
            _warn("No STT segments found. Writing empty match list.")
        if not profiles:
            _warn("No concept profiles found from annotations. Writing empty match list.")

        result = match_cross_speaker(
            speaker_id=speaker_id,
            segments=segments,
            profiles=profiles,
            rules=rules,
            top_k=max(1, int(args.top_k)),
            min_confidence=max(0.0, min(1.0, float(args.min_confidence))),
        )
        matches = result["matches"]

    except Exception as exc:
        _error(f"Cross-speaker matching failed: {exc}")
        return 1

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "[INFO] Wrote {0} concept match groups to {1}".format(len(matches), output_path),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
