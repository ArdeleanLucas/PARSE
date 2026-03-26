#!/usr/bin/env python3
"""Auto-detect constant timestamp offset between CSV timestamps and STT audio time.

Example:
    python offset_detect.py --csv speaker_concepts.csv --stt-output speaker_stt.json --output offset.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from .phonetic_rules import are_phonetically_equivalent, load_rules_from_file
except ImportError:
    from phonetic_rules import are_phonetically_equivalent, load_rules_from_file  # type: ignore


DEFAULT_N_ANCHORS = 10
DEFAULT_BUCKET_SEC = 1.0
DEFAULT_MIN_MATCH_SCORE = 0.56
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "phonetic_rules.json"

TOKEN_RE = re.compile(r"[\w\u0600-\u06FF\u0750-\u077F]+", flags=re.UNICODE)
ARABIC_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
ARABIC_DIACRITIC_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")

ARABIC_SCRIPT_DIGRAPHS: Dict[str, str] = {
    "وو": "u",
}

ARABIC_SCRIPT_CHAR_MAP: Dict[str, str] = {
    "ا": "a",
    "أ": "a",
    "إ": "a",
    "آ": "a",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ث": "s",
    "ج": "dʒ",
    "چ": "tʃ",
    "ح": "h",
    "خ": "x",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ڕ": "r",
    "ز": "z",
    "ژ": "ʒ",
    "س": "s",
    "ش": "ʃ",
    "ع": "ʕ",
    "غ": "ɣ",
    "ف": "f",
    "ڤ": "v",
    "ق": "q",
    "ک": "k",
    "ك": "k",
    "گ": "g",
    "ل": "l",
    "ڵ": "ɫ",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "ھ": "h",
    "ة": "e",
    "ە": "e",
    "ێ": "e",
    "ۆ": "o",
    "ؤ": "u",
    "ئ": "ʔ",
    "ء": "ʔ",
}


@dataclass
class Anchor:
    index: int
    start_sec: float
    text: str
    tokens: List[str]


@dataclass
class Segment:
    index: int
    start_sec: float
    end_sec: float
    text: str
    tokens: List[str]


@dataclass
class MatchHypothesis:
    anchor_index: int
    segment_index: int
    offset_sec: float
    score: float


def _warn(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


def _error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_text(value: Any) -> str:
    text = _normalize_space(value).lower()
    if text.startswith("/") and text.endswith("/") and len(text) >= 2:
        text = text[1:-1].strip()
    if text.startswith("[") and text.endswith("]") and len(text) >= 2:
        text = text[1:-1].strip()
    return text


def _contains_arabic_kurdish_script(text: str) -> bool:
    return bool(ARABIC_SCRIPT_RE.search(text))


def _strip_diacritics(text: str) -> str:
    without_arabic_marks = ARABIC_DIACRITIC_RE.sub("", text)
    decomposed = unicodedata.normalize("NFD", without_arabic_marks)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return unicodedata.normalize("NFC", stripped)


def _arabic_script_to_latin_ipa(text: str) -> str:
    normalized = text.replace("\u200c", "").replace("\u200d", "").replace("ـ", "")

    for source, target in ARABIC_SCRIPT_DIGRAPHS.items():
        normalized = normalized.replace(source, target)

    output: List[str] = []
    for index, char in enumerate(normalized):
        if ARABIC_DIACRITIC_RE.fullmatch(char):
            continue

        if char.isspace():
            output.append(" ")
            continue

        if char in {"ی", "ي", "ى", "ۍ"}:
            prev_is_space = index == 0 or normalized[index - 1].isspace()
            output.append("j" if prev_is_space else "i")
            continue

        if char == "و":
            prev_is_space = index == 0 or normalized[index - 1].isspace()
            output.append("w" if prev_is_space else "u")
            continue

        mapped = ARABIC_SCRIPT_CHAR_MAP.get(char)
        if mapped is not None:
            output.append(mapped)
            continue

        if char.isascii() and (char.isalnum() or char in "-_'"):
            output.append(char.lower())

    return _normalize_space("".join(output))


def _normalize_for_comparison(text: Any) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""

    if _contains_arabic_kurdish_script(normalized):
        normalized = _arabic_script_to_latin_ipa(normalized)

    normalized = _strip_diacritics(normalized)
    return _normalize_space(normalized).lower()


def _parse_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tokenize(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    return [token for token in TOKEN_RE.findall(normalized) if token]


def _dedupe_tokens(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        token = _normalize_text(value)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _pick_value(row: Mapping[str, Any], keys: Sequence[str], fallback: Any = "") -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
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
    a = _normalize_text(left)
    b = _normalize_text(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    distance = _levenshtein_distance(a, b)
    return max(0.0, 1.0 - (distance / max(len(a), len(b), 1)))


def _infer_speaker_from_csv(csv_path: Path) -> str:
    stem = csv_path.stem
    for suffix in ("_concepts", "-concepts", "_timestamps", "-timestamps", "_csv", "-csv"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem or "unknown"


def load_anchors_from_csv(csv_path: Path, n_anchors: int) -> Tuple[str, List[Anchor]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    anchors: List[Anchor] = []
    speaker_hint = ""

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header columns: {csv_path}")

        for row_index, row in enumerate(reader):
            if not isinstance(row, dict):
                continue

            if not speaker_hint:
                speaker_hint = _normalize_space(_pick_value(row, ["speaker", "speaker_id", "Speaker"], ""))

            start_value = _pick_value(
                row,
                ["start_sec", "start", "time_sec", "timestamp", "segment_start_sec", "wav_start_sec", "t0"],
                None,
            )
            if start_value is None:
                continue

            start_sec = _parse_float(start_value)
            if start_sec < 0:
                continue

            row_text = _normalize_space(
                _pick_value(
                    row,
                    [
                        "ortho",
                        "orth",
                        "ipa",
                        "concept",
                        "concept_en",
                        "english",
                        "gloss",
                        "label",
                        "text",
                    ],
                    "",
                )
            )
            if not row_text:
                continue

            tokens = _dedupe_tokens(_tokenize(row_text))
            if not tokens:
                continue

            anchors.append(Anchor(index=row_index, start_sec=start_sec, text=row_text, tokens=tokens))

    if not anchors:
        raise ValueError("No usable anchor rows found in CSV")

    anchors.sort(key=lambda item: item.start_sec)
    anchors = anchors[: max(1, int(n_anchors))]

    speaker = speaker_hint or _infer_speaker_from_csv(csv_path)
    return (speaker, anchors)


def load_stt_segments(stt_path: Path) -> List[Segment]:
    raw = _load_json(stt_path)
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

    segments: List[Segment] = []
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

        text = _normalize_space(
            _pick_value(item, ["text", "transcript", "ortho", "orth", "ipa", "phonetic"], "")
        )
        tokens = _dedupe_tokens(_tokenize(text))
        if not text and not tokens:
            continue

        segments.append(Segment(index=idx, start_sec=start_sec, end_sec=end_sec, text=text, tokens=tokens))

    segments.sort(key=lambda item: (item.start_sec, item.end_sec, item.index))
    for new_index, segment in enumerate(segments):
        segment.index = new_index
    return segments


def _anchor_to_segment_similarity(anchor_token: str, segment_token: str, rules: Sequence[Any]) -> float:
    normalized_anchor = _normalize_for_comparison(anchor_token)
    normalized_segment = _normalize_for_comparison(segment_token)
    if not normalized_anchor or not normalized_segment:
        return 0.0

    lexical = _string_similarity(normalized_anchor, normalized_segment)
    _, phonetic = are_phonetically_equivalent(normalized_anchor, normalized_segment, list(rules))
    return max(lexical, phonetic)


def _anchor_segment_score(anchor: Anchor, segment: Segment, rules: Sequence[Any]) -> float:
    if not anchor.tokens or not segment.tokens:
        return 0.0

    best = 0.0
    for anchor_token in anchor.tokens:
        for segment_token in segment.tokens:
            best = max(best, _anchor_to_segment_similarity(anchor_token, segment_token, rules))
            if best >= 1.0:
                return 1.0
    return best


def build_offset_hypotheses(
    anchors: Sequence[Anchor],
    segments: Sequence[Segment],
    rules: Sequence[Any],
    *,
    min_match_score: float,
) -> List[MatchHypothesis]:
    hypotheses: List[MatchHypothesis] = []

    for anchor in anchors:
        local: List[MatchHypothesis] = []
        for segment in segments:
            score = _anchor_segment_score(anchor, segment, rules)
            if score < min_match_score:
                continue

            local.append(
                MatchHypothesis(
                    anchor_index=anchor.index,
                    segment_index=segment.index,
                    offset_sec=segment.start_sec - anchor.start_sec,
                    score=score,
                )
            )

        if not local:
            continue

        local.sort(key=lambda item: (-item.score, abs(item.offset_sec)))
        hypotheses.extend(local[:20])

    return hypotheses


def _bucketize_offset(offset_sec: float, bucket_sec: float) -> float:
    return round(offset_sec / bucket_sec) * bucket_sec


def select_consistent_matches(
    anchors: Sequence[Anchor],
    hypotheses: Sequence[MatchHypothesis],
    *,
    bucket_sec: float,
) -> List[MatchHypothesis]:
    if not hypotheses:
        return []

    buckets: Dict[float, List[MatchHypothesis]] = {}
    for hypothesis in hypotheses:
        key = _bucketize_offset(hypothesis.offset_sec, bucket_sec)
        buckets.setdefault(key, []).append(hypothesis)

    def bucket_rank(items: List[MatchHypothesis]) -> Tuple[int, float, int]:
        anchors_covered = len({item.anchor_index for item in items})
        score_sum = sum(item.score for item in items)
        return (anchors_covered, score_sum, len(items))

    selected_bucket_key = max(buckets.keys(), key=lambda key: bucket_rank(buckets[key]))
    selected_bucket = buckets[selected_bucket_key]

    best_per_anchor: Dict[int, MatchHypothesis] = {}
    for hypothesis in selected_bucket:
        previous = best_per_anchor.get(hypothesis.anchor_index)
        if previous is None or hypothesis.score > previous.score:
            best_per_anchor[hypothesis.anchor_index] = hypothesis

    selected = [best_per_anchor[key] for key in sorted(best_per_anchor.keys())]
    if len(selected) >= 2:
        return selected

    fallback_per_anchor: Dict[int, MatchHypothesis] = {}
    for hypothesis in hypotheses:
        previous = fallback_per_anchor.get(hypothesis.anchor_index)
        if previous is None or hypothesis.score > previous.score:
            fallback_per_anchor[hypothesis.anchor_index] = hypothesis
    return [fallback_per_anchor[key] for key in sorted(fallback_per_anchor.keys())]


def _robust_spread(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return 0.0

    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    return statistics.median(deviations)


def compute_confidence(selected: Sequence[MatchHypothesis], total_anchors: int) -> float:
    if not selected or total_anchors <= 0:
        return 0.0

    offsets = [item.offset_sec for item in selected]
    spread = _robust_spread(offsets)
    anchor_ratio = len(selected) / float(total_anchors)
    score_quality = sum(item.score for item in selected) / float(len(selected))

    spread_component = max(0.0, 1.0 - (spread / 6.0))
    confidence = (0.45 * anchor_ratio) + (0.30 * spread_component) + (0.25 * score_quality)
    return max(0.0, min(0.99, round(confidence, 3)))


def detect_offset(
    anchors: Sequence[Anchor],
    segments: Sequence[Segment],
    rules: Sequence[Any],
    *,
    bucket_sec: float,
    min_match_score: float,
) -> Tuple[float, float, int]:
    hypotheses = build_offset_hypotheses(
        anchors=anchors,
        segments=segments,
        rules=rules,
        min_match_score=min_match_score,
    )
    if not hypotheses:
        raise ValueError("Unable to find keyword matches between CSV anchors and STT segments")

    selected = select_consistent_matches(anchors, hypotheses, bucket_sec=bucket_sec)
    if not selected:
        raise ValueError("Unable to select a consistent offset cluster")

    offsets = [item.offset_sec for item in selected]
    offset_sec = round(statistics.median(offsets), 3)
    confidence = compute_confidence(selected, len(anchors))
    return (offset_sec, confidence, len(selected))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect constant timestamp offset via keyword alignment.")
    parser.add_argument("--csv", required=True, type=Path, help="CSV with known concept timestamps")
    parser.add_argument("--stt-output", required=True, type=Path, help="STT JSON output for the same speaker audio")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    parser.add_argument("--n-anchors", type=int, default=DEFAULT_N_ANCHORS, help="Number of earliest CSV anchors to use")
    parser.add_argument("--bucket-sec", type=float, default=DEFAULT_BUCKET_SEC, help="Offset clustering bucket size")
    parser.add_argument(
        "--min-match-score",
        type=float,
        default=DEFAULT_MIN_MATCH_SCORE,
        help="Minimum token match score to consider a hypothesis",
    )
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH, help="Path to phonetic_rules.json")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        rules = load_rules_from_file(args.rules)
        speaker, anchors = load_anchors_from_csv(args.csv, max(1, int(args.n_anchors)))
        segments = load_stt_segments(args.stt_output)
        if not segments:
            raise ValueError("No STT segments found")

        offset_sec, confidence, n_anchors = detect_offset(
            anchors=anchors,
            segments=segments,
            rules=rules,
            bucket_sec=max(0.1, float(args.bucket_sec)),
            min_match_score=max(0.0, min(1.0, float(args.min_match_score))),
        )

    except Exception as exc:
        _error(f"Offset detection failed: {exc}")
        return 1

    payload = {
        "speaker": speaker,
        "offset_sec": offset_sec,
        "confidence": confidence,
        "method": "keyword_alignment",
        "n_anchors": n_anchors,
    }

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "[INFO] Wrote detected offset ({0:+.3f}s, confidence {1:.3f}) to {2}".format(
            payload["offset_sec"], payload["confidence"], output_path
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
