from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Iterator


@dataclass
class FetchResult:
    concept_en: str          # e.g. "water"
    language_code: str       # e.g. "ar"
    forms: List[str]         # raw forms from source, verbatim
    source: str              # provider name: "asjp", "grok_llm", etc.
    error: Optional[str] = None


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(
        self,
        concepts: List[str],       # English concept labels from concepts.csv
        language_codes: List[str],  # e.g. ["ar", "fa"]
        language_meta: Dict,        # from sil_contact_languages.json top-level
    ) -> Iterator[FetchResult]:
        """Yield one FetchResult per concept x language combination."""
