"""Tests for monotonicity-constrained offset detection + quantile anchor sampling.

Together these address the failure mode where the bucket-vote selector
elected the wrong direction because false matches (similar-sounding words
elsewhere in the recording) clustered in the same offset bin. With the
monotonic constraint, such false matches can't all win at once because they
violate temporal order.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from compare.offset_detect import (
    Anchor,
    MatchHypothesis,
    Segment,
    anchors_from_intervals,
    detect_offset_detailed,
    select_monotonic_matches,
)


def _hyp(anchor_index: int, segment_index: int, offset_sec: float, score: float = 0.9) -> MatchHypothesis:
    return MatchHypothesis(
        anchor_index=anchor_index,
        segment_index=segment_index,
        offset_sec=offset_sec,
        score=score,
    )


def _anchor(index: int, start_sec: float, text: str = "x") -> Anchor:
    return Anchor(index=index, start_sec=start_sec, text=text, tokens=[text])


def _segment(index: int, start_sec: float, text: str = "x") -> Segment:
    return Segment(index=index, start_sec=start_sec, end_sec=start_sec + 0.5, text=text, tokens=[text])


# -- select_monotonic_matches --------------------------------------------


def test_monotonic_picks_chain_in_order() -> None:
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0), _anchor(2, 30.0)]
    # Each anchor has a correct match (segment in order, offset +5) plus a
    # noisy candidate to an earlier segment (offset -10) — those would all
    # win the bucket vote but they violate monotonicity.
    hypotheses = [
        _hyp(0, 5, +5.0, score=0.9), _hyp(0, 1, -10.0, score=0.95),
        _hyp(1, 6, +5.0, score=0.9), _hyp(1, 1, -10.0, score=0.95),
        _hyp(2, 7, +5.0, score=0.9), _hyp(2, 1, -10.0, score=0.95),
    ]

    chain = select_monotonic_matches(anchors, hypotheses)
    assert len(chain) == 3
    chosen_offsets = sorted(h.offset_sec for h in chain)
    assert chosen_offsets == [5.0, 5.0, 5.0]
    # Segment indices must be strictly increasing along the chain.
    seg_path = [h.segment_index for h in chain]
    assert seg_path == sorted(seg_path)


def test_monotonic_returns_empty_if_no_chain_of_two_exists() -> None:
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0)]
    # Only one anchor has any match.
    hypotheses = [_hyp(0, 5, +5.0)]

    chain = select_monotonic_matches(anchors, hypotheses)
    assert chain == []


def test_monotonic_prefers_longer_chain_over_higher_score() -> None:
    anchors = [_anchor(0, 10.0), _anchor(1, 20.0), _anchor(2, 30.0)]
    # A two-element chain with high scores vs a three-element chain with
    # slightly lower scores. The three-element chain should win.
    hypotheses = [
        _hyp(0, 1, 0.0, score=0.99),
        _hyp(2, 9, 0.0, score=0.99),
        _hyp(0, 2, +1.0, score=0.7),
        _hyp(1, 3, +1.0, score=0.7),
        _hyp(2, 4, +1.0, score=0.7),
    ]

    chain = select_monotonic_matches(anchors, hypotheses)
    assert len(chain) == 3


# -- anchors_from_intervals quantile distribution -----------------------


def _intervals(timestamps: list) -> list:
    return [{"start": t, "end": t + 0.5, "text": "w{0}".format(i)} for i, t in enumerate(timestamps)]


def test_quantile_distribution_keeps_first_and_last_anchor() -> None:
    timestamps = list(range(0, 100, 5))  # 20 anchors at t=0..95
    anchors = anchors_from_intervals(_intervals(timestamps), n_anchors=5, distribution="quantile")
    assert len(anchors) == 5
    assert anchors[0].start_sec == 0.0
    assert anchors[-1].start_sec == 95.0
    # Middle samples should be roughly evenly distributed.
    mids = [a.start_sec for a in anchors]
    assert mids == sorted(mids)
    span = max(mids) - min(mids)
    assert span >= 90.0


def test_earliest_distribution_takes_first_n() -> None:
    timestamps = list(range(0, 100, 5))
    anchors = anchors_from_intervals(_intervals(timestamps), n_anchors=4, distribution="earliest")
    assert [a.start_sec for a in anchors] == [0.0, 5.0, 10.0, 15.0]


def test_quantile_returns_all_when_fewer_than_cap() -> None:
    timestamps = [10.0, 20.0]
    anchors = anchors_from_intervals(_intervals(timestamps), n_anchors=10, distribution="quantile")
    assert len(anchors) == 2


# -- detect_offset_detailed end-to-end -----------------------------------


def test_detect_uses_monotonic_method_when_chain_exists() -> None:
    anchors = [
        Anchor(index=0, start_sec=10.0, text="alpha", tokens=["alpha"]),
        Anchor(index=1, start_sec=20.0, text="beta", tokens=["beta"]),
        Anchor(index=2, start_sec=30.0, text="gamma", tokens=["gamma"]),
    ]
    segments = [
        Segment(index=0, start_sec=15.0, end_sec=15.5, text="alpha", tokens=["alpha"]),
        Segment(index=1, start_sec=25.0, end_sec=25.5, text="beta", tokens=["beta"]),
        Segment(index=2, start_sec=35.0, end_sec=35.5, text="gamma", tokens=["gamma"]),
    ]

    result = detect_offset_detailed(
        anchors=anchors, segments=segments, rules=[], bucket_sec=1.0, min_match_score=0.5
    )

    assert result.method == "monotonic_alignment"
    assert result.offset_sec == 5.0
    assert result.n_matched == 3
    assert result.spread_sec == 0.0
    assert len(result.matches) == 3


def test_detect_recovers_correct_offset_when_false_matches_present() -> None:
    """The original failure mode: each true word ('alpha', 'beta', 'gamma')
    is at +5 s, but each anchor also pseudo-matches an early 'alpha-ish'
    segment near t=1 s. Old bucket vote would elect ~−15s; monotonic
    alignment must keep the +5 s chain."""
    anchors = [
        Anchor(index=0, start_sec=10.0, text="alpha", tokens=["alpha"]),
        Anchor(index=1, start_sec=20.0, text="beta", tokens=["beta"]),
        Anchor(index=2, start_sec=30.0, text="alpha", tokens=["alpha"]),  # repeat
    ]
    segments = [
        # Three "false" early matches that all look like 'alpha'.
        Segment(index=0, start_sec=1.0, end_sec=1.4, text="alpha", tokens=["alpha"]),
        Segment(index=1, start_sec=2.0, end_sec=2.4, text="alpha", tokens=["alpha"]),
        Segment(index=2, start_sec=3.0, end_sec=3.4, text="alpha", tokens=["alpha"]),
        # The real matches at +5s offset.
        Segment(index=3, start_sec=15.0, end_sec=15.5, text="alpha", tokens=["alpha"]),
        Segment(index=4, start_sec=25.0, end_sec=25.5, text="beta", tokens=["beta"]),
        Segment(index=5, start_sec=35.0, end_sec=35.5, text="alpha", tokens=["alpha"]),
    ]

    result = detect_offset_detailed(
        anchors=anchors, segments=segments, rules=[], bucket_sec=1.0, min_match_score=0.5
    )

    assert result.method == "monotonic_alignment"
    assert result.offset_sec == 5.0
    # Three matches in a +5 chain; not the false −9/−18/−27 ones.
    chosen = sorted(m["offset_sec"] for m in result.matches)
    assert chosen == [5.0, 5.0, 5.0]
