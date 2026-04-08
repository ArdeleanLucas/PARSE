"""
lingpy_wordlist.py — Load local CLDF datasets using LingPy Wordlist.from_cldf().

Data: drop git-cloned Lexibank datasets into config/lexibank_data/.
Priority: high (local, scholarly, IPA).
Normalization: none — forms returned verbatim.
"""

from pathlib import Path
from typing import Dict, Iterator, List
from .base import BaseProvider, FetchResult


class LingPyCldfProvider(BaseProvider):
    name = "lingpy_wordlist"

    def __init__(self) -> None:
        self._data_dir = (
            Path(__file__).resolve().parents[3] / "config" / "lexibank_data"
        )

    def _find_metadata_files(self) -> List[Path]:
        if not self._data_dir.exists():
            return []
        return sorted(self._data_dir.glob("**/cldf/*-metadata.json"))

    def _load_dataset(self, metadata_path: Path):
        """Load CLDF dataset using Wordlist.from_cldf(). Returns None on failure."""
        try:
            from lingpy import Wordlist  # type: ignore
            wl = Wordlist.from_cldf(
                str(metadata_path),
                columns=(
                    "parameter_id",
                    "concept_name",
                    "language_id",
                    "language_name",
                    "value",
                    "form",
                    "segments",
                    "language_glottocode",
                ),
                namespace=(
                    ("concept_name", "concept"),
                    ("language_id", "doculect"),
                ),
            )
            return wl
        except Exception as e:
            import sys
            print(f"[lingpy_wordlist] failed to load {metadata_path}: {e}", file=sys.stderr)
            return None

    def _build_index(self, wl) -> Dict[str, Dict[str, List[str]]]:
        """Build {lang_key: {concept_lower: [forms]}} from a loaded LingPy Wordlist."""
        index: Dict[str, Dict[str, List[str]]] = {}
        try:
            for idx in wl:
                # Language: prefer doculect ID, fall back to language_name
                lang_parts = []
                for col in ("doculect", "language_name", "glottolog"):
                    try:
                        v = str(wl[idx, col] or "").strip().lower()
                        if v:
                            lang_parts.append(v)
                    except Exception:
                        pass
                if not lang_parts:
                    continue
                # Store under ALL lang identifiers for flexible matching
                for lang_key in lang_parts:
                    # Concept
                    try:
                        concept = str(wl[idx, "concept"] or "").strip().lower()
                    except Exception:
                        concept = ""
                    if not concept:
                        continue
                    # Form: prefer "value" (native script / IPA), fall back to "form" (ASJP)
                    form = ""
                    for col in ("value", "form"):
                        try:
                            v = str(wl[idx, col] or "").strip()
                            if v and v not in ("-", "0", ""):
                                form = v
                                break
                        except Exception:
                            pass
                    if not form:
                        continue

                    lang_entry = index.setdefault(lang_key, {})
                    forms_list = lang_entry.setdefault(concept, [])
                    if form not in forms_list:
                        forms_list.append(form)
        except Exception as e:
            import sys
            print(f"[lingpy_wordlist] index build error: {e}", file=sys.stderr)
        return index

    def _match_concept(
        self, concept_en: str, concept_index: Dict[str, List[str]]
    ) -> List[str]:
        """
        Match concept_en against concept_index keys using:
        1. Exact case-insensitive match
        2. concept_en is a prefix of the key (e.g. "bark" matches "bark of tree")
        3. key is a prefix of concept_en
        Returns forms for the best match found.
        """
        c = concept_en.lower().strip()
        # 1. exact
        if c in concept_index:
            return concept_index[c]
        # 2. concept_en is prefix
        for key, forms in concept_index.items():
            if key.startswith(c + " ") or key.startswith(c + "("):
                return forms
        # 3. key is prefix of concept_en
        for key, forms in concept_index.items():
            if c.startswith(key):
                return forms
        return []

    def _iso_to_lang_keys(self, iso: str) -> List[str]:
        """
        Return candidate lang key fragments to match against the dataset's language IDs.
        A dataset might use 'pes', 'Persian', 'fa', 'Persian (Iran)', etc.
        We try all reasonable fragments.
        """
        ISO_FRAGMENTS: Dict[str, List[str]] = {
            "ar":  ["arb", "arabic", "ar", "ara"],
            "fa":  ["pes", "persian", "fa", "fas", "iranian", "farsi"],
            "ckb": ["ckb", "sorani", "central kurdish", "kurdish", "kur"],
            "tr":  ["tur", "turkish", "tr", "turk"],
        }
        return ISO_FRAGMENTS.get(iso, [iso])

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        metadata_files = self._find_metadata_files()
        if not metadata_files:
            return

        # Load and index all datasets
        all_indices: List[Dict[str, Dict[str, List[str]]]] = []
        for mf in metadata_files:
            wl = self._load_dataset(mf)
            if wl is not None:
                all_indices.append(self._build_index(wl))

        if not all_indices:
            return

        for lang_code in language_codes:
            fragments = self._iso_to_lang_keys(lang_code)

            for concept_en in concepts:
                all_forms: List[str] = []

                for index in all_indices:
                    # Find matching language key in this dataset
                    matched_concept_index: Dict[str, List[str]] = {}
                    for lang_key, concept_dict in index.items():
                        for frag in fragments:
                            if frag in lang_key:
                                # Merge this language's concepts in
                                for ck, fv in concept_dict.items():
                                    matched_concept_index.setdefault(ck, []).extend(fv)
                                break

                    forms = self._match_concept(concept_en, matched_concept_index)
                    for f in forms:
                        if f and f not in all_forms:
                            all_forms.append(f)

                yield FetchResult(
                    concept_en=concept_en,
                    language_code=lang_code,
                    forms=all_forms[:3],  # cap at 3 forms
                    source="lingpy_wordlist",
                )
