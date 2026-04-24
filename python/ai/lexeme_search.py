"""
Two-signal lexeme candidate ranking for the Lexical Anchor Alignment System.

Signal A (within-speaker phonetic similarity):
  - Normalised Levenshtein on orthographic form (whole string + per-token)
  - Normalised Levenshtein on IPA phoneme sequence (via phonemizer/espeak)
  - Whichever scores higher wins for the candidate

Signal B (cross-speaker concept matching):
  - For the target concept, read confirmed_anchors on every other speaker's
    annotation record
  - Small additive bonus when the candidate's text is phonetically close to
    at least one already-confirmed variant

Tier-priority weighting preserves PR #178's `ortho_words` confidence:
  ortho_words (1.00) > ortho (0.85) > stt (0.70) > ipa (0.55)

The PR A client-side matcher still lives as documentation in the README
scoring formula. This module is the canonical scorer — the HTTP endpoint
in server.py and any future CLI caller should funnel through `search()`.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, Optional
import re
import unicodedata

TIER_PRIORITY = ("ortho_words", "ortho", "stt", "ipa")
TIER_WEIGHT = {
    "ortho_words": 1.0,
    "ortho": 0.85,
    "stt": 0.7,
    "ipa": 0.55,
}

DEFAULT_MAX_DISTANCE = 0.55
DEFAULT_LIMIT = 10
ADJACENCY_GAP_SEC = 0.3
MAX_ADJACENT_DURATION_SEC = 1.2
CROSS_SPEAKER_BONUS = 0.15
DEFAULT_LANGUAGE = "ku"


@dataclass
class Candidate:
    start: float
    end: float
    tier: str
    matched_text: str
    matched_variant: str
    score: float
    phonetic_score: float
    cross_speaker_score: float
    confidence_weight: float
    source_label: str

    def to_dict(self) -> dict:
        return asdict(self)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    curr = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        curr[0] = i
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    return prev[len(b)]


def normalized_levenshtein(a: str, b: str) -> float:
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0
    return levenshtein(a, b) / max_len


_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)


def normalize_for_match(text: str) -> str:
    """Lowercase, NFKD, strip punctuation, collapse whitespace."""
    folded = unicodedata.normalize("NFKD", text).lower()
    stripped = _PUNCT_RE.sub("", folded)
    return re.sub(r"\s+", " ", stripped).strip()


def phonemize_variant(variant: str, language: str = DEFAULT_LANGUAGE) -> list[str]:
    """Convert an orthographic variant to an IPA token list via phonemizer.

    Returns an empty list when the backend is unavailable (no espeak, no
    language model, etc.) — callers fall back to the orthographic signal.
    Import is lazy so the server doesn't pay phonemizer startup cost on
    requests that never need it.
    """
    try:
        from ai.forced_align import _g2p_word  # type: ignore[import-not-found]
    except Exception:
        try:
            from python.ai.forced_align import _g2p_word  # type: ignore[import-not-found]
        except Exception:
            return []
    clean = normalize_for_match(variant).replace(" ", "")
    if not clean:
        return []
    try:
        return _g2p_word(clean, language=language) or []
    except Exception:
        return []


def _best_orth_distance(text: str, variants_orth: list[str]) -> tuple[float, str]:
    norm_text = normalize_for_match(text)
    tokens = [t for t in norm_text.split(" ") if t]
    best_dist = 1.0
    best_variant = variants_orth[0] if variants_orth else ""
    for variant in variants_orth:
        norm_variant = normalize_for_match(variant)
        if not norm_variant:
            continue
        whole = normalized_levenshtein(norm_text, norm_variant)
        if whole < best_dist:
            best_dist = whole
            best_variant = variant
        for tok in tokens:
            d = normalized_levenshtein(tok, norm_variant)
            if d < best_dist:
                best_dist = d
                best_variant = variant
    return best_dist, best_variant


def _best_ipa_distance(text_ipa: list[str], variant_ipa_list: list[list[str]]) -> float:
    if not text_ipa or not variant_ipa_list:
        return 1.0
    text_str = "".join(text_ipa)
    best = 1.0
    for v_tokens in variant_ipa_list:
        if not v_tokens:
            continue
        v_str = "".join(v_tokens)
        d = normalized_levenshtein(text_str, v_str)
        if d < best:
            best = d
    return best


def _adjacency_merges(
    intervals: list[dict],
) -> list[dict]:
    """Original intervals plus merged pairs of adjacent short intervals.

    Mirrors the TS PR A matcher's merge — catches split words like
    "ye" + "k" → "yek" without losing the underlying split forms.
    """
    out: list[dict] = []
    for iv in intervals:
        text = (iv.get("text") or "").strip()
        if not text:
            continue
        entry = {"start": iv["start"], "end": iv["end"], "text": text}
        # Preserve per-interval metadata that downstream scoring uses
        # (ortho_words confidence weighting). Merged pairs intentionally
        # don't carry this across — they're lower-confidence by construction.
        if "confidence" in iv:
            entry["confidence"] = iv["confidence"]
        if "source" in iv:
            entry["source"] = iv["source"]
        out.append(entry)
    for i in range(len(intervals) - 1):
        a, b = intervals[i], intervals[i + 1]
        a_text = (a.get("text") or "").strip()
        b_text = (b.get("text") or "").strip()
        if not a_text or not b_text:
            continue
        if b["start"] - a["end"] > ADJACENCY_GAP_SEC:
            continue
        if (a["end"] - a["start"]) > MAX_ADJACENT_DURATION_SEC:
            continue
        if (b["end"] - b["start"]) > MAX_ADJACENT_DURATION_SEC:
            continue
        out.append({
            "start": a["start"],
            "end": b["end"],
            "text": f"{a_text} {b_text}".strip(),
            "_merged": True,
        })
    return out


def _cross_speaker_anchor_texts(
    concept_id: Optional[str],
    cross_speaker_records: Optional[Iterable[dict]],
) -> list[str]:
    """Collect matched_text from confirmed_anchors for this concept_id
    across every other speaker. Falls back to the lemma at each anchor's
    time range on the owner's ortho_words tier if matched_text is missing.
    """
    if not concept_id or not cross_speaker_records:
        return []
    out: list[str] = []
    cid = str(concept_id)
    for rec in cross_speaker_records:
        anchors = (rec or {}).get("confirmed_anchors") or {}
        anchor = anchors.get(cid)
        if not isinstance(anchor, dict):
            continue
        text = (anchor.get("matched_text") or anchor.get("text") or "").strip()
        if not text:
            # Try to pull from ortho_words at the anchor's time range.
            start = anchor.get("start")
            end = anchor.get("end")
            if start is None or end is None:
                continue
            ow = (rec.get("tiers") or {}).get("ortho_words") or {}
            for iv in ow.get("intervals") or []:
                if iv.get("start", 0) <= start + 0.05 and iv.get("end", 0) >= end - 0.05:
                    text = (iv.get("text") or "").strip()
                    if text:
                        break
        if text:
            out.append(text)
    return out


def _cross_speaker_bonus(text: str, anchor_texts: list[str]) -> float:
    if not anchor_texts:
        return 0.0
    norm_text = normalize_for_match(text)
    best = 1.0
    for a in anchor_texts:
        d = normalized_levenshtein(norm_text, normalize_for_match(a))
        if d < best:
            best = d
    return max(0.0, 1.0 - best) * CROSS_SPEAKER_BONUS


def search(
    record: Optional[dict],
    variants: list[str],
    *,
    concept_id: Optional[str] = None,
    cross_speaker_records: Optional[Iterable[dict]] = None,
    language: str = DEFAULT_LANGUAGE,
    limit: int = DEFAULT_LIMIT,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    tiers: Optional[Iterable[str]] = None,
) -> list[dict]:
    """Rank candidate time ranges matching the given variants.

    Returns a list of plain dicts (ready to JSON-serialize) ordered by
    descending combined score. Each candidate dict has the shape of
    Candidate.to_dict().
    """
    cleaned = [v.strip() for v in variants if v and v.strip()]
    if not record or not cleaned:
        return []

    tier_set = tuple(tiers) if tiers else TIER_PRIORITY
    record_tiers = record.get("tiers") or {}

    # Phonemize each variant once; an empty list means phonemizer is not
    # available for this language — we silently degrade to orthographic-only.
    variant_ipa = [phonemize_variant(v, language=language) for v in cleaned]

    anchor_texts = _cross_speaker_anchor_texts(concept_id, cross_speaker_records)

    raw: list[Candidate] = []
    for tier_name in tier_set:
        if tier_name not in TIER_WEIGHT:
            continue
        tier = record_tiers.get(tier_name)
        if not isinstance(tier, dict):
            continue
        intervals = tier.get("intervals") or []
        if not intervals:
            continue

        for iv in _adjacency_merges(intervals):
            text = iv["text"]
            orth_dist, best_variant = _best_orth_distance(text, cleaned)

            # Compare the interval's text in IPA space too (phonemized on
            # the fly). If the tier itself is already IPA we skip that
            # re-phonemization and use the text directly.
            if tier_name == "ipa":
                text_ipa = list(text.replace(" ", ""))
            else:
                text_ipa = phonemize_variant(text, language=language)
            ipa_dist = _best_ipa_distance(text_ipa, variant_ipa)

            combined_dist = min(orth_dist, ipa_dist)
            if combined_dist > max_distance:
                continue

            phonetic_score = 1.0 - combined_dist
            confidence_weight = 1.0
            if tier_name == "ortho_words":
                # Prefer the merged-pair's originating confidence when
                # present; fall back to 1.0 for merges that span two
                # intervals of different confidences.
                conf = iv.get("confidence")
                if isinstance(conf, (int, float)):
                    confidence_weight = max(0.5, min(1.0, float(conf)))

            cs_bonus = _cross_speaker_bonus(text, anchor_texts)

            base_score = phonetic_score * TIER_WEIGHT[tier_name] * confidence_weight
            total_score = min(1.0, base_score + cs_bonus)

            raw.append(Candidate(
                start=float(iv["start"]),
                end=float(iv["end"]),
                tier=tier_name,
                matched_text=text,
                matched_variant=best_variant,
                score=round(total_score, 4),
                phonetic_score=round(phonetic_score, 4),
                cross_speaker_score=round(cs_bonus, 4),
                confidence_weight=round(confidence_weight, 4),
                source_label=f"{tier_name}:{total_score:.2f}",
            ))

    raw.sort(key=lambda c: c.score, reverse=True)

    # De-dupe by near-identical time range, keeping the top-scoring hit.
    deduped: list[Candidate] = []
    tol = 0.01
    for c in raw:
        collision = next(
            (d for d in deduped
             if abs(d.start - c.start) < tol and abs(d.end - c.end) < tol),
            None,
        )
        if collision is None:
            deduped.append(c)

    return [c.to_dict() for c in deduped[:limit]]


def load_contact_variants(
    concept_id: Optional[str],
    sil_contact_path: Any,
) -> list[str]:
    """Scrape `sil_contact_languages.json` for any recorded variants of the
    given concept. Returns an empty list if the file is missing, malformed,
    or has no concept entry. Stable across future schema tweaks because we
    only read `concepts[concept_id]` and pull whichever strings it carries.
    """
    if not concept_id:
        return []
    try:
        import json
        import pathlib
    except Exception:
        return []
    try:
        path = pathlib.Path(sil_contact_path)
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []

    variants: list[str] = []
    cid = str(concept_id)
    for _lang_key, lang_entry in data.items():
        if not isinstance(lang_entry, dict):
            continue
        concepts = lang_entry.get("concepts")
        if not isinstance(concepts, dict):
            continue
        entry = concepts.get(cid)
        if entry is None:
            continue
        # Accept either a bare string, a list of strings, or a dict with
        # a "variants"/"forms" list — keeps us forgiving about future
        # schema additions from contact_lexeme_fetcher.
        if isinstance(entry, str):
            variants.append(entry)
        elif isinstance(entry, list):
            variants.extend(str(x) for x in entry if isinstance(x, (str, int, float)))
        elif isinstance(entry, dict):
            for key in ("variants", "forms", "surface", "orthographic"):
                val = entry.get(key)
                if isinstance(val, str):
                    variants.append(val)
                elif isinstance(val, list):
                    variants.extend(str(x) for x in val if isinstance(x, (str, int, float)))

    # Dedupe while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for v in variants:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique
