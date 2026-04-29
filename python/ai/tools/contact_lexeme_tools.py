from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..chat_tools import (
    ChatToolSpec,
    _read_json_file,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


CONTACT_LEXEME_TOOL_NAMES = (
    "contact_lexeme_lookup",
    "clef_clear_data",
)


CONTACT_LEXEME_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "contact_lexeme_lookup": ChatToolSpec(
                    name="contact_lexeme_lookup",
                    description=(
                        "Fetch reference forms (IPA transcriptions) for contact/comparison languages "
                        "from third-party sources (local CLDF, ASJP, Wikidata, Wiktionary, Grok LLM, "
                        "literature). Gated by dryRun: pass dryRun=true FIRST to preview what would be "
                        "fetched without touching sil_contact_languages.json, then dryRun=false after "
                        "the user confirms — only the second call writes. maxConcepts caps the sample "
                        "size per call for bounded previews."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["dryRun"],
                        "properties": {
                            "languages": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 10,
                                "items": {"type": "string", "minLength": 1, "maxLength": 16},
                                "description": "ISO 639 language codes, e.g. [\"ar\", \"fa\", \"ckb\"]",
                            },
                            "conceptIds": {
                                "type": "array",
                                "maxItems": 100,
                                "items": {"type": "string", "minLength": 1, "maxLength": 100},
                                "description": "Project concept IDs or English concept labels to look up. Defaults to all project concepts.",
                            },
                            "providers": {
                                "type": "array",
                                "maxItems": 10,
                                "items": {
                                    "type": "string",
                                    "enum": [
                                        "csv_override", "lingpy_wordlist", "pycldf", "pylexibank",
                                        "asjp", "cldf", "wikidata", "wiktionary", "grok_llm", "literature",
                                    ],
                                },
                                "description": "Provider priority order. Defaults to full chain.",
                            },
                            "dryRun": {
                                "type": "boolean",
                                "description": "If true, preview only — fetches via the provider registry but does NOT write to sil_contact_languages.json. If false, merges results and writes. Required.",
                            },
                            "maxConcepts": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 200,
                                "description": "Cap on concepts processed this call. Useful for bounded previews.",
                            },
                            "overwrite": {
                                "type": "boolean",
                                "description": "If true and dryRun is false, re-fetch even if forms already exist. Ignored when dryRun is true.",
                            },
                        },
                    },
                ),
    "clef_clear_data": ChatToolSpec(
                    name="clef_clear_data",
                    description=(
                        "Clear CLEF-populated reference forms from config/sil_contact_languages.json. "
                        "Supports dryRun preview, optional language/concept scoping, and optional provider-cache cleanup. "
                        "Use dryRun=true first before destructive clears."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "dryRun": {
                                "type": "boolean",
                                "description": "If true, preview the number of forms, languages, concepts, and cache entries that would be cleared without writing anything. Defaults to false.",
                            },
                            "languages": {
                                "type": ["array", "null"],
                                "items": {"type": "string", "minLength": 1, "maxLength": 16},
                                "maxItems": 50,
                                "description": "Optional list of language codes to clear. Omit or pass null to clear all configured languages.",
                            },
                            "concepts": {
                                "type": ["array", "null"],
                                "items": {"type": "string", "minLength": 1, "maxLength": 200},
                                "maxItems": 500,
                                "description": "Optional list of concept labels to clear. Omit or pass null to clear all concepts.",
                            },
                            "clearCache": {
                                "type": "boolean",
                                "description": "If true, also remove known CLEF provider caches under config/cache.",
                            },
                        },
                    },
                ),
}


def contact_lexeme_lookup(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch reference forms for contact languages via the provider registry.

        dryRun controls write behavior:
          dryRun=true  → call ProviderRegistry.fetch_all directly; no filesystem
                         writes; returns a preview of what would be merged.
          dryRun=false → call fetch_and_merge; writes results to
                         sil_contact_languages.json.
        """
        dry_run = bool(args.get("dryRun"))

        try:
            from compare.contact_lexeme_fetcher import fetch_and_merge
        except ImportError:
            return {
                "readOnly": True,
                "status": "unavailable",
                "message": (
                    "compare.contact_lexeme_fetcher module is unavailable. "
                    "Ensure the compare package is importable."
                ),
            }

        concepts_path = tools.project_root / "concepts.csv"
        if not concepts_path.exists():
            return {
                "ok": False,
                "error": "concepts.csv not found in project root. Import concepts first.",
            }

        config_path = tools.sil_config_path
        if not config_path.exists():
            # Create minimal config so fetch_and_merge can proceed
            import json as _json
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                _json.dump({}, f)

        # Parse arguments
        languages_raw = args.get("languages")
        if isinstance(languages_raw, list) and languages_raw:
            languages = [str(lc).strip().lower() for lc in languages_raw if str(lc).strip()]
        else:
            # Default: read configured languages from sil_contact_languages.json
            import json as _json
            try:
                with open(config_path, encoding="utf-8") as f:
                    sil_config = _json.load(f)
                languages = [k for k, v in sil_config.items() if isinstance(v, dict) and "name" in v]
            except Exception:
                languages = []
            if not languages:
                return {
                    "ok": False,
                    "error": (
                        "No languages specified and none configured in sil_contact_languages.json. "
                        "Provide languages parameter, e.g. [\"ar\", \"fa\"]."
                    ),
                }

        providers_raw = args.get("providers")
        providers = None
        if isinstance(providers_raw, list) and providers_raw:
            providers = [str(p).strip() for p in providers_raw if str(p).strip()]

        overwrite = bool(args.get("overwrite", False))
        max_concepts_raw = args.get("maxConcepts")
        max_concepts: Optional[int] = None
        if isinstance(max_concepts_raw, int) and max_concepts_raw > 0:
            max_concepts = max_concepts_raw

        # Concept filter
        concept_ids_raw = args.get("conceptIds")
        concept_filter = None
        if isinstance(concept_ids_raw, list) and concept_ids_raw:
            project_concepts = load_project_concepts(tools)
            label_by_id = {
                str(concept.get("id") or "").strip(): str(concept.get("label") or "").strip()
                for concept in project_concepts
                if str(concept.get("id") or "").strip() and str(concept.get("label") or "").strip()
            }
            label_by_label = {
                str(concept.get("label") or "").strip().lower(): str(concept.get("label") or "").strip()
                for concept in project_concepts
                if str(concept.get("label") or "").strip()
            }
            concept_filter = []
            for raw_concept in concept_ids_raw:
                token = str(raw_concept).strip()
                if not token:
                    continue
                concept_label = label_by_id.get(token) or label_by_label.get(token.lower()) or token
                if concept_label not in concept_filter:
                    concept_filter.append(concept_label)

        if concept_filter is not None and max_concepts is not None:
            concept_filter = concept_filter[:max_concepts]

        # Load ai_config for provider credentials (grok_llm needs API keys)
        ai_config = _read_json_file(tools.config_path, {})

        # If concept filter is given, write a temporary concepts CSV with only those
        import tempfile
        import csv as _csv
        if concept_filter:
            tmp_concepts = Path(tempfile.mktemp(suffix=".csv"))
            try:
                with open(tmp_concepts, "w", newline="", encoding="utf-8") as f:
                    writer = _csv.DictWriter(f, fieldnames=["id", "concept_en"])
                    writer.writeheader()
                    for i, c in enumerate(concept_filter, 1):
                        writer.writerow({"id": str(i), "concept_en": c})
                effective_concepts_path = tmp_concepts
            except Exception:
                effective_concepts_path = concepts_path
                concept_filter = None
        else:
            effective_concepts_path = concepts_path
            tmp_concepts = None

        try:
            if dry_run:
                # Preview path — load sil_config for language_meta, call the provider
                # registry directly, never touch the filesystem. Imported lazily here
                # (not at the top of the handler) because the provider registry pulls
                # in optional deps like pycldf/pylexibank that the write path doesn't
                # need — hoisting it would regress write-path availability when those
                # deps are missing.
                try:
                    from compare.providers.registry import ProviderRegistry, PROVIDER_PRIORITY
                except ImportError as exc:
                    return {
                        "ok": False,
                        "error": (
                            "Provider registry unavailable for dryRun preview: {0}. "
                            "Re-run with dryRun=false to fall back to fetch_and_merge."
                        ).format(exc),
                    }
                import csv as _csv_preview
                import json as _json_preview
                try:
                    with open(config_path, encoding="utf-8") as f:
                        sil_config_preview = _json_preview.load(f)
                except Exception:
                    sil_config_preview = {}
                language_meta = {k: v for k, v in sil_config_preview.items() if isinstance(v, dict)}

                with open(effective_concepts_path, newline="", encoding="utf-8") as f:
                    reader = _csv_preview.DictReader(f)
                    preview_concepts = [
                        (row.get("concept_en") or "").strip()
                        for row in reader
                        if (row.get("concept_en") or "").strip()
                    ]
                if max_concepts is not None:
                    preview_concepts = preview_concepts[:max_concepts]

                registry = ProviderRegistry(ai_config if isinstance(ai_config, dict) else {})
                fetched = registry.fetch_all(
                    concepts=preview_concepts,
                    language_codes=languages,
                    language_meta=language_meta,
                    priority_order=providers,
                )
                filled = {
                    lc: sum(1 for forms in fetched.get(lc, {}).values() if forms)
                    for lc in languages
                }

                sample_forms: Dict[str, Dict[str, List[str]]] = {}
                for lc in languages:
                    sample: Dict[str, List[str]] = {}
                    for concept_en, forms in list(fetched.get(lc, {}).items())[:5]:
                        if forms:
                            sample[concept_en] = forms
                    sample_forms[lc] = sample

                return {
                    "ok": True,
                    "dryRun": True,
                    "readOnly": True,
                    "previewOnly": True,
                    "languages": languages,
                    "filled": filled,
                    "totalConceptsFetched": sum(filled.values()),
                    "providersUsed": providers or list(PROVIDER_PRIORITY),
                    "sampleForms": sample_forms,
                    "message": (
                        "DRY RUN — fetched reference forms for {0} language(s); "
                        "no writes to sil_contact_languages.json. "
                        "Re-run with dryRun=false to persist these results."
                    ).format(len(languages)),
                }

            filled = fetch_and_merge(
                concepts_path=effective_concepts_path,
                config_path=config_path,
                language_codes=languages,
                providers=providers,
                overwrite=overwrite,
                ai_config=ai_config if isinstance(ai_config, dict) else {},
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": "Contact lexeme fetch failed: {0}".format(exc),
            }
        finally:
            if tmp_concepts and tmp_concepts.exists():
                try:
                    tmp_concepts.unlink()
                except Exception:
                    pass

        # Read back what was fetched to provide a summary
        import json as _json
        try:
            with open(config_path, encoding="utf-8") as f:
                updated_config = _json.load(f)
        except Exception:
            updated_config = {}

        sample_forms = {}
        for lc in languages:
            lang_data = updated_config.get(lc, {})
            concepts_data = lang_data.get("concepts", {})
            sample = {}
            for concept_en, forms in list(concepts_data.items())[:5]:
                sample[concept_en] = forms if isinstance(forms, list) else []
            sample_forms[lc] = sample

        return {
            "ok": True,
            "dryRun": False,
            "readOnly": False,
            "previewOnly": False,
            "languages": languages,
            "filled": filled,
            "totalConceptsFetched": sum(filled.values()),
            "providersUsed": providers or [
                "csv_override", "lingpy_wordlist", "pycldf", "pylexibank",
                "asjp", "cldf", "wikidata", "wiktionary", "grok_llm", "literature",
            ],
            "overwrite": overwrite,
            "configPath": str(config_path),
            "sampleForms": sample_forms,
            "message": (
                "Fetched reference forms for {0} language(s). "
                "Total concepts filled: {1}. "
                "Results written to sil_contact_languages.json. "
                "Use cognate_compute_preview with contactLanguages to compare."
            ).format(len(languages), sum(filled.values())),
        }


def clef_clear_data(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Clear CLEF reference forms and optional provider caches.

        Delegates to the HTTP handler logic so HTTP, chat, and MCP stay on one
        contract for validation, dry-run semantics, summaries, and backup
        behavior.
        """
        from datetime import datetime, timezone
        from app.http.clef_http_handlers import (
            ClefHttpHandlerError,
            build_post_clef_clear_response,
        )

        body: Dict[str, Any] = {"dryRun": bool(args.get("dryRun", False))}
        if "languages" in args:
            body["languages"] = args.get("languages")
        if "concepts" in args:
            body["concepts"] = args.get("concepts")
        if "clearCache" in args:
            body["clearCache"] = args.get("clearCache")

        try:
            response = build_post_clef_clear_response(
                body,
                config_path=tools.sil_config_path,
                now_factory=lambda: datetime.now(timezone.utc),
            )
        except ClefHttpHandlerError as exc:
            return {
                "ok": False,
                "status": int(exc.status),
                "error": exc.message,
            }

        return dict(response.payload)


def load_project_concepts(tools: "ParseChatTools") -> List[Dict[str, Any]]:
    """Load project concepts from concepts.csv. Returns list of {id, label} dicts."""
    concepts_path = tools.project_root / "concepts.csv"
    if not concepts_path.exists():
        return []
    import csv as _csv

    concepts: List[Dict[str, Any]] = []
    try:
        with open(concepts_path, newline="", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                cid = str(row.get("id") or "").strip()
                label = str(row.get("concept_en") or "").strip()
                if cid and label:
                    concepts.append({"id": cid, "label": label})
    except Exception:
        pass
    return concepts


CONTACT_LEXEME_TOOL_HANDLERS = {
    "contact_lexeme_lookup": contact_lexeme_lookup,
    "clef_clear_data": clef_clear_data,
}


__all__ = [
    "CONTACT_LEXEME_TOOL_NAMES",
    "CONTACT_LEXEME_TOOL_SPECS",
    "CONTACT_LEXEME_TOOL_HANDLERS",
    "load_project_concepts",
    "contact_lexeme_lookup",
    "clef_clear_data",
]
