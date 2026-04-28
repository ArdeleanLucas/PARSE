"""
contact_lexeme_fetcher.py -- Populate sil_contact_languages.json with contact language forms.

Standalone:
    python compare/contact_lexeme_fetcher.py \
        --concepts ../../concepts.csv \
        --config ../../config/sil_contact_languages.json \
        --languages ar fa ckb \
        --providers grok_llm asjp
"""

import argparse
import csv
import json
import os
import sys
import tempfile
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
    return_report: bool = False,
) -> Dict[str, Any]:
    """
    Main entry point.

    Default return shape: ``{lang_code: count_filled}``.

    When ``return_report=True`` the fetcher returns a richer dict with the
    per-language counts under ``filled`` plus machine-readable CLEF
    diagnostics (status, warnings, provider_errors, provider stats). The
    server route uses that richer path so the UI can distinguish
    ``ok`` / ``no_forms`` / ``provider_error`` instead of treating a
    zero-form populate as a plain success.
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
            "No concepts found at {0}. Import concepts.csv before running CLEF.".format(concepts_path)
        )

    print(
        "[clef] fetch_and_merge start: concepts={0} langs={1} providers={2} overwrite={3} config={4}".format(
            len(concepts), language_codes, providers or "<all>", overwrite, config_path,
        ),
        file=sys.stderr,
    )

    # 3. Determine which concepts need filling.
    # "Has forms" must recognise BOTH the legacy bare-list shape
    # (``["ma:ʔ"]``) and the new provenance shape
    # (``[{"form": "ma:ʔ", "sources": [...]}]``). A concept is filled
    # if its list is truthy and contains at least one non-empty entry.
    if not overwrite:
        needs_fill = {
            lc: [
                c for c in concepts
                if not _entry_has_forms(config.get(lc, {}).get("concepts", {}).get(c))
            ]
            for lc in language_codes
        }
    else:
        needs_fill = {lc: list(concepts) for lc in language_codes}

    # 4. Run registry
    from .providers.registry import PROVIDER_PRIORITY, ProviderRegistry

    registry = ProviderRegistry(ai_config)
    all_needed = sorted(set(c for cc in needs_fill.values() for c in cc))
    if not all_needed:
        filled = {lc: 0 for lc in language_codes}
        if return_report:
            return {
                "status": "no_forms",
                "filled": filled,
                "forms_count": 0,
                "total_filled": 0,
                "requested_concepts": [],
                "requested_concepts_count": 0,
                "providers_requested": list(providers or PROVIDER_PRIORITY),
                "providers_attempted": [],
                "providers_returning_forms": [],
                "provider_errors": [],
                "warnings": [
                    "All requested concepts already have reference forms; nothing needed to be fetched."
                ],
                "provider_stats": {},
                "config_path": str(config_path),
            }
        return filled

    if return_report:
        registry_payload = registry.fetch_all_detailed(
            concepts=all_needed,
            language_codes=language_codes,
            language_meta=language_meta,
            priority_order=providers,
            progress_callback=progress_callback,
        )
        results = registry_payload.get("results", {})
        provider_errors = list(registry_payload.get("provider_errors", []))
        warnings = list(registry_payload.get("warnings", []))
        providers_requested = list(registry_payload.get("providers_requested", providers or PROVIDER_PRIORITY))
        providers_attempted = list(registry_payload.get("providers_attempted", []))
        providers_returning_forms = list(registry_payload.get("providers_returning_forms", []))
        provider_stats = registry_payload.get("provider_stats", {})
    else:
        results = registry.fetch_all(
            concepts=all_needed,
            language_codes=language_codes,
            language_meta=language_meta,
            priority_order=providers,
            progress_callback=progress_callback,
        )
        provider_errors = []
        warnings = []
        providers_requested = list(providers or PROVIDER_PRIORITY)
        providers_attempted = []
        providers_returning_forms = []
        provider_stats = {}

    # 5. Merge results back into config.
    # The registry now emits ``[{"form": str, "sources": [...]}]`` entries.
    # We write that shape directly; any pre-existing bare-list data in
    # untouched concepts is left exactly as it was (no forced migration,
    # so callers can roll the feature forward without re-populating the
    # entire corpus).
    filled: Dict[str, int] = {}
    for lc in language_codes:
        lang_entry = config.setdefault(lc, {"name": lc, "concepts": {}})
        if not isinstance(lang_entry, dict):
            lang_entry = {"name": lc, "concepts": {}}
            config[lc] = lang_entry
        concepts_dict = lang_entry.setdefault("concepts", {})
        if not isinstance(concepts_dict, dict):
            concepts_dict = {}
            lang_entry["concepts"] = concepts_dict
        count = 0
        for concept_en, forms in results.get(lc, {}).items():
            if forms:
                if overwrite or not _entry_has_forms(concepts_dict.get(concept_en)):
                    concepts_dict[concept_en] = forms
                    count += 1
        filled[lc] = count

    # 6. Atomic write + post-write verification. A torn write (crash
    # mid-flush) previously left the file empty and silently wiped the
    # user's `_meta.primary_contact_languages`, so CLEF appeared
    # "configured but unpopulated" with no recovery path. tempfile +
    # os.replace gives us crash-safe durability; we then re-read the
    # file and assert every requested language code is present so we
    # fail loudly if the disk didn't accept what we wrote.
    _atomic_write_json(config_path, config)
    _verify_written_config(config_path, language_codes)

    total_filled = sum(filled.values())
    print(
        "[clef] fetch_and_merge done: total_filled={0} per_lang={1} file={2}".format(
            total_filled, filled, config_path,
        ),
        file=sys.stderr,
    )

    if not return_report:
        return filled

    status = "ok" if total_filled > 0 else ("provider_error" if provider_errors else "no_forms")
    if total_filled == 0 and not warnings:
        warnings = [
            "No provider returned forms for the remaining concept/language pairs."
        ]

    return {
        "status": status,
        "filled": filled,
        "forms_count": total_filled,
        "total_filled": total_filled,
        "requested_concepts": list(all_needed),
        "requested_concepts_count": len(all_needed),
        "providers_requested": providers_requested,
        "providers_attempted": providers_attempted,
        "providers_returning_forms": providers_returning_forms,
        "provider_errors": provider_errors,
        "warnings": warnings,
        "provider_stats": provider_stats,
        "config_path": str(config_path),
    }


def _entry_has_forms(entry: Any) -> bool:
    """Return True if ``entry`` represents one or more non-empty forms
    under EITHER the legacy bare-list shape (``["ma:ʔ"]``) OR the new
    provenance shape (``[{"form": "ma:ʔ", "sources": [...]}]``). Thin
    wrapper so callers don't need to reach into the providers package."""
    from .providers.provenance import entry_has_forms
    return entry_has_forms(entry)


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                # fsync is best-effort on some platforms (e.g. tmpfs);
                # os.replace below is still atomic w.r.t. the visible
                # filename, which is what readers care about.
                pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _verify_written_config(path: Path, language_codes: List[str]) -> None:
    try:
        with open(path, encoding="utf-8") as handle:
            roundtrip = json.load(handle)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "Wrote {0} but could not re-read it: {1}".format(path, exc)
        )
    if not isinstance(roundtrip, dict):
        raise RuntimeError(
            "Wrote {0} but its contents are not a JSON object".format(path)
        )
    missing = [lc for lc in language_codes if not isinstance(roundtrip.get(lc), dict)]
    if missing:
        raise RuntimeError(
            "Wrote {0} but languages missing after write: {1}".format(path, missing)
        )


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
