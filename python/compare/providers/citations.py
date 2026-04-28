"""Academic citations for the CLEF Sources Report.

Each provider in ``PROVIDER_PRIORITY`` carries a canonical bibliographic
reference that the Sources Report modal renders alongside the per-form
provider chip. The citations are dataset-level, not per-form: an ASJP
entry currently can't be deep-linked to a specific row, only attributed
to "the ASJP database (version 20)". A follow-up change can extend the
``FetchResult`` shape to attach per-form metadata (URL, dataset version,
retrieval date, lexeme id) for true per-form citations.

Schema -- one entry per provider id::

    {
      "label":   "Wikidata",
      "type":    "dataset" | "tool" | "ai" | "manual" | "sentinel",
      "authors": "Vrandečić, D. & Krötzsch, M.",
      "year":    2014,
      "title":   "Wikidata: a free collaborative knowledgebase",
      "venue":   "Communications of the ACM 57(10): 78-85",
      "doi":     "10.1145/2629489",
      "url":     "https://www.wikidata.org",
      "license": "CC0-1.0",
      "note":    "(optional caveat -- e.g. 'LLM-generated, must be verified')",
      "citation": "Vrandečić, D. & Krötzsch, M. 2014. Wikidata: a free collaborative knowledgebase. Communications of the ACM 57(10): 78-85. doi:10.1145/2629489",
      "bibtex":   "@article{wikidata2014, ...}"
    }

The free-text ``citation`` is what most readers paste into a footnote.
``bibtex`` lets the user export a single .bib for the whole report.
``type`` lets the modal flag the LLM and sentinel entries differently.

The keys here MUST match the provider ids registered in
``compare/providers/registry.PROVIDER_PRIORITY`` plus the
``compare/providers/provenance.UNKNOWN_SOURCE`` sentinel. A test in
``test_citations.py`` enforces that contract so a new provider can't
ship without a citation entry.
"""

from __future__ import annotations

from typing import Any, Dict


# Stable order so the modal can render a consistent provider list across
# refreshes. Not enforced -- the registry's PROVIDER_PRIORITY drives the
# real fetch order; this list just controls display when iterating the
# citations map.
CITATION_DISPLAY_ORDER = (
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
    "unknown",
)


PROVIDER_CITATIONS: Dict[str, Dict[str, Any]] = {
    "asjp": {
        "label": "ASJP",
        "type": "dataset",
        "authors": "Wichmann, S., Holman, E. W., & Brown, C. H. (eds.)",
        "year": 2022,
        "title": "The ASJP Database (version 20)",
        "venue": "Max Planck Institute for Evolutionary Anthropology",
        "url": "https://asjp.clld.org",
        "license": "CC-BY-4.0",
        "citation": (
            "Wichmann, S., Holman, E. W., & Brown, C. H. (eds.). 2022. "
            "The ASJP Database (version 20). "
            "Max Planck Institute for Evolutionary Anthropology. "
            "https://asjp.clld.org"
        ),
        "bibtex": (
            "@misc{asjp2022,\n"
            "  author = {Wichmann, Søren and Holman, Eric W. and Brown, Cecil H.},\n"
            "  title = {{The ASJP Database (version 20)}},\n"
            "  year = {2022},\n"
            "  publisher = {Max Planck Institute for Evolutionary Anthropology},\n"
            "  url = {https://asjp.clld.org}\n"
            "}"
        ),
    },
    "wikidata": {
        "label": "Wikidata",
        "type": "dataset",
        "authors": "Vrandečić, D. & Krötzsch, M.",
        "year": 2014,
        "title": "Wikidata: a free collaborative knowledgebase",
        "venue": "Communications of the ACM 57(10): 78-85",
        "doi": "10.1145/2629489",
        "url": "https://www.wikidata.org",
        "license": "CC0-1.0",
        "citation": (
            "Vrandečić, D. & Krötzsch, M. 2014. Wikidata: a free collaborative "
            "knowledgebase. Communications of the ACM 57(10): 78-85. "
            "doi:10.1145/2629489"
        ),
        "bibtex": (
            "@article{wikidata2014,\n"
            "  author = {Vrandečić, Denny and Krötzsch, Markus},\n"
            "  title = {{Wikidata: A Free Collaborative Knowledgebase}},\n"
            "  journal = {Communications of the ACM},\n"
            "  volume = {57},\n"
            "  number = {10},\n"
            "  pages = {78--85},\n"
            "  year = {2014},\n"
            "  doi = {10.1145/2629489}\n"
            "}"
        ),
    },
    "wiktionary": {
        "label": "Wiktionary",
        "type": "dataset",
        "authors": "Wiktionary contributors",
        "year": None,  # rolling -- citation includes "accessed YYYY-MM-DD"
        "title": "Wiktionary, the free dictionary",
        "url": "https://www.wiktionary.org",
        "license": "CC-BY-SA-4.0",
        "note": "Per-page revision history available via the wiki history view.",
        "citation": (
            "Wiktionary contributors. Wiktionary, the free dictionary. "
            "Wikimedia Foundation. https://www.wiktionary.org "
            "(accessed via the PARSE CLEF populate run; check entry history "
            "for the revision used)."
        ),
        "bibtex": (
            "@misc{wiktionary,\n"
            "  author = {{Wiktionary contributors}},\n"
            "  title = {{Wiktionary, the free dictionary}},\n"
            "  publisher = {Wikimedia Foundation},\n"
            "  url = {https://www.wiktionary.org},\n"
            "  note = {Accessed via PARSE CLEF; entry-level revisions in page history}\n"
            "}"
        ),
    },
    "cldf": {
        "label": "CLDF",
        "type": "dataset",
        "authors": "Forkel, R., List, J.-M., Greenhill, S. J., Rzymski, C., Bank, S., Cysouw, M., Hammarström, H., Haspelmath, M., Kaiping, G. A., & Gray, R. D.",
        "year": 2018,
        "title": "Cross-Linguistic Data Formats, advancing data sharing and re-use in comparative linguistics",
        "venue": "Scientific Data 5: 180205",
        "doi": "10.1038/sdata.2018.205",
        "url": "https://cldf.clld.org",
        "license": "CC-BY-4.0",
        "citation": (
            "Forkel, R. et al. 2018. Cross-Linguistic Data Formats, advancing "
            "data sharing and re-use in comparative linguistics. "
            "Scientific Data 5: 180205. doi:10.1038/sdata.2018.205"
        ),
        "bibtex": (
            "@article{cldf2018,\n"
            "  author = {Forkel, Robert and List, Johann-Mattis and Greenhill, "
            "Simon J. and Rzymski, Christoph and Bank, Sebastian and Cysouw, "
            "Michael and Hammarström, Harald and Haspelmath, Martin and Kaiping, "
            "Gereon A. and Gray, Russell D.},\n"
            "  title = {{Cross-Linguistic Data Formats, advancing data sharing "
            "and re-use in comparative linguistics}},\n"
            "  journal = {Scientific Data},\n"
            "  volume = {5},\n"
            "  pages = {180205},\n"
            "  year = {2018},\n"
            "  doi = {10.1038/sdata.2018.205}\n"
            "}"
        ),
    },
    "pycldf": {
        "label": "pycldf",
        "type": "tool",
        "authors": "Forkel, R.",
        "year": 2024,
        "title": "pycldf: A Python library to read and write CLDF datasets",
        "url": "https://github.com/cldf/pycldf",
        "license": "Apache-2.0",
        "note": "Cite the underlying CLDF dataset(s) too; pycldf is the loader.",
        "citation": (
            "Forkel, R. 2024. pycldf: A Python library to read and write "
            "CLDF datasets. https://github.com/cldf/pycldf"
        ),
        "bibtex": (
            "@misc{pycldf,\n"
            "  author = {Forkel, Robert},\n"
            "  title = {{pycldf: A Python library to read and write CLDF datasets}},\n"
            "  year = {2024},\n"
            "  url = {https://github.com/cldf/pycldf}\n"
            "}"
        ),
    },
    "pylexibank": {
        "label": "Lexibank / pylexibank",
        "type": "dataset",
        "authors": "List, J.-M., Forkel, R., Greenhill, S. J., Rzymski, C., Englisch, J., & Gray, R. D.",
        "year": 2022,
        "title": "Lexibank, a public repository of standardized wordlists with computed phonological and lexical features",
        "venue": "Scientific Data 9: 316",
        "doi": "10.1038/s41597-022-01432-0",
        "url": "https://lexibank.clld.org",
        "license": "CC-BY-4.0",
        "note": "Cite the specific Lexibank wordlist used in addition to this umbrella reference.",
        "citation": (
            "List, J.-M., Forkel, R., Greenhill, S. J., Rzymski, C., Englisch, J., "
            "& Gray, R. D. 2022. Lexibank, a public repository of standardized "
            "wordlists with computed phonological and lexical features. "
            "Scientific Data 9: 316. doi:10.1038/s41597-022-01432-0"
        ),
        "bibtex": (
            "@article{lexibank2022,\n"
            "  author = {List, Johann-Mattis and Forkel, Robert and Greenhill, "
            "Simon J. and Rzymski, Christoph and Englisch, Johannes and Gray, "
            "Russell D.},\n"
            "  title = {{Lexibank, a public repository of standardized wordlists "
            "with computed phonological and lexical features}},\n"
            "  journal = {Scientific Data},\n"
            "  volume = {9},\n"
            "  pages = {316},\n"
            "  year = {2022},\n"
            "  doi = {10.1038/s41597-022-01432-0}\n"
            "}"
        ),
    },
    "lingpy_wordlist": {
        "label": "LingPy",
        "type": "tool",
        "authors": "List, J.-M., Greenhill, S. J., Tresoldi, T., & Forkel, R.",
        "year": 2023,
        "title": "LingPy. A Python library for quantitative tasks in historical linguistics",
        "doi": "10.5281/zenodo.10093521",
        "url": "https://lingpy.org",
        "license": "GPL-3.0",
        "note": "Cite the underlying CLDF/Lexibank wordlist too; LingPy is the loader.",
        "citation": (
            "List, J.-M., Greenhill, S. J., Tresoldi, T., & Forkel, R. 2023. "
            "LingPy. A Python library for quantitative tasks in historical "
            "linguistics. doi:10.5281/zenodo.10093521"
        ),
        "bibtex": (
            "@software{lingpy2023,\n"
            "  author = {List, Johann-Mattis and Greenhill, Simon J. and Tresoldi, "
            "Tiago and Forkel, Robert},\n"
            "  title = {{LingPy. A Python library for quantitative tasks in "
            "historical linguistics}},\n"
            "  year = {2023},\n"
            "  doi = {10.5281/zenodo.10093521},\n"
            "  url = {https://lingpy.org}\n"
            "}"
        ),
    },
    "csv_override": {
        "label": "CSV override (workspace-local)",
        "type": "manual",
        "authors": "Workspace maintainer",
        "year": None,
        "title": "Per-workspace CSV override",
        "note": (
            "User-curated forms loaded from config/clef_overrides.csv. "
            "Provenance is whatever the maintainer recorded in their own notes."
        ),
        "citation": (
            "Per-workspace CSV override (config/clef_overrides.csv). "
            "Cite the maintainer's source notes for each entry."
        ),
        "bibtex": "",  # not bibliographically citable -- workspace-local
    },
    "literature": {
        "label": "Literature (workspace-local)",
        "type": "manual",
        "authors": "Workspace maintainer",
        "year": None,
        "title": "Manually curated literature references",
        "note": (
            "Forms loaded from the literature provider's per-workspace config. "
            "Each entry should carry its own bibliographic source -- see the "
            "provider's config file for per-form citations."
        ),
        "citation": (
            "Workspace-local literature references. "
            "See the literature provider's config for per-form bibliographic sources."
        ),
        "bibtex": "",
    },
    "grok_llm": {
        "label": "Grok LLM (LLM-generated)",
        "type": "ai",
        "authors": None,
        "year": None,
        "title": "LLM-generated reference forms (xAI Grok / OpenAI GPT)",
        "note": (
            "NOT CITABLE AS A PRIMARY SOURCE. LLM output -- model name + "
            "version + prompt are recorded in the populate job log, but the "
            "underlying training data is not auditable. Verify each form "
            "against an authoritative source before using in published work."
        ),
        "citation": (
            "Grok LLM provider: LLM-generated reference forms (xAI Grok or "
            "OpenAI GPT, depending on auth_tokens.json). Not citable as a "
            "primary source -- verify each form before publication."
        ),
        "bibtex": "",  # intentionally empty -- LLM output is not bibliographic
    },
    "unknown": {
        "label": "Unattributed (legacy)",
        "type": "sentinel",
        "authors": None,
        "year": None,
        "title": "Pre-provenance bare-string entry",
        "note": (
            "These forms were populated before PR #209 introduced provenance "
            "tracking, so the provider that contributed each form is not "
            "recorded on disk. Re-run CLEF populate with overwrite=true to "
            "re-attribute the entries."
        ),
        "citation": (
            "Unattributed legacy entry: provider not recorded. "
            "Re-run CLEF populate with overwrite=true to attribute."
        ),
        "bibtex": "",
    },
}


def get_citations() -> Dict[str, Dict[str, Any]]:
    """Return a deep-copy-safe view of the provider citation map.

    The Sources Report endpoint surfaces this as part of its JSON payload
    so the modal renders citations without a second round-trip.
    """
    return {k: dict(v) for k, v in PROVIDER_CITATIONS.items()}


def get_citation(provider_id: str) -> Dict[str, Any]:
    """Look up the citation block for ``provider_id``.

    Falls back to the ``unknown`` sentinel for unrecognised providers so
    the modal can still render a row instead of crashing.
    """
    entry = PROVIDER_CITATIONS.get(provider_id)
    if entry is None:
        return dict(PROVIDER_CITATIONS["unknown"])
    return dict(entry)
