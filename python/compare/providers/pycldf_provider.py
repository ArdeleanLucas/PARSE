"""
pycldf_provider.py — Load local CLDF datasets using pycldf.Dataset.from_metadata().

Complements lingpy_wordlist: this one also captures source citations (good for thesis).
Data: same config/lexibank_data/ directory.
Normalization: none.
"""

from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .base import BaseProvider, FetchResult
from .language_match import lang_key_matches


class PycldfProvider(BaseProvider):
    name = "pycldf"

    def __init__(self) -> None:
        self._data_dir = (
            Path(__file__).resolve().parents[3] / "config" / "lexibank_data"
        )

    def _find_metadata_files(self) -> List[Path]:
        if not self._data_dir.exists():
            return []
        return sorted(self._data_dir.glob("**/cldf/*-metadata.json"))

    def _iso_fragments(self, iso: str) -> List[str]:
        frags: Dict[str, List[str]] = {
            "ar": ["arb", "ara", "ar", "arabic", "stan1318"],
            "fa": ["pes", "fas", "fa", "persian", "farsi", "west2369"],
            "ckb": ["ckb", "sorani", "centralkurdish", "kur"],
            "kmr": ["kmr", "kurmanji", "northernkurdish"],
            "tr": ["tur", "tr", "turkish", "nucl1301"],
            "heb": ["heb", "he", "hebrew"],
            "syr": ["syr", "syriac"],
            "urd": ["urd", "ur", "urdu"],
        }
        return frags.get(iso, [iso])

    def _match_concept_key(self, concept_en: str, keys) -> Optional[str]:
        c = concept_en.lower().strip()
        keys_lower = [(k.lower(), k) for k in keys]
        # exact
        for kl, k in keys_lower:
            if kl == c:
                return k
        # prefix
        for kl, k in keys_lower:
            if kl.startswith(c + " ") or kl.startswith(c + "("):
                return k
        for kl, k in keys_lower:
            if c.startswith(kl):
                return k
        return None

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        try:
            import pycldf  # type: ignore
        except ImportError:
            return

        metadata_files = self._find_metadata_files()
        if not metadata_files:
            return

        for lang_code in language_codes:
            frags = self._iso_fragments(lang_code)

            for concept_en in concepts:
                all_forms: List[str] = []

                for mf in metadata_files:
                    try:
                        ds = pycldf.Dataset.from_metadata(str(mf))
                    except Exception:
                        continue

                    # Build lang_id set from languages table
                    try:
                        langs_table = ds.get("LanguageTable") or ds.get("languages.csv")
                        if langs_table is None:
                            continue
                        matched_lang_ids = set()
                        for row in langs_table:
                            row_id = str(row.get("ID") or row.get("Language_ID") or "")
                            row_name = str(row.get("Name") or "")
                            row_glottocode = str(row.get("Glottocode") or "")
                            if (
                                lang_key_matches(row_id, frags)
                                or lang_key_matches(row_name, frags)
                                or lang_key_matches(row_glottocode, frags)
                            ):
                                lid = row.get("ID") or row.get("Language_ID") or ""
                                if lid:
                                    matched_lang_ids.add(str(lid))
                        if not matched_lang_ids:
                            continue

                        # Build param_id from parameters table
                        params_table = ds.get("ParameterTable") or ds.get("parameters.csv")
                        if params_table is None:
                            continue
                        param_names = {
                            str(row.get("ID") or ""): str(row.get("Name") or row.get("Concepticon_Gloss") or "")
                            for row in params_table
                        }
                        matched_param_key = self._match_concept_key(concept_en, param_names.values())
                        if matched_param_key is None:
                            continue
                        matched_param_ids = {
                            pid for pid, pname in param_names.items()
                            if pname == matched_param_key
                        }

                        # Scan forms
                        forms_table = ds.get("FormTable") or ds.get("forms.csv")
                        if forms_table is None:
                            continue
                        for row in forms_table:
                            lid = str(row.get("Language_ID") or "")
                            pid = str(row.get("Parameter_ID") or "")
                            if lid not in matched_lang_ids or pid not in matched_param_ids:
                                continue
                            form = str(row.get("Form") or row.get("Value") or "").strip()
                            if form and form not in ("-", "0") and form not in all_forms:
                                all_forms.append(form)

                    except Exception as e:
                        import sys
                        print(f"[pycldf] dataset {mf.parent.parent.name} error: {e}", file=sys.stderr)
                        continue

                yield FetchResult(
                    concept_en=concept_en,
                    language_code=lang_code,
                    forms=all_forms[:3],
                    source="pycldf",
                )
