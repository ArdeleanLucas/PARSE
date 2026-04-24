"""Shared helpers for reading provenance-annotated CLEF form entries.

The SIL contact-language config stores per-concept forms under
``<lang>.concepts.<concept_en>``. Two shapes coexist:

- Legacy (pre-PR): ``["ma:ʔ", "mɑ"]`` — bare list of form strings. No
  provenance information at all.
- New (this PR): ``[{"form": "ma:ʔ", "sources": ["wikidata"]}, ...]`` —
  each form carries the list of providers that independently produced
  it.

Every reader (API endpoints, sources report, future exports) must cope
with both shapes so rolling the feature forward doesn't force a
corpus-wide re-populate. Use :func:`iter_forms_with_sources` for that.

The sentinel ``"unknown"`` fills in for legacy entries that never went
through the new pipeline. Consumers can choose to display it as
"unattributed" (sources report) or simply hide it (export formats).
"""

from typing import Any, Iterable, List, Tuple

# Sentinel provider name used when legacy (pre-provenance) forms are
# observed. The sources report surfaces these as "unattributed" so the
# distinction between "we know no provider" and "we know the provider"
# stays visible in academic citations.
UNKNOWN_SOURCE = "unknown"


def iter_forms_with_sources(entry: Any) -> Iterable[Tuple[str, List[str]]]:
    """Yield ``(form, sources)`` tuples from one concept entry regardless
    of which schema version it was written in.

    - ``None`` / empty list -> yields nothing.
    - ``["x", "y"]`` -> yields ``("x", ["unknown"])``, ``("y", ["unknown"])``.
    - ``[{"form": "x", "sources": ["wikidata"]}]`` -> yields
      ``("x", ["wikidata"])``.
    - Malformed items (non-string forms, dicts without ``form``) are
      skipped silently so a single bad row can't break the whole report.
    """
    if not entry or not isinstance(entry, list):
        return
    for item in entry:
        if isinstance(item, str):
            form = item.strip()
            if form:
                yield form, [UNKNOWN_SOURCE]
        elif isinstance(item, dict):
            form = item.get("form")
            if not isinstance(form, str) or not form.strip():
                continue
            sources_raw = item.get("sources")
            if isinstance(sources_raw, list) and sources_raw:
                sources = [str(s) for s in sources_raw if isinstance(s, (str, int)) and str(s).strip()]
                if not sources:
                    sources = [UNKNOWN_SOURCE]
            else:
                sources = [UNKNOWN_SOURCE]
            yield form.strip(), sources


def entry_has_forms(entry: Any) -> bool:
    """True if ``entry`` contains at least one non-empty form."""
    for _ in iter_forms_with_sources(entry):
        return True
    return False
