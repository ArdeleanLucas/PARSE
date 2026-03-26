#!/usr/bin/env python3
"""Phonetic variation rules engine for PARSE Compare mode.

Usage:
    python phonetic_rules.py --form1 "jek" --form2 "yek" --rules config/phonetic_rules.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple, Union


VALID_CONTEXTS: Set[str] = {"onset", "coda", "nucleus", "intervocalic", "any"}
DEFAULT_EQUIVALENCE_THRESHOLD = 0.78
MAX_VARIANTS = 1024

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "phonetic_rules.json"

BOUNDARY_CHARS: Set[str] = {"", " ", "-", "_", ".", "|", "/"}

VOWEL_CHARS: Set[str] = {
    "a",
    "e",
    "i",
    "o",
    "u",
    "y",
    "ə",
    "ɛ",
    "æ",
    "ɪ",
    "ʊ",
    "ɔ",
    "ɒ",
    "ɑ",
    "ɐ",
    "ʉ",
    "ø",
    "œ",
    "ɜ",
    "ɞ",
    "ɤ",
    "ʌ",
    "ɚ",
    "ɝ",
    "ê",
    "î",
    "û",
}


@dataclass(frozen=True)
class PhoneticRule:
    """Single contextual rewrite rule."""

    source: str
    target: str
    context: str
    bidirectional: bool


RuleInput = Union[PhoneticRule, Dict[str, Any]]

DEFAULT_RULES: List[Dict[str, Any]] = [
    {"from": "j", "to": "y", "context": "onset", "bidirectional": True},
    {"from": "e", "to": "a", "context": "nucleus", "bidirectional": True},
    {"from": "k", "to": "g", "context": "onset", "bidirectional": True},
    {"from": "b", "to": "v", "context": "intervocalic", "bidirectional": False},
    {"from": "b", "to": "w", "context": "intervocalic", "bidirectional": False},
    {"from": "d", "to": "ð", "context": "intervocalic", "bidirectional": True},
    {"from": "g", "to": "ɣ", "context": "intervocalic", "bidirectional": True},
]


def _warn(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


def _error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def normalize_ipa_form(ipa_form: str) -> str:
    """Normalize IPA-ish text for matching."""
    text = str(ipa_form or "").strip().lower()
    if text.startswith("/") and text.endswith("/") and len(text) >= 2:
        text = text[1:-1]
    if text.startswith("[") and text.endswith("]") and len(text) >= 2:
        text = text[1:-1]
    text = " ".join(text.split())
    return text


def _has_vowel(value: str) -> bool:
    return any(ch in VOWEL_CHARS for ch in value)


def _context_matches(form: str, start_idx: int, end_idx: int, source: str, context: str) -> bool:
    if context == "any":
        return True

    left = form[start_idx - 1] if start_idx > 0 else ""
    right = form[end_idx] if end_idx < len(form) else ""

    if context == "onset":
        return left in BOUNDARY_CHARS

    if context == "coda":
        return right in BOUNDARY_CHARS

    if context == "nucleus":
        return _has_vowel(source)

    if context == "intervocalic":
        return left in VOWEL_CHARS and right in VOWEL_CHARS

    return False


def _iter_rule_directions(rule: PhoneticRule) -> Iterable[Tuple[str, str, str]]:
    yield (rule.source, rule.target, rule.context)
    if rule.bidirectional and rule.source != rule.target:
        yield (rule.target, rule.source, rule.context)


def parse_rules(rules: Sequence[RuleInput]) -> List[PhoneticRule]:
    """Parse/validate rule inputs from JSON or call-sites."""
    parsed: List[PhoneticRule] = []

    for idx, entry in enumerate(rules):
        if isinstance(entry, PhoneticRule):
            parsed.append(entry)
            continue

        if not isinstance(entry, dict):
            _warn(f"Rule {idx} ignored: expected object, got {type(entry).__name__}")
            continue

        source = str(entry.get("from", "")).strip()
        has_target_key = "to" in entry
        target = str(entry.get("to", "")).strip() if has_target_key else ""
        context = str(entry.get("context", "any")).strip().lower() or "any"
        bidirectional = bool(entry.get("bidirectional", False))

        if not source:
            _warn(f"Rule {idx} ignored: 'from' is required")
            continue
        if not has_target_key:
            _warn(f"Rule {idx} ignored: 'to' is required")
            continue
        if context not in VALID_CONTEXTS:
            _warn(
                f"Rule {idx} ignored: invalid context '{context}' "
                f"(allowed: {', '.join(sorted(VALID_CONTEXTS))})"
            )
            continue

        parsed.append(
            PhoneticRule(
                source=source,
                target=target,
                context=context,
                bidirectional=bidirectional,
            )
        )

    return parsed


def get_default_rules() -> List[PhoneticRule]:
    """Return built-in Kurdish-focused defaults."""
    return parse_rules(DEFAULT_RULES)


def load_rules_from_file(rules_path: Path) -> List[PhoneticRule]:
    """Load rule definitions from JSON file."""
    if not rules_path.exists():
        _warn(f"Rules file not found: {rules_path}; using built-in defaults")
        return get_default_rules()

    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _warn(f"Failed to read rules from {rules_path}: {exc}; using built-in defaults")
        return get_default_rules()

    raw_rules: Sequence[RuleInput]
    if isinstance(data, list):
        raw_rules = data
    elif isinstance(data, dict) and isinstance(data.get("rules"), list):
        raw_rules = data["rules"]
    else:
        _warn("Rules JSON must be an array or an object with 'rules' array; using defaults")
        return get_default_rules()

    parsed = parse_rules(raw_rules)
    if not parsed:
        _warn("No valid rules found in file; using built-in defaults")
        return get_default_rules()
    return parsed


def _generate_variants(form: str, rules: Sequence[PhoneticRule], max_variants: int = MAX_VARIANTS) -> Set[str]:
    """Generate contextual rewrite variants with bounded BFS."""
    seed = normalize_ipa_form(form)
    if not seed:
        return {""}

    seen: Set[str] = {seed}
    queue: List[str] = [seed]

    while queue:
        current = queue.pop(0)

        for rule in rules:
            for source, target, context in _iter_rule_directions(rule):
                start = 0
                while True:
                    idx = current.find(source, start)
                    if idx < 0:
                        break

                    end_idx = idx + len(source)
                    if _context_matches(current, idx, end_idx, source, context):
                        candidate = current[:idx] + target + current[end_idx:]
                        if candidate not in seen:
                            seen.add(candidate)
                            queue.append(candidate)
                            if len(seen) >= max_variants:
                                return seen

                    start = idx + 1

    return seen


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


def _similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0

    distance = _levenshtein_distance(left, right)
    max_len = max(len(left), len(right))
    return max(0.0, 1.0 - (distance / max_len)) if max_len else 1.0


def _canonical_variant(variants: Set[str]) -> str:
    if not variants:
        return ""
    return min(variants, key=lambda item: (len(item), item))


def apply_rules(ipa_form: str, rules: List[RuleInput]) -> str:
    """Apply contextual rules and return a canonical normalized form."""
    parsed_rules = parse_rules(rules)
    if not parsed_rules:
        return normalize_ipa_form(ipa_form)

    variants = _generate_variants(ipa_form, parsed_rules)
    return _canonical_variant(variants)


def are_phonetically_equivalent(form1: str, form2: str, rules: List[RuleInput]) -> Tuple[bool, float]:
    """Return (equivalent, similarity_score) for two forms."""
    parsed_rules = parse_rules(rules)
    norm1 = normalize_ipa_form(form1)
    norm2 = normalize_ipa_form(form2)

    if not norm1 and not norm2:
        return (True, 1.0)
    if not norm1 or not norm2:
        return (False, 0.0)

    if not parsed_rules:
        score = round(_similarity(norm1, norm2), 3)
        return (score >= DEFAULT_EQUIVALENCE_THRESHOLD, score)

    variants1 = _generate_variants(norm1, parsed_rules)
    variants2 = _generate_variants(norm2, parsed_rules)

    if variants1.intersection(variants2):
        return (True, 1.0)

    best_score = 0.0
    pair_budget = 4096
    checked = 0

    for left in variants1:
        for right in variants2:
            best_score = max(best_score, _similarity(left, right))
            checked += 1
            if checked >= pair_budget:
                break
        if checked >= pair_budget:
            break

    if checked < pair_budget:
        canonical1 = _canonical_variant(variants1)
        canonical2 = _canonical_variant(variants2)
        best_score = max(best_score, _similarity(canonical1, canonical2))

    score_rounded = round(best_score, 3)
    return (score_rounded >= DEFAULT_EQUIVALENCE_THRESHOLD, score_rounded)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply phonetic variation rules to compare forms.")
    parser.add_argument("--form1", required=True, help="First IPA form")
    parser.add_argument("--form2", required=True, help="Second IPA form")
    parser.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES_PATH,
        help="Path to phonetic_rules.json",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    rules = load_rules_from_file(args.rules)
    equivalent, similarity = are_phonetically_equivalent(args.form1, args.form2, list(rules))

    output = {
        "form1": args.form1,
        "form2": args.form2,
        "form1_normalized": apply_rules(args.form1, list(rules)),
        "form2_normalized": apply_rules(args.form2, list(rules)),
        "equivalent": equivalent,
        "similarity": similarity,
        "threshold": DEFAULT_EQUIVALENCE_THRESHOLD,
        "rules_loaded": len(rules),
        "rules_path": str(args.rules),
    }

    try:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as exc:  # pragma: no cover - defensive serialization guard
        _error(f"Failed to serialize result: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
