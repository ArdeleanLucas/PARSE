"""CSV override provider — reads config/contact_forms_override.csv if it exists."""

import csv
from pathlib import Path
from typing import Dict, Iterator, List

from .base import BaseProvider, FetchResult

_OVERRIDE_PATH = Path(__file__).resolve().parents[3] / "config" / "contact_forms_override.csv"


class CsvOverrideProvider(BaseProvider):
    name = "csv_override"

    def fetch(
        self,
        concepts: List[str],
        language_codes: List[str],
        language_meta: Dict,
    ) -> Iterator[FetchResult]:
        if not _OVERRIDE_PATH.exists():
            return

        with open(_OVERRIDE_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        concept_set = set(concepts)
        lang_set = set(language_codes)

        for row in rows:
            concept_en = (row.get("concept_en") or "").strip()
            if not concept_en or concept_en not in concept_set:
                continue
            for lang_code in lang_set:
                cell = (row.get(lang_code) or "").strip()
                if not cell:
                    continue
                forms = [f.strip() for f in cell.split(",") if f.strip()]
                if forms:
                    yield FetchResult(
                        concept_en=concept_en,
                        language_code=lang_code,
                        forms=forms,
                        source="csv_override",
                    )
