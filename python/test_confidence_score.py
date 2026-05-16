from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from typing import get_args, get_type_hints

import pytest

from ai.provider import ConfidenceScore, ConfidenceSource


def test_confidence_score_dataclass_shape() -> None:
    assert is_dataclass(ConfidenceScore)
    hints = get_type_hints(ConfidenceScore)
    assert hints["value"] is float
    assert hints["source"] == ConfidenceSource
    assert set(get_args(ConfidenceSource)) == {"avg_logprob", "constant_fallback"}
    assert hints["n_tokens"] is int

    score = ConfidenceScore(value=0.75, source="avg_logprob", n_tokens=3)
    assert score.value == pytest.approx(0.75)
    assert score.source == "avg_logprob"
    assert score.n_tokens == 3
    assert float(score) == pytest.approx(0.75)
    with pytest.raises(FrozenInstanceError):
        score.value = 0.5  # type: ignore[misc]


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan"), float("inf")])
def test_confidence_score_rejects_out_of_range_value(value: float) -> None:
    with pytest.raises(ValueError, match="ConfidenceScore.value"):
        ConfidenceScore(value=value, source="avg_logprob", n_tokens=1)


def test_confidence_score_rejects_negative_token_count() -> None:
    with pytest.raises(ValueError, match="ConfidenceScore.n_tokens"):
        ConfidenceScore(value=0.5, source="avg_logprob", n_tokens=-1)
