"""
pylexibank_provider.py — Use pylexibank-installed datasets as Python packages.

Requires: pip install pylexibank
Then install datasets: pip install pylexibank-northeuralex pylexibank-ids etc.

If pylexibank is not installed, this provider is a silent no-op.
Normalization: none.
"""

from typing import Dict, Iterator, List
from .base import BaseProvider, FetchResult

try:
    import pylexibank  # type: ignore
    PYLEXIBANK_AVAILABLE = True
except ImportError:
    PYLEXIBANK_AVAILABLE = False

# Known pylexibank dataset package names and their language coverage
# Add to this list as datasets are installed
KNOWN_DATASETS = [
    "northeuralex",   # pip install pylexibank-northeuralex  — covers fa, tr
    "ids",            # pip install pylexibank-ids             — covers ar, fa, tr
    "wold",           # pip install pylexibank-wold            — loanword database
]

ISO_FRAGMENTS: Dict[str, List[str]] = {
    "ar":  ["arb", "arabic", "ar"],
    "fa":  ["pes", "persian", "fa", "farsi"],
    "ckb": ["ckb", "sorani", "central kurdish", "kurdish"],
    "tr":  ["tur", "turkish", "tr"],
}


class PylexibankProvider(BaseProvider):
    name = "pylexibank"

    def _load_installed_datasets(self):
        """Return list of installed pylexibank Dataset objects."""
        if not PYLEXIBANK_AVAILABLE:
            return []
        datasets = []
        for pkg_name in KNOWN_DATASETS:
            try:
                import importlib
                mod = importlib.import_module(pkg_name)
                ds = mod.Dataset()
                datasets.append(ds)
            except (ImportError, AttributeError, Exception):
                continue
        return datasets

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        if not PYLEXIBANK_AVAILABLE:
            return

        datasets = self._load_installed_datasets()
        if not datasets:
            return

        for lang_code in language_codes:
            frags = ISO_FRAGMENTS.get(lang_code, [lang_code])

            for concept_en in concepts:
                all_forms: List[str] = []

                for ds in datasets:
                    try:
                        cldf = ds.cldf_reader()
                        lang_ids = set()
                        for row in cldf["LanguageTable"]:
                            lid = str(row.get("ID") or "").lower()
                            lname = str(row.get("Name") or "").lower()
                            for frag in frags:
                                if frag in lid or frag in lname:
                                    lang_ids.add(row["ID"])
                                    break

                        concept_lower = concept_en.lower()
                        param_ids = set()
                        for row in cldf["ParameterTable"]:
                            pname = str(row.get("Name") or row.get("Concepticon_Gloss") or "").lower()
                            if pname == concept_lower or pname.startswith(concept_lower + " ") or concept_lower.startswith(pname):
                                param_ids.add(row["ID"])

                        for row in cldf["FormTable"]:
                            if row["Language_ID"] in lang_ids and row["Parameter_ID"] in param_ids:
                                form = str(row.get("Form") or row.get("Value") or "").strip()
                                if form and form not in ("-", "0") and form not in all_forms:
                                    all_forms.append(form)
                    except Exception:
                        continue

                yield FetchResult(
                    concept_en=concept_en,
                    language_code=lang_code,
                    forms=all_forms[:3],
                    source="pylexibank",
                )
