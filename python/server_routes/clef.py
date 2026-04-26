"""PARSE server route-domain module: clef."""
from __future__ import annotations

import server as _server

def _compute_contact_lexemes(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Fetch and merge contact language lexeme forms into sil_contact_languages.json."""
    from compare.contact_lexeme_fetcher import fetch_and_merge
    concepts_path = _server._project_root() / 'concepts.csv'
    config_path = _server._sil_config_path()
    providers = _server._coerce_string_list(payload.get('providers')) or None
    languages_raw = _server._coerce_string_list(payload.get('languages'))
    if not languages_raw:
        sil_config = _server._load_sil_config_safe(config_path)
        meta = sil_config.get('_meta') if isinstance(sil_config.get('_meta'), dict) else {}
        primary = meta.get('primary_contact_languages') if isinstance(meta, dict) else None
        if isinstance(primary, list) and primary:
            languages_raw = [str(c).strip().lower() for c in primary if isinstance(c, str) and c.strip()]
        if not languages_raw:
            languages_raw = [k for k, v in sil_config.items() if isinstance(v, dict) and 'name' in v and isinstance(k, str) and (not k.startswith('_'))]
    overwrite = bool(payload.get('overwrite', False))

    def _progress(pct: float, msg: str) -> None:
        _server._set_job_progress(job_id, pct * 0.9, message=msg)
    try:
        ai_config_path = _server._project_root() / 'config' / 'ai_config.json'
        import json as _json2
        with open(ai_config_path) as f:
            ai_config = _json2.load(f)
    except Exception:
        ai_config = {}
    _server._set_job_progress(job_id, 5.0, message='Starting contact lexeme fetch')
    filled = fetch_and_merge(concepts_path=concepts_path, config_path=config_path, language_codes=languages_raw, providers=providers, overwrite=overwrite, ai_config=ai_config, progress_callback=_progress)
    _server._set_job_progress(job_id, 100.0, message='Done')
    total_filled = sum(filled.values())
    result: _server.Dict[str, _server.Any] = {'filled': filled, 'total_filled': total_filled, 'languages_requested': list(languages_raw), 'providers_requested': providers or 'all', 'config_path': str(config_path)}
    if total_filled == 0:
        result['warning'] = 'Populate finished with 0 reference forms. Try 1: check your internet connection — wikidata, wiktionary, asjp, cldf, and grokipedia all need network. Try 2: open the CLEF configure modal and enable more providers (or leave the list empty to try all built-in providers). Other causes: grokipedia needs an xAI API key; lingpy_wordlist and pycldf need local CLDF datasets under config/lexibank_data/; ASJP only covers 40 Swadesh concepts, so glosses outside that list return nothing from it. Backend stderr has per-provider errors.'
        print('[clef] {0}'.format(result['warning']), file=_server.sys.stderr)
    return result

def _api_get_contact_lexeme_coverage(self) -> None:
    """Return coverage stats for contact language lexeme data."""
    try:
        response = _server._app_build_get_contact_lexeme_coverage_response(config_path=_server._sil_config_path(), project_root=_server._project_root(), load_sil_config_safe=_server._load_sil_config_safe)
    except _server._app_ClefHttpHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_clef_config(self) -> None:
    """Return the current CLEF configuration + readiness state. The UI's
    configure modal reads this to decide whether to prompt the user
    before running Borrowing detection."""
    try:
        response = _server._app_build_get_clef_config_response(config_path=_server._sil_config_path(), project_root=_server._project_root(), load_sil_config_safe=_server._load_sil_config_safe)
    except _server._app_ClefHttpHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_clef_config(self) -> None:
    """Create/update the SIL contact-language config. Accepts:
        {
          "primary_contact_languages": ["eng", "spa"],
          "languages": [
            {"code": "eng", "name": "English", "family": "Germanic"},
            ...
          ]
        }
    Merges with any existing per-language concepts data -- populated
    forms are never dropped when the user re-saves the config."""
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_clef_config_response(body, config_path=_server._sil_config_path(), load_sil_config_safe=_server._load_sil_config_safe, write_sil_config=_server._write_sil_config, now_factory=lambda: _server.datetime.now(_server.timezone.utc))
    except _server._app_ClefHttpHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_clef_form_selections(self) -> None:
    """Persist which reference forms the user has selected for a given
    (concept, language) into ``_meta.form_selections`` in the SIL
    contact-language config.

    Request body:
        {
          "concept_en": "water",
          "lang_code": "ar",
          "forms": ["ماء", "maːʔ"]
        }

    Semantics downstream (honoured by future compute work, not this PR):
        - missing entry        → all populated forms are used (default)
        - empty ``forms`` list → none selected, similarity skipped
        - subset               → only listed forms contribute

    Selections are keyed by exact form string so the persisted choice
    survives re-population that preserves the same raw text. Adding or
    removing a concept/language from the config does not touch
    selections -- they stay keyed by English concept label + ISO code.
    """
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_clef_form_selections_response(body, config_path=_server._sil_config_path(), load_sil_config_safe=_server._load_sil_config_safe, write_sil_config=_server._write_sil_config)
    except _server._app_ClefHttpHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_clef_catalog(self) -> None:
    """Return the bundled SIL/ISO language catalog the configure modal
    uses for its searchable picker. Kept server-side so we can extend
    it without reshipping the frontend bundle.

    Merges a per-workspace override file at
    ``config/sil_catalog_extra.json`` on top of the bundled list, so
    users can add private entries without editing the repo. The extras
    file may be a bare list or ``{"languages": [...]}``; duplicate
    codes in the extras replace the bundled entry."""
    from compare.sil_catalog import SIL_CATALOG
    try:
        response = _server._app_build_get_clef_catalog_response(project_root=_server._project_root(), sil_catalog=SIL_CATALOG)
    except _server._app_ClefHttpHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_clef_providers(self) -> None:
    """Return the list of CLEF providers in priority order -- drives
    the provider-selection checkboxes in the configure modal."""
    from compare.providers.registry import PROVIDER_PRIORITY
    try:
        response = _server._app_build_get_clef_providers_response(provider_priority=PROVIDER_PRIORITY)
    except _server._app_ClefHttpHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_clef_sources_report(self) -> None:
    """Walk the SIL contact-language config and return a provenance
    report for academic citation. Accepts both the legacy bare-list
    and the new provenance shape, so the report is well-defined on
    partially-migrated corpora.

    Response shape::

        {
          "generated_at": "2026-04-25T...Z",
          "providers": [
            {"id": "wikidata", "total_forms": 42},
            {"id": "unknown", "total_forms": 7},   # legacy entries
            ...
          ],
          "languages": [
            {
              "code": "ar",
              "name": "Arabic",
              "total_forms": 25,
              "concepts_covered": 18,
              "concepts_total": 30,
              "per_provider": {"wikidata": 10, "asjp": 8, "unknown": 7},
              "forms": [
                {
                  "concept_en": "water",
                  "form": "ma:ʔ",
                  "sources": ["wikidata", "wiktionary"]
                },
                ...
              ]
            }
          ]
        }
    """
    from compare.providers.citations import CITATION_DISPLAY_ORDER, get_citations
    from compare.providers.provenance import iter_forms_with_sources
    try:
        response = _server._app_build_get_clef_sources_report_response(config_path=_server._sil_config_path(), project_root=_server._project_root(), load_sil_config_safe=_server._load_sil_config_safe, iter_forms_with_sources=iter_forms_with_sources, get_citations=get_citations, citation_display_order=CITATION_DISPLAY_ORDER, now_factory=lambda: _server.datetime.now(_server.timezone.utc))
    except _server._app_ClefHttpHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

__all__ = ['_compute_contact_lexemes', '_api_get_contact_lexeme_coverage', '_api_get_clef_config', '_api_post_clef_config', '_api_post_clef_form_selections', '_api_get_clef_catalog', '_api_get_clef_providers', '_api_get_clef_sources_report']

