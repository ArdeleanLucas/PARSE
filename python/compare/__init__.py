"""Compare pipeline scripts for PARSE."""

from .cognate_compute import compute_similarity_scores
from .cross_speaker_match import compute_matches
from .offset_detect import (
    OffsetResult,
    anchors_from_intervals,
    detect_offset,
    detect_offset_detailed,
    segments_from_raw,
)
from .phonetic_rules import (
    PhoneticRule,
    apply_rules,
    are_phonetically_equivalent,
    get_default_rules,
    load_rules_from_file,
)

__all__ = [
    "compute_similarity_scores",
    "compute_matches",
    "OffsetResult",
    "anchors_from_intervals",
    "detect_offset",
    "detect_offset_detailed",
    "segments_from_raw",
    "PhoneticRule",
    "apply_rules",
    "are_phonetically_equivalent",
    "get_default_rules",
    "load_rules_from_file",
]
