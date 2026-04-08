"""
contact_lexeme_fetcher.py -- Populate sil_contact_languages.json with contact language forms.

Standalone:
    python compare/contact_lexeme_fetcher.py \
        --concepts ../../concepts.csv \
        --config ../../config/sil_contact_languages.json \
        --languages ar fa ckb \
        --providers grokipedia asjp
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def fetch_and_merge(
    concepts_path: Path,
    config_path: Path,
    language_codes: List[str],
    providers: Optional[List[str]] = None,
    overwrite: bool = False,
    ai_config: Optional[Dict] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, int]:
    """
    Main entry point.
    Returns: {lang_code: count_filled} -- how many concepts got forms per language.
    """
    # 1. Load concepts
    concepts = _load_concepts(concepts_path)

    # 2. Load current config
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    language_meta = {k: v for k, v in config.items() if isinstance(v, dict)}

    # 3. Determine which concepts need filling
    if not overwrite:
        needs_fill = {
            lc: [c for c in concepts if not config.get(lc, {}).get("concepts", {}).get(c)]
            for lc in language_codes
        }
    else:
        needs_fill = {lc: list(concepts) for lc in language_codes}

    # 4. Run registry
    from .providers.registry import ProviderRegistry

    registry = ProviderRegistry(ai_config)
    all_needed = sorted(set(c for cc in needs_fill.values() for c in cc))
    if not all_needed:
        return {lc: 0 for lc in language_codes}

    results = registry.fetch_all(
        concepts=all_needed,
        language_codes=language_codes,
        language_meta=language_meta,
        priority_order=providers,
        progress_callback=progress_callback,
    )

    # 5. Merge results back into config
    filled: Dict[str, int] = {}
    for lc in language_codes:
        lang_entry = config.setdefault(lc, {"name": lc, "concepts": {}})
        concepts_dict = lang_entry.setdefault("concepts", {})
        count = 0
        for concept_en, forms in results.get(lc, {}).items():
            if forms:
                if overwrite or not concepts_dict.get(concept_en):
                    concepts_dict[concept_en] = forms
                    count += 1
        filled[lc] = count

    # 6. Write back
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return filled


def _load_concepts(path: Path) -> List[str]:
    concepts = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            concept_en = (row.get("concept_en") or "").strip()
            if concept_en:
                concepts.append(concept_en)
    return concepts


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate contact language lexemes")
    parser.add_argument("--concepts", required=True, help="Path to concepts.csv")
    parser.add_argument("--config", required=True, help="Path to sil_contact_languages.json")
    parser.add_argument("--languages", nargs="+", help="Language codes (default: all in config)")
    parser.add_argument("--providers", nargs="+", help="Provider names in priority order")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing forms")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not args.languages:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        lang_codes = [k for k, v in cfg.items() if isinstance(v, dict) and "name" in v]
    else:
        lang_codes = args.languages

    def _progress(pct: float, msg: str) -> None:
        print("[{:.0f}%] {}".format(pct, msg))

    filled = fetch_and_merge(
        concepts_path=Path(args.concepts),
        config_path=config_path,
        language_codes=lang_codes,
        providers=args.providers,
        overwrite=args.overwrite,
        progress_callback=_progress,
    )

    for lc, count in filled.items():
        print("{}: {} concepts filled".format(lc, count))


if __name__ == "__main__":
    main()
