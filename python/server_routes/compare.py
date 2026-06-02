"""PARSE server route-domain module: compare."""
from __future__ import annotations

import server as _server
from canonical_lexemes import CanonicalLexemeError, delete_canonical_selection, store_canonical_selection
from compare_bundles import build_canonical_lexemes_report_tsv, build_compare_bundles
from concept_identity import identity_payload, load_concept_identity

def _compute_cognates(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    if _server.cognate_compute_module is None:
        raise RuntimeError('compare.cognate_compute is unavailable')
    threshold_raw = payload.get('threshold', 0.6)
    try:
        threshold = float(threshold_raw)
    except (TypeError, ValueError):
        raise RuntimeError('threshold must be a number')
    if threshold <= 0.0:
        raise RuntimeError('threshold must be greater than 0')
    speaker_filter_values = _server._coerce_string_list(payload.get('speakers'))
    speaker_filter = set(speaker_filter_values)
    concept_filter_values = _server._coerce_concept_id_list(payload.get('conceptIds'))
    concept_filter = set(concept_filter_values)
    contact_override = [code.lower() for code in _server._coerce_string_list(payload.get('contactLanguages'))]
    if not contact_override:
        contact_override = [code.lower() for code in _server._coerce_string_list(payload.get('contact_languages'))]
    annotations_dir_raw = payload.get('annotationsDir', payload.get('annotations_dir', 'annotations'))
    annotations_dir = _server._resolve_project_path(str(annotations_dir_raw))
    _server._set_job_progress(job_id, 10.0, message='Loading contact language data')
    contact_languages_from_config, refs_by_concept, form_selections_by_concept = _server.cognate_compute_module.load_contact_language_data(_server._sil_config_path())
    contact_languages = contact_override or contact_languages_from_config
    _server._set_job_progress(job_id, 25.0, message='Loading annotation files')
    forms_by_concept, discovered_speakers = _server.cognate_compute_module.load_annotations(annotations_dir)
    filtered_forms: _server.Dict[str, _server.List[_server.Any]] = {}
    for concept_id, records in forms_by_concept.items():
        normalized_concept_id = _server._normalize_concept_id(concept_id)
        if concept_filter and normalized_concept_id not in concept_filter:
            continue
        kept_records: _server.List[_server.Any] = []
        for record in records:
            record_speaker = str(getattr(record, 'speaker', '')).strip()
            if speaker_filter and record_speaker not in speaker_filter:
                continue
            kept_records.append(record)
        if kept_records:
            filtered_forms[normalized_concept_id] = kept_records
    if concept_filter_values:
        selected_concept_ids = concept_filter_values
    else:
        selected_concept_ids = sorted(filtered_forms.keys(), key=_server._concept_sort_key)
    concept_specs = [_server.cognate_compute_module.ConceptSpec(concept_id=concept_id, label='') for concept_id in selected_concept_ids]
    _server._set_job_progress(job_id, 45.0, message='Computing cognate sets')
    cognate_sets = _server.cognate_compute_module._compute_cognate_sets_with_lingpy(filtered_forms, concept_specs, threshold)
    _server._set_job_progress(job_id, 75.0, message='Computing similarity scores')
    similarity = _server.cognate_compute_module.compute_similarity_scores(forms_by_concept=filtered_forms, concepts=concept_specs, contact_languages=contact_languages, refs_by_concept=refs_by_concept, form_selections_by_concept=form_selections_by_concept)
    if speaker_filter_values:
        speakers_included = sorted([speaker for speaker in discovered_speakers if speaker in speaker_filter])
    else:
        speakers_included = sorted(discovered_speakers)
    enrichments_payload = {'computed_at': _server._utc_now_iso(), 'config': {'contact_languages': list(contact_languages), 'speakers_included': speakers_included, 'concepts_included': [_server._concept_out_value(concept_id) for concept_id in selected_concept_ids], 'lexstat_threshold': round(float(threshold), 3)}, 'cognate_sets': cognate_sets, 'similarity': similarity, 'borrowing_flags': {}, 'manual_overrides': {}}
    _server._set_job_progress(job_id, 92.0, message='Writing parse-enrichments.json')
    output_path = _server._enrichments_path()
    _server._write_json_file(output_path, enrichments_payload)
    return {'type': 'cognates', 'outputPath': str(output_path), 'computedAt': enrichments_payload['computed_at'], 'conceptCount': len(enrichments_payload['config']['concepts_included']), 'speakerCount': len(enrichments_payload['config']['speakers_included'])}

def _api_get_enrichments(self) -> None:
    payload = _server._read_json_file(_server._enrichments_path(), _server._default_enrichments_payload())
    self._send_json(_server.HTTPStatus.OK, {'enrichments': payload})

def _api_post_enrichments(self) -> None:
    body = self._read_json_body(required=True)
    if not isinstance(body, dict):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Enrichments payload must be a JSON object')
    enrichments_payload = body.get('enrichments') if isinstance(body.get('enrichments'), dict) else body
    _server._write_json_file(_server._enrichments_path(), enrichments_payload)
    self._send_json(_server.HTTPStatus.OK, {'success': True})

def _api_post_lexeme_note(self) -> None:
    """Write a single lexeme-level note into parse-enrichments.json."""
    body = self._expect_object(self._read_json_body(required=True), 'Request body')
    try:
        response = _server._app_build_post_lexeme_note_response(body, normalize_speaker_id=_server._normalize_speaker_id, normalize_concept_id=_server._normalize_concept_id, read_json_file=_server._read_json_file, default_enrichments_payload=_server._default_enrichments_payload, write_json_file=_server._write_json_file, enrichments_path=_server._enrichments_path(), utc_now_iso=_server._utc_now_iso)
    except _server._app_LexemeNoteHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_lexeme_notes_import(self) -> None:
    """Multipart POST — parse Audition comments CSV into lexeme_notes."""
    try:
        response = _server._app_build_post_lexeme_notes_import_response(headers=self.headers, rfile=self.rfile, project_root=_server._project_root(), upload_limit=_server.ONBOARD_MAX_UPLOAD_BYTES, normalize_speaker_id=_server._normalize_speaker_id, normalize_concept_id=_server._normalize_concept_id, annotation_read_path_for_speaker=_server._annotation_read_path_for_speaker, read_json_any_file=_server._read_json_any_file, normalize_annotation_record=_server._normalize_annotation_record, read_json_file=_server._read_json_file, default_enrichments_payload=_server._default_enrichments_payload, write_json_file=_server._write_json_file, enrichments_path=_server._enrichments_path(), utc_now_iso=_server._utc_now_iso)
    except _server._app_LexemeNoteHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_lexeme_search(self) -> None:
    """GET /api/lexeme/search — rank candidate time ranges for a concept."""
    try:
        from ai import lexeme_search as lex
    except Exception:
        try:
            from python.ai import lexeme_search as lex
        except Exception as exc:
            raise _server.ApiError(_server.HTTPStatus.INTERNAL_SERVER_ERROR, 'lexeme_search module unavailable: {0}'.format(exc))
    try:
        response = _server._app_build_get_lexeme_search_response(self.path, lex_module=lex, normalize_speaker_id=_server._normalize_speaker_id, annotation_read_path_for_speaker=_server._annotation_read_path_for_speaker, read_json_any_file=_server._read_json_any_file, normalize_annotation_record=_server._normalize_annotation_record, project_root=_server._project_root(), annotation_filename_suffix=_server.ANNOTATION_FILENAME_SUFFIX, annotation_legacy_filename_suffix=_server.ANNOTATION_LEGACY_FILENAME_SUFFIX, sil_config_path=_server._sil_config_path)
    except _server._app_MediaSearchHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_tags(self) -> None:
    """GET /api/tags — return parse-tags.json as tag array."""
    try:
        response = _server._app_build_get_tags_response(project_root=_server._project_root())
    except _server._app_ProjectArtifactHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_tags_merge(self) -> None:
    """POST /api/tags/merge — additive merge of incoming tags into parse-tags.json."""
    data = self._expect_object(self._read_json_body(required=True), 'Request body')
    try:
        response = _server._app_build_post_tags_merge_response(data, project_root=_server._project_root())
    except _server._app_ProjectArtifactHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_concept_identity(self) -> None:
    identity = load_concept_identity(_server._project_root())
    self._send_json(_server.HTTPStatus.OK, identity_payload(identity))


def _api_get_compare_bundles(self) -> None:
    params = _server._app_request_query_params(getattr(self, 'path', '/api/compare/bundles'))
    speakers = None
    if params.get('speaker'):
        speakers = [str(params['speaker'][0]).strip()]
    bundle_id = str(params.get('bundle_id', [''])[0] or '').strip() or None
    payload = build_compare_bundles(_server._project_root(), speakers=speakers, bundle_id=bundle_id)
    self._send_json(_server.HTTPStatus.OK, payload)


def _validate_canonical_request(project_root, bundle_id: str, speaker: str, body: _server.Mapping[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    csv_row_id = str(body.get('csv_row_id') or '').strip()
    if not csv_row_id:
        raise CanonicalLexemeError(_server.HTTPStatus.BAD_REQUEST, 'csv_row_id is required')
    payload = build_compare_bundles(project_root, speakers=[speaker], bundle_id=bundle_id)
    base_payload = build_compare_bundles(project_root, speakers=[], bundle_id=bundle_id)
    if not payload['bundles']:
        raise CanonicalLexemeError(_server.HTTPStatus.NOT_FOUND, 'bundle_id not found')
    bundle = payload['bundles'][0]
    base_bundle = base_payload['bundles'][0] if base_payload.get('bundles') else bundle
    if csv_row_id not in bundle.get('row_ids', []):
        raise CanonicalLexemeError(_server.HTTPStatus.BAD_REQUEST, 'csv_row_id is not a member of bundle')
    visible = any(
        variant.get('csv_row_id') == csv_row_id
        for bucket in bundle.get('buckets', [])
        for variant in bucket.get('variants', [])
        if bucket.get('survey_id') or bucket.get('source_item')
    )
    if not visible:
        raise CanonicalLexemeError(
            _server.HTTPStatus.CONFLICT,
            'selected csv_row_id is no longer visible under active per-speaker survey overrides',
            'Reload compare bundles; the active survey/source_item for this speaker changed.',
        )
    base_bucket_keys = {bucket.get('bucket_key') for bucket in base_bundle.get('buckets', [])}
    active_bucket_keys = {
        bucket.get('bucket_key')
        for bucket in bundle.get('buckets', [])
        for variant in bucket.get('variants', [])
        if variant.get('csv_row_id') == csv_row_id
    }
    if active_bucket_keys and active_bucket_keys.isdisjoint(base_bucket_keys):
        raise CanonicalLexemeError(
            _server.HTTPStatus.CONFLICT,
            'selected csv_row_id is no longer visible under active per-speaker survey overrides',
            'Reload compare bundles; the active survey/source_item for this speaker changed.',
        )
    if 'realization_index' in body and body.get('realization_index') is not None:
        try:
            idx = int(body.get('realization_index'))
        except (TypeError, ValueError) as exc:
            raise CanonicalLexemeError(_server.HTTPStatus.BAD_REQUEST, 'realization_index must be an integer') from exc
        if idx < 0:
            raise CanonicalLexemeError(_server.HTTPStatus.BAD_REQUEST, 'realization_index must be non-negative')
        if bundle.get('candidates', {}).get(speaker, {}).get(csv_row_id) is None and idx > 0:
            raise CanonicalLexemeError(_server.HTTPStatus.BAD_REQUEST, 'realization_index is out of range')
    selection = None
    for bucket in bundle.get('buckets', []):
        for variant in bucket.get('variants', []):
            if variant.get('csv_row_id') == csv_row_id:
                selection = {
                    'csv_row_id': csv_row_id,
                    'survey_id': bucket.get('survey_id', ''),
                    'source_item': bucket.get('source_item', ''),
                    'bucket_key': bucket.get('bucket_key', ''),
                    'variant_label': variant.get('variant_label', ''),
                    'realization_index': int(body.get('realization_index') or 0),
                    'source': 'manual',
                }
                break
        if selection:
            break
    if selection is None:
        raise CanonicalLexemeError(
            _server.HTTPStatus.CONFLICT,
            'selected csv_row_id is no longer visible under active per-speaker survey overrides',
            'Reload compare bundles; the active survey/source_item for this speaker changed.',
        )
    return selection


def _api_put_compare_canonical_lexeme(self, bundle_id: str, speaker: str) -> None:
    body = self._expect_object(self._read_json_body(required=True), 'Request body')
    try:
        selection = _validate_canonical_request(_server._project_root(), bundle_id, speaker, body)
        store_canonical_selection(_server._project_root(), bundle_id=bundle_id, speaker=speaker, selection=selection)
        payload = build_compare_bundles(_server._project_root(), speakers=[speaker], bundle_id=bundle_id)
    except CanonicalLexemeError as exc:
        raise _server.ApiError(exc.status, str(exc)) from exc
    self._send_json(_server.HTTPStatus.OK, {'bundle': payload['bundles'][0] if payload['bundles'] else None})


def _api_delete_compare_canonical_lexeme(self, bundle_id: str, speaker: str) -> None:
    try:
        delete_canonical_selection(_server._project_root(), bundle_id=bundle_id, speaker=speaker)
        payload = build_compare_bundles(_server._project_root(), speakers=[speaker], bundle_id=bundle_id)
    except CanonicalLexemeError as exc:
        raise _server.ApiError(exc.status, str(exc)) from exc
    self._send_json(_server.HTTPStatus.OK, {'bundle': payload['bundles'][0] if payload['bundles'] else None})


def _api_get_canonical_lexemes_report(self) -> None:
    payload = build_compare_bundles(_server._project_root())
    body = build_canonical_lexemes_report_tsv(payload).encode('utf-8')
    self.send_response(_server.HTTPStatus.OK)
    self.send_header('Content-Type', 'text/tab-separated-values; charset=utf-8')
    self.send_header('Content-Disposition', 'attachment; filename="canonical-lexemes.tsv"')
    self.send_header('Content-Length', str(len(body)))
    self.end_headers()
    self.wfile.write(body)


__all__ = ['_compute_cognates', '_api_get_enrichments', '_api_post_enrichments', '_api_post_lexeme_note', '_api_post_lexeme_notes_import', '_api_get_lexeme_search', '_api_get_tags', '_api_post_tags_merge', '_api_get_concept_identity', '_api_get_compare_bundles', '_api_put_compare_canonical_lexeme', '_api_delete_compare_canonical_lexeme', '_api_get_canonical_lexemes_report']

