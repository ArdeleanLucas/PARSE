"""CLDF provider — fetches forms from Lexibank CLDF datasets on GitHub."""

import csv
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import requests

from .base import BaseProvider, FetchResult

_CACHE_DIR = Path(__file__).resolve().parents[3] / "config" / "cache"

_CACHE_MAX_AGE_S = 7 * 24 * 3600  # 7 days

CLDF_DATASETS = {
    "northeuralex": {
        "forms_url": "https://raw.githubusercontent.com/lexibank/northeuralex/main/cldf/forms.csv",
        "languages_url": "https://raw.githubusercontent.com/lexibank/northeuralex/main/cldf/languages.csv",
        "parameters_url": "https://raw.githubusercontent.com/lexibank/northeuralex/main/cldf/parameters.csv",
    },
}

CLDF_LANG_MAP = {
    "fa": ["per", "Persian"],
    "tr": ["tur", "Turkish"],
    "ar": ["arb", "Arabic"],
    "ckb": ["ckb", "Sorani"],
}


class CldfProvider(BaseProvider):
    name = "cldf"

    def __init__(self):
        self._indices: Dict[str, Dict] = {}  # dataset -> index

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        for dataset_name, urls in CLDF_DATASETS.items():
            index = self._get_index(dataset_name, urls)
            if index is None:
                continue
            for lang_code in language_codes:
                lang_ids = self._resolve_lang_ids(lang_code, index.get("languages", {}))
                for concept_en in concepts:
                    forms = self._find_forms(concept_en, lang_ids, index)
                    yield FetchResult(
                        concept_en=concept_en,
                        language_code=lang_code,
                        forms=forms,
                        source="cldf",
                    )

    def _get_index(self, dataset_name: str, urls: Dict[str, str]) -> Optional[Dict]:
        if dataset_name in self._indices:
            return self._indices[dataset_name]

        cache_dir = _CACHE_DIR / "cldf_{}".format(dataset_name)
        cache_dir.mkdir(parents=True, exist_ok=True)

        csvs = {}
        for key in ("forms_url", "languages_url", "parameters_url"):
            filename = key.replace("_url", ".csv")
            cached = cache_dir / filename
            if cached.exists() and (time.time() - os.path.getmtime(str(cached))) < _CACHE_MAX_AGE_S:
                try:
                    with open(cached, encoding="utf-8") as f:
                        csvs[key] = f.read()
                    continue
                except OSError:
                    pass
            try:
                resp = requests.get(urls[key], timeout=30)
                if resp.status_code != 200:
                    return None
                csvs[key] = resp.text
                with open(cached, "w", encoding="utf-8") as f:
                    f.write(resp.text)
            except Exception as exc:
                print("[cldf] download failed for {}: {}".format(key, exc), file=sys.stderr)
                return None

        index = self._build_index(csvs)
        self._indices[dataset_name] = index
        return index

    def _build_index(self, csvs: Dict[str, str]) -> Dict:
        # Build language lookup: language_id -> {iso, name}
        languages = {}
        reader = csv.DictReader(io.StringIO(csvs.get("languages_url", "")))
        for row in reader:
            lid = row.get("ID") or row.get("id") or ""
            iso = row.get("ISO639P3code") or row.get("iso") or ""
            name = row.get("Name") or row.get("name") or ""
            languages[lid] = {"iso": iso, "name": name}

        # Build parameter lookup: parameter_id -> concept_name
        parameters = {}
        reader = csv.DictReader(io.StringIO(csvs.get("parameters_url", "")))
        for row in reader:
            pid = row.get("ID") or row.get("id") or ""
            name = row.get("Name") or row.get("name") or row.get("Concepticon_Gloss") or ""
            parameters[pid] = name.lower()

        # Build forms index: language_id -> {concept_lower -> [forms]}
        forms_idx: Dict[str, Dict[str, List[str]]] = {}
        reader = csv.DictReader(io.StringIO(csvs.get("forms_url", "")))
        for row in reader:
            lid = row.get("Language_ID") or row.get("language_id") or ""
            pid = row.get("Parameter_ID") or row.get("parameter_id") or ""
            form = row.get("Form") or row.get("form") or row.get("Value") or ""
            if not form or not lid:
                continue
            concept_name = parameters.get(pid, "")
            if not concept_name:
                continue
            forms_idx.setdefault(lid, {}).setdefault(concept_name, []).append(form)

        return {"languages": languages, "forms": forms_idx}

    def _resolve_lang_ids(self, lang_code: str, languages: Dict) -> List[str]:
        mapping = CLDF_LANG_MAP.get(lang_code, [lang_code])
        ids = []
        for lid, info in languages.items():
            iso = info.get("iso", "")
            name = info.get("name", "")
            for alias in mapping:
                if alias.lower() in (iso.lower(), name.lower(), lid.lower()):
                    ids.append(lid)
                    break
        return ids

    def _find_forms(self, concept_en: str, lang_ids: List[str], index: Dict) -> List[str]:
        forms_idx = index.get("forms", {})
        concept_lower = concept_en.lower()
        forms = []
        for lid in lang_ids:
            lid_forms = forms_idx.get(lid, {})
            # Exact match first
            if concept_lower in lid_forms:
                forms.extend(lid_forms[concept_lower])
            else:
                # Startswith fallback
                for key, vals in lid_forms.items():
                    if key.startswith(concept_lower):
                        forms.extend(vals)
                        break
        return forms
