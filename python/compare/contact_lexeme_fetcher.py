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

    # 2. Load current config (create empty on first run)
    config = _load_or_init_config(config_path)

    # Underscore-prefixed top-level keys (e.g. "_meta") are metadata, not
    # languages -- skip them when building the provider-facing map.
    language_meta = {
        k: v for k, v in config.items()
        if isinstance(v, dict) and isinstance(k, str) and not k.startswith("_")
    }

    if not language_codes:
        raise ValueError(
            "No contact languages configured. Open the CLEF configure modal "
            "(Compute -> Borrowing detection (CLEF)) to pick at least one."
        )
    if not concepts:
        raise ValueError(
            "No concepts found. Import concepts.csv before running CLEF."
        )

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
    if not path.exists():
        return []
    concepts = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            concept_en = (row.get("concept_en") or "").strip()
            if concept_en:
                concepts.append(concept_en)
    return concepts


def _load_or_init_config(path: Path) -> Dict[str, Any]:
    """Load the SIL contact-language config, creating an empty file on first
    access. A missing file previously crashed the fetch with ``[Errno 2]``;
    the CLEF configure flow in the UI writes a real config, but the compute
    path must still cope with a freshly-initialised workspace where the
    user has not yet opened the configure modal."""
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f)
        except OSError:
            return {}
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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
