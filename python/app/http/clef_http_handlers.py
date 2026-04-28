"""Helpers for PARSE CLEF/contact-language HTTP endpoints."""

from __future__ import annotations

import copy
import csv
import fnmatch
import json
import pathlib
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

from .job_observability_handlers import JsonResponseSpec


@dataclass(frozen=True)
class ClefHttpHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


SilConfigLoader = Callable[[pathlib.Path], Dict[str, Any]]
SilConfigWriter = Callable[[pathlib.Path, Dict[str, Any]], None]
NowFactory = Callable[[], datetime]
IterFormsWithSources = Callable[[Any], Iterable[Tuple[str, List[str]]]]
CitationGetter = Callable[[], Dict[str, Dict[str, Any]]]

CLEF_LANGUAGE_BUCKET_KEYS = ("concepts",)
PROVIDER_CACHE_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "asjp": ("asjp_*.json",),
    "cldf": ("cldf_*",),
    "wikidata": ("wikidata_*.json",),
    "wiktionary": ("wiktionary_*.json",),
}


@dataclass(frozen=True)
class ClefClearPlan:
    updated_config: Dict[str, Any]
    summary: Dict[str, Any]
    warnings: List[str]
    cache_targets: List[pathlib.Path]
    needs_write: bool



def _timestamp_z(now_factory: NowFactory) -> str:
    current = now_factory()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")



def _read_concepts_for_coverage(project_root: pathlib.Path) -> List[str]:
    concepts_path = project_root / "concepts.csv"
    try:
        with open(concepts_path, newline="") as handle:
            reader = csv.DictReader(handle)
            return [row.get("concept_en", "").strip() for row in reader if row.get("concept_en")]
    except (OSError, KeyError):
        return []



def _count_concepts_total(project_root: pathlib.Path) -> int:
    concepts_path = project_root / "concepts.csv"
    try:
        with open(concepts_path, newline="") as handle:
            reader = csv.DictReader(handle)
            return sum(1 for row in reader if (row.get("concept_en") or "").strip())
    except OSError:
        return 0



def build_get_contact_lexeme_coverage_response(
    *,
    config_path: pathlib.Path,
    project_root: pathlib.Path,
    load_sil_config_safe: SilConfigLoader,
) -> JsonResponseSpec:
    config = load_sil_config_safe(config_path)
    all_concepts = _read_concepts_for_coverage(project_root)

    languages: Dict[str, Dict[str, Any]] = {}
    for lang_code, lang_data in config.items():
        if not isinstance(lang_code, str) or lang_code.startswith("_"):
            continue
        if not isinstance(lang_data, dict) or "name" not in lang_data:
            continue
        concepts_dict = lang_data.get("concepts", {})
        filled = {concept: value for concept, value in concepts_dict.items() if value}
        empty = [concept for concept in all_concepts if not filled.get(concept)]
        languages[lang_code] = {
            "name": lang_data.get("name", lang_code),
            "total": len(all_concepts),
            "filled": len(filled),
            "empty": len(empty),
            "concepts": filled,
        }

    return JsonResponseSpec(status=HTTPStatus.OK, payload={"languages": languages})



def build_get_clef_config_response(
    *,
    config_path: pathlib.Path,
    project_root: pathlib.Path,
    load_sil_config_safe: SilConfigLoader,
) -> JsonResponseSpec:
    config = load_sil_config_safe(config_path)

    meta_raw = config.get("_meta") if isinstance(config.get("_meta"), dict) else {}
    primary_raw = meta_raw.get("primary_contact_languages") if isinstance(meta_raw, dict) else []
    primary: List[str] = []
    if isinstance(primary_raw, list):
        primary = [str(code).strip().lower() for code in primary_raw if isinstance(code, str) and code.strip()]

    languages: List[Dict[str, Any]] = []
    for code, data in config.items():
        if not isinstance(code, str) or code.startswith("_"):
            continue
        if not isinstance(data, dict):
            continue
        concepts_dict = data.get("concepts", {}) if isinstance(data.get("concepts"), dict) else {}
        languages.append(
            {
                "code": code,
                "name": data.get("name") or code,
                "family": data.get("family") or None,
                "script": data.get("script") or None,
                "filled": sum(1 for value in concepts_dict.values() if value),
                "total": len(concepts_dict),
            }
        )
    languages.sort(key=lambda item: item["code"])

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "configured": bool(primary) and len(languages) > 0,
            "primary_contact_languages": primary,
            "languages": languages,
            "config_path": str(config_path),
            "concepts_csv_exists": (project_root / "concepts.csv").exists(),
            "meta": meta_raw if isinstance(meta_raw, dict) else {},
        },
    )



def build_post_clef_config_response(
    body: Mapping[str, Any],
    *,
    config_path: pathlib.Path,
    load_sil_config_safe: SilConfigLoader,
    write_sil_config: SilConfigWriter,
    now_factory: NowFactory,
) -> JsonResponseSpec:
    primary_raw = body.get("primary_contact_languages", [])
    if not isinstance(primary_raw, list):
        raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "primary_contact_languages must be a list")
    primary = [str(code).strip().lower() for code in primary_raw if isinstance(code, str) and code.strip()]
    if len(primary) > 2:
        raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "Pick at most 2 primary contact languages")

    langs_raw = body.get("languages", [])
    if not isinstance(langs_raw, list):
        raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "languages must be a list")

    clean_langs: Dict[str, Dict[str, Any]] = {}
    for item in langs_raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip().lower()
        if not code or code.startswith("_"):
            continue
        entry: Dict[str, Any] = {
            "name": str(item.get("name") or code),
        }
        family = item.get("family")
        if isinstance(family, str) and family.strip():
            entry["family"] = family.strip()
        script = item.get("script")
        if isinstance(script, str) and script.strip():
            entry["script"] = script.strip()
        clean_langs[code] = entry

    for code in primary:
        clean_langs.setdefault(code, {"name": code})

    try:
        existing = load_sil_config_safe(config_path)

        merged: Dict[str, Any] = {}
        for code, entry in clean_langs.items():
            prev = existing.get(code) if isinstance(existing.get(code), dict) else {}
            prev_concepts = prev.get("concepts") if isinstance(prev.get("concepts"), dict) else {}
            merged[code] = {**entry, "concepts": prev_concepts}

        prev_meta = existing.get("_meta") if isinstance(existing.get("_meta"), dict) else {}
        prev_selections = prev_meta.get("form_selections") if isinstance(prev_meta.get("form_selections"), dict) else None

        new_meta: Dict[str, Any] = {
            "primary_contact_languages": primary,
            "configured_at": _timestamp_z(now_factory),
            "schema_version": 1,
        }
        if prev_selections is not None:
            new_meta["form_selections"] = prev_selections

        merged["_meta"] = new_meta
        write_sil_config(config_path, merged)
    except ClefHttpHandlerError:
        raise
    except Exception as exc:
        raise ClefHttpHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "success": True,
            "config_path": str(config_path),
            "primary_contact_languages": primary,
            "language_count": len(clean_langs),
        },
    )



def build_post_clef_form_selections_response(
    body: Mapping[str, Any],
    *,
    config_path: pathlib.Path,
    load_sil_config_safe: SilConfigLoader,
    write_sil_config: SilConfigWriter,
) -> JsonResponseSpec:
    concept_en = body.get("concept_en")
    if not isinstance(concept_en, str) or not concept_en.strip():
        raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "concept_en must be a non-empty string")
    concept_key = concept_en.strip()

    lang_code_raw = body.get("lang_code")
    if not isinstance(lang_code_raw, str) or not lang_code_raw.strip():
        raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "lang_code must be a non-empty string")
    lang_code = lang_code_raw.strip().lower()
    if lang_code.startswith("_"):
        raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "lang_code must not start with '_'")

    forms_raw = body.get("forms", [])
    if not isinstance(forms_raw, list):
        raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "forms must be a list of strings")
    forms: List[str] = []
    seen: set[str] = set()
    for item in forms_raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        forms.append(text)

    try:
        existing = load_sil_config_safe(config_path)

        meta = existing.get("_meta")
        if not isinstance(meta, dict):
            meta = {}
        selections = meta.get("form_selections")
        if not isinstance(selections, dict):
            selections = {}

        concept_entry = selections.get(concept_key)
        if not isinstance(concept_entry, dict):
            concept_entry = {}

        concept_entry[lang_code] = forms
        selections[concept_key] = concept_entry
        meta["form_selections"] = selections
        existing["_meta"] = meta

        write_sil_config(config_path, existing)
    except ClefHttpHandlerError:
        raise
    except Exception as exc:
        raise ClefHttpHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "success": True,
            "concept_en": concept_key,
            "lang_code": lang_code,
            "forms": forms,
        },
    )



def _require_bool_field(body: Mapping[str, Any], field_name: str, *, default: bool) -> bool:
    if field_name not in body:
        return default
    value = body.get(field_name)
    if isinstance(value, bool):
        return value
    raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "{0} must be a boolean".format(field_name))



def _optional_string_list(
    value: Any,
    *,
    field_name: str,
    lowercase: bool = False,
) -> List[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "{0} must be null or a list of strings".format(field_name))

    normalized: List[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "{0} must be null or a list of strings".format(field_name))
        text = item.strip()
        if not text:
            raise ClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "{0} must be null or a list of strings".format(field_name))
        if lowercase:
            text = text.lower()
        if text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized



def _load_clef_config_object(config_path: pathlib.Path) -> Dict[str, Any]:
    if not config_path.exists():
        return {}

    try:
        with open(config_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise ClefHttpHandlerError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Could not read config/sil_contact_languages.json: {0}".format(exc),
        ) from exc
    except ValueError as exc:
        raise ClefHttpHandlerError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "config/sil_contact_languages.json is not valid JSON: {0}".format(exc),
        ) from exc

    if not isinstance(payload, dict):
        raise ClefHttpHandlerError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "config/sil_contact_languages.json must contain a JSON object",
        )
    return payload



def _count_entry_forms_and_sources(entry: Any) -> Tuple[int, set[str]]:
    from compare.providers.provenance import iter_forms_with_sources

    count = 0
    providers: set[str] = set()
    for _form, sources in iter_forms_with_sources(entry):
        count += 1
        for source in sources:
            text = str(source).strip()
            if text:
                providers.add(text)
    return count, providers



def _matches_requested_scope(
    *,
    language_code: str,
    concept_key: str,
    languages_filter: set[str] | None,
    concepts_filter: set[str] | None,
) -> bool:
    if languages_filter is not None and language_code not in languages_filter:
        return False
    if concepts_filter is not None and concept_key not in concepts_filter:
        return False
    return True



def _collect_clef_cache_targets(cache_dir: pathlib.Path) -> List[pathlib.Path]:
    if not cache_dir.exists() or not cache_dir.is_dir():
        return []

    targets: List[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for child in cache_dir.iterdir():
        for patterns in PROVIDER_CACHE_PATTERNS.values():
            if any(fnmatch.fnmatch(child.name, pattern) for pattern in patterns):
                resolved = child.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    targets.append(child)
                break
    return sorted(targets, key=lambda item: item.name)



def _count_cache_payloads(targets: Sequence[pathlib.Path]) -> int:
    count = 0
    for target in targets:
        if target.is_dir():
            count += sum(1 for child in target.rglob("*") if child.is_file())
        elif target.exists():
            count += 1
    return count



def _remove_cache_payloads(targets: Sequence[pathlib.Path]) -> Tuple[int, List[str]]:
    removed = 0
    warnings: List[str] = []

    for target in targets:
        if not target.exists():
            continue
        try:
            if target.is_dir():
                removed += sum(1 for child in target.rglob("*") if child.is_file())
                shutil.rmtree(target)
            else:
                target.unlink()
                removed += 1
        except OSError as exc:
            warnings.append("Could not remove cache entry {0}: {1}".format(target.name, exc))
    return removed, warnings



def _write_clef_config_json(config_path: pathlib.Path, payload: Dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def _backup_clef_config(config_path: pathlib.Path, now_factory: NowFactory) -> pathlib.Path:
    current = now_factory()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)

    timestamp = current.replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    backup_path = config_path.with_name("{0}.{1}.bak".format(config_path.name, timestamp))
    suffix = 1
    while backup_path.exists():
        backup_path = config_path.with_name("{0}.{1}.{2}.bak".format(config_path.name, timestamp, suffix))
        suffix += 1
    shutil.copy2(config_path, backup_path)
    return backup_path



def _plan_clef_clear(
    config: Dict[str, Any],
    *,
    config_exists: bool,
    languages: Sequence[str] | None,
    concepts: Sequence[str] | None,
    clear_cache: bool,
    cache_dir: pathlib.Path,
) -> ClefClearPlan:
    languages_filter = set(languages) if languages is not None else None
    concepts_filter = set(concepts) if concepts is not None else None
    updated = copy.deepcopy(config)

    languages_affected: set[str] = set()
    concepts_affected: set[str] = set()
    forms_removed = 0
    data_changed = False
    warnings: List[str] = []

    def _record_removal(language_code: str, concept_key: str, entry: Any) -> None:
        nonlocal forms_removed, data_changed
        count, _providers = _count_entry_forms_and_sources(entry)
        forms_removed += count
        languages_affected.add(language_code)
        concepts_affected.add(concept_key)
        data_changed = True

    for raw_language_code, payload in list(updated.items()):
        if not isinstance(raw_language_code, str) or raw_language_code.startswith("_"):
            continue
        if not isinstance(payload, dict):
            continue
        language_code = raw_language_code.strip().lower()
        if languages_filter is not None and language_code not in languages_filter:
            continue

        for bucket_key in CLEF_LANGUAGE_BUCKET_KEYS:
            scoped = payload.get(bucket_key)
            if not isinstance(scoped, dict):
                if bucket_key == "concepts":
                    warnings_message = (
                        "Language {0} has no concepts object in config/sil_contact_languages.json; "
                        "no forms removed for that language."
                    ).format(language_code)
                    if warnings_message not in warnings:
                        warnings.append(warnings_message)
                continue
            for concept_key, entry in list(scoped.items()):
                if not _matches_requested_scope(
                    language_code=language_code,
                    concept_key=concept_key,
                    languages_filter=languages_filter,
                    concepts_filter=concepts_filter,
                ):
                    continue
                _record_removal(language_code, concept_key, entry)
                del scoped[concept_key]

    cache_targets = _collect_clef_cache_targets(cache_dir) if clear_cache else []

    if not config_exists:
        warnings.append("config/sil_contact_languages.json not found; no CLEF reference forms were available to clear.")
    elif forms_removed == 0:
        warnings.append("No CLEF reference forms found in config/sil_contact_languages.json for the requested scope.")

    return ClefClearPlan(
        updated_config=updated,
        summary={
            "languagesAffected": len(languages_affected),
            "conceptsAffected": len(concepts_affected),
            "formsRemoved": forms_removed,
            "cacheFilesRemoved": 0,
        },
        warnings=warnings,
        cache_targets=cache_targets,
        needs_write=bool(data_changed),
    )



def build_post_clef_clear_response(
    body: Mapping[str, Any],
    *,
    config_path: pathlib.Path,
    now_factory: NowFactory,
) -> JsonResponseSpec:
    """POST /api/clef/clear -- clear CLEF reference forms from
    ``config/sil_contact_languages.json``.

    Destructive writes use a backup-before-write strategy: when the config file
    exists, every real (non-dryRun) clear creates a sibling
    ``sil_contact_languages.json.<timestamp>.bak`` snapshot before any optional
    rewrite, even if no forms are removed. This deliberately captures edge cases
    where a user requests a destructive maintenance action against an already
    empty or unexpectedly-shaped CLEF config. Cache cleanup is limited to
    ``config/cache`` and is best-effort per entry.
    """
    dry_run = _require_bool_field(body, "dryRun", default=False)
    clear_cache = _require_bool_field(body, "clearCache", default=False)
    languages = _optional_string_list(body.get("languages"), field_name="languages", lowercase=True)
    concepts = _optional_string_list(body.get("concepts"), field_name="concepts")

    config_exists = config_path.exists()
    config = _load_clef_config_object(config_path)
    plan = _plan_clef_clear(
        config,
        config_exists=config_exists,
        languages=languages,
        concepts=concepts,
        clear_cache=clear_cache,
        cache_dir=config_path.parent / "cache",
    )

    summary = dict(plan.summary)
    warnings = list(plan.warnings)

    if dry_run:
        if clear_cache:
            summary["cacheFilesRemoved"] = _count_cache_payloads(plan.cache_targets)
        return JsonResponseSpec(
            status=HTTPStatus.OK,
            payload={
                "ok": True,
                "dryRun": True,
                "summary": summary,
                "warnings": warnings,
            },
        )

    if config_exists:
        try:
            _backup_clef_config(config_path, now_factory)
        except OSError as exc:
            raise ClefHttpHandlerError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Could not back up config/sil_contact_languages.json: {0}".format(exc),
            ) from exc

    if plan.needs_write:
        try:
            _write_clef_config_json(config_path, plan.updated_config)
        except OSError as exc:
            raise ClefHttpHandlerError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Could not write config/sil_contact_languages.json: {0}".format(exc),
            ) from exc

    if clear_cache:
        removed_count, cache_warnings = _remove_cache_payloads(plan.cache_targets)
        summary["cacheFilesRemoved"] = removed_count
        warnings.extend(cache_warnings)

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "ok": True,
            "dryRun": False,
            "summary": summary,
            "warnings": warnings,
        },
    )



def build_get_clef_catalog_response(
    *,
    project_root: pathlib.Path,
    sil_catalog: Sequence[Mapping[str, Any]],
) -> JsonResponseSpec:
    merged: Dict[str, Dict[str, Any]] = {}
    for entry in sil_catalog:
        code = str(entry.get("code", "")).strip().lower()
        if not code:
            continue
        merged[code] = {key: value for key, value in entry.items() if value is not None}

    extras_path = project_root / "config" / "sil_catalog_extra.json"
    if extras_path.exists():
        try:
            with open(extras_path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            raw = None
        if isinstance(raw, dict):
            raw = raw.get("languages", [])
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code", "")).strip().lower()
                if not code:
                    continue
                merged[code] = {
                    "code": code,
                    "name": str(item.get("name") or code),
                    **({"family": item["family"]} if isinstance(item.get("family"), str) and item["family"].strip() else {}),
                    **({"script": item["script"]} if isinstance(item.get("script"), str) and item["script"].strip() else {}),
                }

    languages = sorted(merged.values(), key=lambda item: item.get("name", item.get("code", "")))
    return JsonResponseSpec(status=HTTPStatus.OK, payload={"languages": languages})



def build_get_clef_providers_response(*, provider_priority: Sequence[str]) -> JsonResponseSpec:
    providers = [{"id": provider_id, "name": provider_id} for provider_id in provider_priority]
    return JsonResponseSpec(status=HTTPStatus.OK, payload={"providers": providers})



def build_get_clef_sources_report_response(
    *,
    config_path: pathlib.Path,
    project_root: pathlib.Path,
    load_sil_config_safe: SilConfigLoader,
    iter_forms_with_sources: IterFormsWithSources,
    get_citations: CitationGetter,
    citation_display_order: Sequence[str],
    now_factory: NowFactory,
) -> JsonResponseSpec:
    config = load_sil_config_safe(config_path)
    all_concepts_total = _count_concepts_total(project_root)

    provider_totals: Dict[str, int] = {}
    languages_out: List[Dict[str, Any]] = []

    for code, data in sorted(config.items()):
        if not isinstance(code, str) or code.startswith("_"):
            continue
        if not isinstance(data, dict):
            continue
        concepts_dict = data.get("concepts") if isinstance(data.get("concepts"), dict) else {}

        forms_out: List[Dict[str, Any]] = []
        per_provider: Dict[str, int] = {}
        concepts_covered = 0
        for concept_en, entry in sorted(concepts_dict.items()):
            any_forms = False
            for form, sources in iter_forms_with_sources(entry):
                any_forms = True
                forms_out.append(
                    {
                        "concept_en": concept_en,
                        "form": form,
                        "sources": list(sources),
                    }
                )
                for source in sources:
                    per_provider[source] = per_provider.get(source, 0) + 1
                    provider_totals[source] = provider_totals.get(source, 0) + 1
            if any_forms:
                concepts_covered += 1

        languages_out.append(
            {
                "code": code,
                "name": data.get("name") or code,
                "family": data.get("family") or None,
                "script": data.get("script") or None,
                "total_forms": len(forms_out),
                "concepts_covered": concepts_covered,
                "concepts_total": all_concepts_total,
                "per_provider": per_provider,
                "forms": forms_out,
            }
        )

    providers_sorted = sorted(
        ({"id": provider_id, "total_forms": count} for provider_id, count in provider_totals.items()),
        key=lambda item: (-item["total_forms"], item["id"]),
    )

    return JsonResponseSpec(
        status=HTTPStatus.OK,
        payload={
            "generated_at": _timestamp_z(now_factory),
            "providers": providers_sorted,
            "languages": languages_out,
            "concepts_total": all_concepts_total,
            "citations": get_citations(),
            "citation_order": list(citation_display_order),
        },
    )
