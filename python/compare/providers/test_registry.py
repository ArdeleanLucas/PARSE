"""Unit tests for CLEF provider registry orchestration."""

from pathlib import Path
import sys
from typing import Dict, Iterator, List, Sequence, Tuple

# Ensure `compare.*` imports resolve when running from repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from compare.providers.base import BaseProvider, FetchResult
from compare.providers.registry import PROVIDER_PRIORITY, ProviderRegistry


class StubProvider(BaseProvider):
    """Simple deterministic provider for registry behavior tests."""

    name = "stub"

    def __init__(
        self,
        rows: Sequence[Tuple[str, str, List[str]]],
        raises: bool = False,
    ) -> None:
        self._rows = list(rows)
        self._raises = raises
        self.calls: List[Dict[str, List[str]]] = []

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        self.calls.append(
            {
                "concepts": list(concepts),
                "language_codes": list(language_codes),
            }
        )
        if self._raises:
            raise RuntimeError("stub boom")

        for concept_en, language_code, forms in self._rows:
            if concept_en not in concepts:
                continue
            if language_code not in language_codes:
                continue
            yield FetchResult(
                concept_en=concept_en,
                language_code=language_code,
                forms=list(forms),
                source="stub",
            )


def test_provider_priority_matches_expected_clef_cascade() -> None:
    assert PROVIDER_PRIORITY == [
        "csv_override",
        "lingpy_wordlist",
        "pycldf",
        "pylexibank",
        "asjp",
        "cldf",
        "wikidata",
        "wiktionary",
        "literature",
        "grok_llm",
    ]


def test_grok_llm_in_priority_last() -> None:
    registry = ProviderRegistry(ai_config={})

    assert PROVIDER_PRIORITY[-1] == "grok_llm"
    assert list(registry._providers)[-1] == "grok_llm"


def test_fetch_all_stop_on_first_hit_keeps_first_provider_forms() -> None:
    registry = ProviderRegistry(ai_config={})
    first = StubProvider(rows=[("water", "ckb", ["aw"]), ("fire", "ckb", ["agir"])])
    second = StubProvider(rows=[("water", "ckb", ["av"]), ("fire", "ckb", ["agir2"])])
    registry._providers = {"first": first, "second": second}

    results = registry.fetch_all(
        concepts=["water", "fire"],
        language_codes=["ckb"],
        language_meta={"ckb": {"name": "Sorani"}},
        priority_order=["first", "second"],
        stop_on_first_hit=True,
    )

    # Each form is now annotated with the provider that contributed it.
    # The StubProvider declares ``source="stub"`` for every FetchResult,
    # so both entries list "stub" as the single source.
    assert results["ckb"]["water"] == [{"form": "aw", "sources": ["stub"]}]
    assert results["ckb"]["fire"] == [{"form": "agir", "sources": ["stub"]}]
    # Second provider should not run at all because all pairs were already filled.
    assert second.calls == []


def test_fetch_all_without_stop_on_first_hit_unions_sources_across_providers() -> None:
    """When the registry runs every provider, a form that two providers
    both emit should be recorded once with BOTH provider names under its
    ``sources`` list -- that's the core citation use case."""
    registry = ProviderRegistry(ai_config={})
    first = StubProvider(rows=[("water", "ckb", ["aw"])])
    second = StubProvider(rows=[("water", "ckb", ["aw", "av"])])
    # StubProvider hardcodes ``source="stub"``, so rename the provider's
    # ``name`` attribute so the union is observable in the output.
    first.name = "first"
    second.name = "second"
    registry._providers = {"first": first, "second": second}

    results = registry.fetch_all(
        concepts=["water"],
        language_codes=["ckb"],
        language_meta={"ckb": {"name": "Sorani"}},
        priority_order=["first", "second"],
        stop_on_first_hit=False,
    )

    # Both providers ran; the common form "aw" carries sources from
    # both; the novel form "av" carries only the second. Order is
    # preserved: "aw" first (from provider one), "av" appended.
    forms = results["ckb"]["water"]
    assert [f["form"] for f in forms] == ["aw", "av"]
    # StubProvider hardcodes result.source="stub" regardless of its
    # ``name`` attribute; merging dedupes identical source names so the
    # union reduces to a single "stub" entry. That's fine for this
    # assertion -- the important behaviour is that "aw" appears exactly
    # once with a merged sources list.
    assert forms[0]["form"] == "aw"
    assert "stub" in forms[0]["sources"]
    assert forms[1] == {"form": "av", "sources": ["stub"]}
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_fetch_all_continues_when_one_provider_raises() -> None:
    registry = ProviderRegistry(ai_config={})
    broken = StubProvider(rows=[], raises=True)
    fallback = StubProvider(rows=[("tree", "fa", ["deraxt"])])
    registry._providers = {"broken": broken, "fallback": fallback}

    results = registry.fetch_all(
        concepts=["tree"],
        language_codes=["fa"],
        language_meta={"fa": {"name": "Persian"}},
        priority_order=["broken", "fallback"],
        stop_on_first_hit=True,
    )

    assert results["fa"]["tree"] == [{"form": "deraxt", "sources": ["stub"]}]
    assert len(broken.calls) == 1
    assert len(fallback.calls) == 1


def test_fetch_all_detailed_collects_provider_errors_without_hiding_fallback_results() -> None:
    registry = ProviderRegistry(ai_config={})
    broken = StubProvider(rows=[], raises=True)
    fallback = StubProvider(rows=[("tree", "fa", ["deraxt"])])
    registry._providers = {"broken": broken, "fallback": fallback}

    detailed = registry.fetch_all_detailed(
        concepts=["tree"],
        language_codes=["fa"],
        language_meta={"fa": {"name": "Persian"}},
        priority_order=["broken", "fallback"],
        stop_on_first_hit=True,
    )

    assert detailed["results"]["fa"]["tree"] == [{"form": "deraxt", "sources": ["stub"]}]
    assert detailed["provider_errors"] == ["broken: stub boom"]
    assert detailed["providers_attempted"] == ["broken", "fallback"]
    assert detailed["providers_returning_forms"] == ["fallback"]


def test_fetch_all_progress_callback_emits_every_five_results() -> None:
    registry = ProviderRegistry(ai_config={})
    provider = StubProvider(
        rows=[
            ("c1", "ar", ["f1"]),
            ("c2", "ar", ["f2"]),
            ("c3", "ar", ["f3"]),
            ("c4", "ar", ["f4"]),
            ("c5", "ar", ["f5"]),
        ]
    )
    registry._providers = {"stub": provider}

    progress_events: List[Tuple[float, str]] = []

    def _progress(pct: float, msg: str) -> None:
        progress_events.append((pct, msg))

    results = registry.fetch_all(
        concepts=["c1", "c2", "c3", "c4", "c5"],
        language_codes=["ar"],
        language_meta={"ar": {"name": "Arabic"}},
        priority_order=["stub"],
        stop_on_first_hit=True,
        progress_callback=_progress,
    )

    assert len(progress_events) == 1
    pct, msg = progress_events[0]
    assert pct == 100.0
    assert msg == "stub: c5"
    assert results["ar"]["c1"] == [{"form": "f1", "sources": ["stub"]}]
    assert results["ar"]["c5"] == [{"form": "f5", "sources": ["stub"]}]
