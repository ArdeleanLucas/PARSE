"""PARSE server route-domain module: media."""
from __future__ import annotations

import server as _server
from concept_source_item import concept_row_from_item, source_item_from_audition_row, write_concepts_csv_rows
from concept_registry import concept_label_key, load_concept_registry, resolve_or_allocate_concept_id

def _load_cached_suggestions(speaker: str, concept_ids: _server.List[str]) -> _server.List[_server.Dict[str, _server.Any]]:
    suggestions_path = _server._project_root() / 'ai_suggestions.json'
    if not suggestions_path.exists():
        return []
    try:
        payload = _server.json.loads(suggestions_path.read_text(encoding='utf-8'))
    except (OSError, _server.json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    suggestions_block = payload.get('suggestions')
    if not isinstance(suggestions_block, dict):
        return []
    if concept_ids:
        concept_iter = concept_ids
    else:
        concept_iter = sorted(suggestions_block.keys(), key=_server._concept_sort_key)
    output: _server.List[_server.Dict[str, _server.Any]] = []
    for concept_id in concept_iter:
        entry = suggestions_block.get(str(concept_id))
        if not isinstance(entry, dict):
            continue
        speakers_map = entry.get('speakers')
        if not isinstance(speakers_map, dict):
            continue
        speaker_suggestions = speakers_map.get(speaker)
        if not isinstance(speaker_suggestions, list):
            continue
        output.append({'conceptId': _server._concept_out_value(concept_id), 'conceptEn': str(entry.get('concept_en') or ''), 'suggestions': speaker_suggestions})
    return output

def _run_stt_job(job_id: str, speaker: str, source_wav: str, language: _server.Optional[str]) -> _server.Dict[str, _server.Any]:
    """Run STT for ``speaker`` and return the result dict.

    Raises on failure. Terminal job state (_set_job_complete /
    _set_job_error) is now the dispatcher's responsibility — this
    function only reports in-progress via _set_job_progress. That
    lets the same function run cleanly under every compute mode
    (thread, subprocess, persistent) via the unified compute
    dispatcher, and also keeps direct callers like
    ``_compute_full_pipeline`` simple (try/except + read return value).
    """
    audio_path = _server._resolve_project_path(source_wav)
    if not audio_path.exists():
        raise FileNotFoundError('Audio file not found: {0}'.format(audio_path))
    _server._set_job_progress(job_id, 0.5, message='Initializing STT provider ({0})'.format(language or 'auto'))
    try:
        provider = _server.get_stt_provider()
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print('[stt] get_stt_provider failed for speaker={0!r}: {1}'.format(speaker, tb), file=_server.sys.stderr, flush=True)
        raise RuntimeError('STT provider init failed: {0}'.format(exc)) from exc
    _server._set_job_progress(job_id, 2.0, message='Loading model')

    def _progress_callback(progress: float, segments_processed: int) -> None:
        clamped = min(float(progress) if progress is not None else 0.0, 98.0)
        _server._set_job_progress(job_id, max(2.0, clamped), message='Transcribing ({0} segments)'.format(segments_processed), segments_processed=segments_processed)

    def _segment_callback(segment: _server.Dict[str, _server.Any]) -> None:
        if not isinstance(segment, dict):
            return
        partial_segment: _server.Dict[str, _server.Any] = {}
        try:
            partial_segment['start'] = float(segment.get('start', 0.0) or 0.0)
        except (TypeError, ValueError):
            partial_segment['start'] = 0.0
        try:
            partial_segment['end'] = float(segment.get('end', partial_segment['start']) or partial_segment['start'])
        except (TypeError, ValueError):
            partial_segment['end'] = partial_segment['start']
        partial_segment['text'] = str(segment.get('text', '') or '').strip()
        try:
            partial_segment['confidence'] = float(segment.get('confidence', 0.0) or 0.0)
        except (TypeError, ValueError):
            partial_segment['confidence'] = 0.0
        words = segment.get('words')
        if isinstance(words, list) and words:
            partial_segment['words'] = _server.copy.deepcopy(words)
        _server._publish_stt_partial_segment(job_id, partial_segment)
    try:
        transcribe_kwargs = {'audio_path': audio_path, 'language': language, 'progress_callback': _progress_callback, 'segment_callback': _segment_callback}
        try:
            segments = provider.transcribe(**transcribe_kwargs)
        except TypeError as exc:
            if 'segment_callback' not in str(exc):
                raise
            transcribe_kwargs.pop('segment_callback', None)
            segments = provider.transcribe(**transcribe_kwargs)
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print('[stt] transcribe failed for speaker={0!r} path={1!r}: {2}'.format(speaker, str(audio_path), tb), file=_server.sys.stderr, flush=True)
        raise RuntimeError('STT transcription failed: {0}'.format(exc)) from exc
    result = {'speaker': speaker, 'sourceWav': str(audio_path), 'language': language, 'segments': segments}
    _server._write_stt_cache(speaker, str(audio_path), language, segments)
    return result

def _compute_stt(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Compute-dispatcher adapter for STT.

    Unpacks the HTTP/chat payload into ``_run_stt_job``'s positional
    signature. The dispatcher (or persistent worker) handles the
    terminal _set_job_complete / _set_job_error — this wrapper only
    translates payload shapes.
    """
    speaker = str(payload.get('speaker') or '').strip()
    run_mode = _server._normalize_compute_run_mode(payload.get('run_mode') if payload.get('run_mode') is not None else payload.get('runMode'))
    if run_mode != 'full':
        return _server._compute_speaker_stt(job_id, payload)
    source_wav = str(payload.get('sourceWav') or payload.get('source_wav') or '').strip()
    language_raw = payload.get('language')
    language = str(language_raw).strip() if language_raw is not None else None
    if not language:
        language = None
    if not speaker:
        raise ValueError("stt payload missing 'speaker'")
    if not source_wav:
        raise ValueError("stt payload missing 'sourceWav'")
    return _server._run_stt_job(job_id, speaker, source_wav, language)

def _parse_concepts_csv(csv_path: _server.pathlib.Path) -> _server.List[_server.Dict[str, str]]:
    """Parse a concepts-style CSV (id, concept_en). Returns [] if columns don't match."""
    import csv as _csv
    try:
        with open(csv_path, newline='', encoding='utf-8-sig') as handle:
            reader = _csv.DictReader(handle)
            fieldnames = [str(name or '').strip().lower() for name in reader.fieldnames or []]
            if 'id' not in fieldnames or 'concept_en' not in fieldnames:
                return []
            concepts: _server.List[_server.Dict[str, str]] = []
            for row in reader:
                cid = _server._normalize_concept_id(row.get('id'))
                label = str(row.get('concept_en') or '').strip()
                if cid and label:
                    normalized = concept_row_from_item(row)
                    concepts.append({
                        'id': cid,
                        'label': label,
                        'source_item': normalized.get('source_item', ''),
                        'source_survey': normalized.get('source_survey', ''),
                        'custom_order': normalized.get('custom_order', ''),
                    })
            return concepts
    except (OSError, UnicodeDecodeError, _csv.Error):
        return []

def _merge_concepts_into_root_csv(new_concepts: _server.List[_server.Dict[str, str]]) -> int:
    """Merge new concepts into root concepts.csv. Existing rows win on id collision. Returns total."""
    import csv as _csv
    concepts_path = _server._project_root() / 'concepts.csv'
    merged: _server.Dict[str, _server.Dict[str, str]] = {}
    if concepts_path.exists():
        try:
            with open(concepts_path, newline='', encoding='utf-8') as handle:
                reader = _csv.DictReader(handle)
                for row in reader:
                    cid = _server._normalize_concept_id(row.get('id'))
                    label = str(row.get('concept_en') or '').strip()
                    if cid and label:
                        normalized = concept_row_from_item(row)
                        normalized['id'] = cid
                        normalized['concept_en'] = label
                        merged[cid] = normalized
        except (OSError, _csv.Error):
            pass
    for item in new_concepts:
        cid = _server._normalize_concept_id(item.get('id'))
        label = str(item.get('label') or '').strip()
        if not (cid and label):
            continue
        incoming = concept_row_from_item({**item, 'concept_en': label})
        incoming['id'] = cid
        incoming['concept_en'] = label
        if cid not in merged:
            merged[cid] = incoming
            continue
        existing = merged[cid]
        for key in ('source_item', 'source_survey', 'custom_order'):
            if not existing.get(key) and incoming.get(key):
                existing[key] = incoming[key]
    ordered = [row for _cid, row in sorted(merged.items(), key=lambda kv: _server._concept_sort_key(kv[0]))]
    write_concepts_csv_rows(concepts_path, ordered)
    return len(ordered)

def _register_speaker_in_project_json(speaker: str) -> None:
    """Add speaker to project.json speakers block. Preserves existing keys."""
    project = _server._read_json_file(_server._project_json_path(), {})
    if not isinstance(project, dict):
        project = {}
    speakers_block = project.get('speakers')
    if isinstance(speakers_block, list):
        speakers_block = {str(item).strip(): {} for item in speakers_block if str(item).strip()}
    elif not isinstance(speakers_block, dict):
        speakers_block = {}
    speakers_block.setdefault(speaker, {})
    project['speakers'] = speakers_block
    _server._write_json_file(_server._project_json_path(), project)


def _looks_like_audition_csv(csv_path: _server.pathlib.Path) -> bool:
    """Return True for Adobe Audition marker exports (Name + Start header)."""
    import csv as _csv
    import io as _io
    try:
        sample = csv_path.read_text(encoding='utf-8-sig')[:4096]
        dialect = None
        try:
            dialect = _csv.Sniffer().sniff(sample, delimiters='\t,;')
        except _csv.Error:
            pass
        reader = _csv.DictReader(_io.StringIO(sample), dialect=dialect) if dialect else _csv.DictReader(_io.StringIO(sample), delimiter='\t')
        fieldnames = {str(name or '').strip().lower() for name in (reader.fieldnames or [])}
        return 'name' in fieldnames and 'start' in fieldnames
    except (OSError, UnicodeDecodeError, _csv.Error) as exc:
        print('[audition-csv] detection failed for {0}: {1!r}'.format(csv_path, exc), file=_server.sys.stderr, flush=True)
        return False


def _audition_row_label(row: _server.Any) -> str:
    label = str(getattr(row, 'remainder', '') or '').strip()
    if label:
        return label
    return str(getattr(row, 'raw_name', '') or '').strip()


def _audition_label_key(label: str) -> str:
    return concept_label_key(label)


def _resolve_audition_concepts(rows: _server.List[_server.Any]) -> _server.List[_server.Dict[str, str]]:
    """Resolve Audition cue labels to integer PARSE concept ids in CSV order."""
    registry = load_concept_registry(_server._project_root())
    resolved: _server.List[_server.Dict[str, str]] = []
    for import_index, row in enumerate(rows):
        label = _audition_row_label(row)
        audition_prefix = _server._normalize_concept_id(getattr(row, 'concept_id', ''))
        if not label:
            continue
        if not audition_prefix:
            audition_prefix = 'row_{0}'.format(import_index)
        cid, _was_allocated = resolve_or_allocate_concept_id(registry, label)
        resolved.append({'id': cid, 'label': label, 'audition_prefix': audition_prefix, 'source_item': source_item_from_audition_row(row)})
    return resolved


def _unique_resolved_concepts(resolved_concepts: _server.List[_server.Dict[str, str]]) -> _server.List[_server.Dict[str, str]]:
    concepts: _server.List[_server.Dict[str, str]] = []
    seen = set()
    for item in resolved_concepts:
        cid = _server._normalize_concept_id(item.get('id'))
        label = str(item.get('label') or '').strip()
        if not cid or not label or cid in seen:
            continue
        seen.add(cid)
        concepts.append({
            'id': cid,
            'label': label,
            'source_item': str(item.get('source_item') or '').strip(),
            'source_survey': str(item.get('source_survey') or '').strip(),
            'custom_order': str(item.get('custom_order') or '').strip(),
        })
    return concepts


def _append_audition_rows_to_annotation(annotation: _server.Dict[str, _server.Any], rows: _server.List[_server.Any], resolved_concepts: _server.Optional[_server.List[_server.Dict[str, str]]] = None) -> int:
    """Append Audition cue rows to concept + ortho_words tiers in CSV order."""
    if resolved_concepts is None:
        resolved_concepts = _resolve_audition_concepts(rows)
    tiers = annotation.get('tiers')
    if not isinstance(tiers, dict):
        tiers = {}
        annotation['tiers'] = tiers
    concept_tier = tiers.get('concept')
    if not isinstance(concept_tier, dict):
        concept_tier = _server._annotation_empty_tier(_server.ANNOTATION_TIER_ORDER['concept'])
        tiers['concept'] = concept_tier
    concept_intervals = concept_tier.get('intervals')
    if not isinstance(concept_intervals, list):
        concept_intervals = []
        concept_tier['intervals'] = concept_intervals
    ortho_words_tier = tiers.get('ortho_words')
    if not isinstance(ortho_words_tier, dict):
        ortho_words_tier = _server._annotation_empty_tier(_server.ANNOTATION_TIER_ORDER['ortho_words'])
        tiers['ortho_words'] = ortho_words_tier
    ortho_words_intervals = ortho_words_tier.get('intervals')
    if not isinstance(ortho_words_intervals, list):
        ortho_words_intervals = []
        ortho_words_tier['intervals'] = ortho_words_intervals

    try:
        current_duration = float(annotation.get('source_audio_duration_sec') or 0.0)
    except (TypeError, ValueError):
        current_duration = 0.0
    max_end = current_duration
    imported = 0
    for import_index, row in enumerate(rows):
        if import_index >= len(resolved_concepts):
            break
        resolved = resolved_concepts[import_index]
        label = _audition_row_label(row)
        if not label:
            continue
        start = float(getattr(row, 'start_sec', 0.0) or 0.0)
        duration = float(getattr(row, 'duration_sec', 0.0) or 0.0)
        if duration <= 0:
            duration = 1.0
        end = start + duration
        interval = {
            'start': start,
            'end': end,
            'text': label,
            'concept_id': _server._normalize_concept_id(resolved.get('id')),
            'import_index': int(import_index),
            'audition_prefix': str(resolved.get('audition_prefix') or '').strip(),
        }
        concept_intervals.append(interval)
        ortho_words_intervals.append(_server.copy.deepcopy(interval))
        max_end = max(max_end, end)
        imported += 1
    if current_duration <= 0.0 and imported:
        annotation['source_audio_duration_sec'] = max_end
    return imported


def _concepts_from_audition_rows(rows: _server.List[_server.Any]) -> _server.List[_server.Dict[str, str]]:
    return _unique_resolved_concepts(_resolve_audition_concepts(rows))


def _strip_audition_comment_connector(note_text: str) -> str:
    note = str(note_text or '').strip()
    while note[:1] in {'-', ':', '–', '—'}:
        note = note[1:].strip()
    return note


def _collect_audition_comment_notes(cue_rows: _server.List[_server.Any], comments_rows: _server.List[_server.Any], resolved_concepts: _server.List[_server.Dict[str, str]], cue_name: str, comments_name: str) -> _server.List[_server.Dict[str, _server.Any]]:
    """Return import-note entries by physical Audition CSV row index."""
    if len(cue_rows) != len(comments_rows):
        print('[audition-csv] comments row count mismatch for {0} vs {1}: {2} != {3}'.format(cue_name, comments_name, len(cue_rows), len(comments_rows)), file=_server.sys.stderr, flush=True)
        return []
    notes: _server.List[_server.Dict[str, _server.Any]] = []
    for import_index, (cue_row, comments_row, resolved) in enumerate(zip(cue_rows, comments_rows, resolved_concepts)):
        cue_raw = str(getattr(cue_row, 'raw_name', '') or '')
        comments_raw = str(getattr(comments_row, 'raw_name', '') or '')
        if comments_raw == cue_raw:
            continue
        if not comments_raw.startswith(cue_raw):
            print('[audition-csv] row {0} misaligned: cue={1} comments={2}'.format(import_index, cue_raw, comments_raw), file=_server.sys.stderr, flush=True)
            continue
        note = _strip_audition_comment_connector(comments_raw[len(cue_raw):])
        cid = _server._normalize_concept_id(resolved.get('id'))
        if not note or not cid:
            continue
        notes.append({'concept_id': cid, 'import_note': note, 'import_raw': comments_raw, 'import_index': int(import_index), 'audition_prefix': str(resolved.get('audition_prefix') or '').strip()})
    return notes


def _write_audition_comment_notes(speaker: str, notes: _server.List[_server.Dict[str, _server.Any]]) -> int:
    if not notes:
        return 0
    payload = _server._read_json_file(_server._enrichments_path(), _server._default_enrichments_payload())
    notes_block = payload.get('lexeme_notes')
    if not isinstance(notes_block, dict):
        notes_block = {}
        payload['lexeme_notes'] = notes_block
    speaker_block = notes_block.get(speaker)
    if not isinstance(speaker_block, dict):
        speaker_block = {}
        notes_block[speaker] = speaker_block
    now = _server._utc_now_iso()
    imported = 0
    for note in notes:
        cid = _server._normalize_concept_id(note.get('concept_id'))
        if not cid:
            continue
        speaker_block[cid] = {'import_note': str(note.get('import_note') or '').strip(), 'import_raw': str(note.get('import_raw') or ''), 'import_index': int(note.get('import_index') or 0), 'audition_prefix': str(note.get('audition_prefix') or ''), 'updated_at': now}
        imported += 1
    _server._write_json_file(_server._enrichments_path(), payload)
    return imported


def _run_onboard_speaker_job(job_id: str, speaker: str, wav_dest: _server.pathlib.Path, csv_dest: _server.Optional[_server.pathlib.Path], comments_csv_dest: _server.Optional[_server.pathlib.Path] = None) -> None:
    """Background worker for onboard/speaker — scaffold annotation + register in source_index."""
    try:
        _server._set_job_progress(job_id, 30.0, message='Scaffolding annotation record')
        wav_relative = str(wav_dest.relative_to(_server._project_root()))
        annotation = _server._annotation_empty_record(speaker, wav_relative, None, None)
        annotation['speaker'] = speaker
        _server._annotation_touch_metadata(annotation, preserve_created=False)
        annotation_path = _server._annotation_record_path_for_speaker(speaker)
        legacy_annotation_path = _server._annotation_legacy_record_path_for_speaker(speaker)
        _server._write_annotation_to_canonical_and_legacy(annotation_path, annotation_path, legacy_annotation_path, annotation)
        _server._set_job_progress(job_id, 55.0, message='Updating source index')
        source_index_path = _server._source_index_path()
        source_index = _server._read_json_file(source_index_path, {})
        speakers_block = source_index.get('speakers')
        if not isinstance(speakers_block, dict):
            speakers_block = {}
            source_index['speakers'] = speakers_block
        speaker_entry = speakers_block.get(speaker)
        if not isinstance(speaker_entry, dict):
            speaker_entry = {'source_wavs': []}
            speakers_block[speaker] = speaker_entry
        source_wavs = speaker_entry.get('source_wavs')
        if not isinstance(source_wavs, list):
            source_wavs = []
            speaker_entry['source_wavs'] = source_wavs
        wav_filename = wav_dest.name
        already_registered = any((isinstance(entry, dict) and str(entry.get('filename', '')) == wav_filename for entry in source_wavs))
        if not already_registered:
            source_wavs.append({'filename': wav_filename, 'path': wav_relative, 'is_primary': len(source_wavs) == 0, 'added_at': _server._utc_now_iso()})
        _server._write_json_file(source_index_path, source_index)
        _server._set_job_progress(job_id, 70.0, message='Registering speaker in project.json')
        _server._register_speaker_in_project_json(speaker)
        concept_total: _server.Optional[int] = None
        concepts_added = 0
        comments_imported = 0
        lexemes_imported = 0
        if csv_dest is not None and csv_dest.exists():
            _server._set_job_progress(job_id, 80.0, message='Merging concepts from CSV')
            parsed = _server._parse_concepts_csv(csv_dest)
            if parsed:
                concepts_added = len(parsed)
                concept_total = _server._merge_concepts_into_root_csv(parsed)
            elif _looks_like_audition_csv(csv_dest):
                from lexeme_notes import parse_audition_csv as _parse_audition_csv
                csv_text = csv_dest.read_text(encoding='utf-8-sig')
                cue_rows = _parse_audition_csv(csv_text)
                if cue_rows:
                    audition_resolved_concepts = _resolve_audition_concepts(cue_rows)
                    lexemes_imported = _append_audition_rows_to_annotation(annotation, cue_rows, audition_resolved_concepts)
                    if lexemes_imported:
                        _server._annotation_touch_metadata(annotation, preserve_created=True)
                        _server._write_annotation_to_canonical_and_legacy(annotation_path, annotation_path, legacy_annotation_path, annotation)
                        audition_concepts = _unique_resolved_concepts(audition_resolved_concepts)
                        concepts_added = len(audition_concepts)
                        if audition_concepts:
                            concept_total = _server._merge_concepts_into_root_csv(audition_concepts)
                    if comments_csv_dest is not None and comments_csv_dest.exists():
                        try:
                            comments_text = comments_csv_dest.read_text(encoding='utf-8-sig')
                            comments_rows = _parse_audition_csv(comments_text)
                            comment_notes = _collect_audition_comment_notes(cue_rows, comments_rows, audition_resolved_concepts, csv_dest.name, comments_csv_dest.name)
                            comments_imported = _write_audition_comment_notes(speaker, comment_notes)
                        except Exception as exc:
                            print('[audition-csv] comments import failed for {0}: {1!r}'.format(comments_csv_dest.name, exc), file=_server.sys.stderr, flush=True)
                            comments_imported = 0
        _server._set_job_progress(job_id, 90.0, message='Finalizing')
        result: _server.Dict[str, _server.Any] = {'speaker': speaker, 'wavPath': wav_relative, 'csvPath': str(csv_dest.relative_to(_server._project_root())) if csv_dest else None, 'commentsCsvPath': str(comments_csv_dest.relative_to(_server._project_root())) if comments_csv_dest else None, 'annotationPath': str(annotation_path.relative_to(_server._project_root())), 'conceptsAdded': concepts_added, 'conceptTotal': concept_total, 'commentsImported': comments_imported, 'lexemesImported': lexemes_imported}
        complete_message = 'Imported {0} lexemes from {1}'.format(lexemes_imported, csv_dest.name) if lexemes_imported and csv_dest else 'Speaker onboarded'
        _server._set_job_complete(job_id, result, message=complete_message)
    except Exception as exc:
        _server._set_job_error(job_id, str(exc))

def _run_normalize_job(job_id: str, speaker: str, source_wav: str) -> None:
    """Background worker — runs ffmpeg loudnorm to normalize audio to LUFS target."""
    try:
        audio_path = _server._resolve_project_path(source_wav)
        if not audio_path.exists():
            raise FileNotFoundError('Audio file not found: {0}'.format(audio_path))
        working_root = _server._project_root() / 'audio' / 'working'
        _server._set_job_progress(job_id, 5.0, message='Checking ffmpeg availability')
        try:
            _server.subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=10)
        except FileNotFoundError:
            raise RuntimeError('ffmpeg is not installed or not on PATH')
        _server._set_job_progress(job_id, 10.0, message='Scanning loudness (pass 1)')
        measure_cmd = ['ffmpeg', '-i', str(audio_path), '-af', 'loudnorm=print_format=json', '-f', 'null', '-']
        measure_result = _server.subprocess.run(measure_cmd, capture_output=True, text=True, timeout=600)
        stderr_text = measure_result.stderr or ''
        measured_i = None
        measured_tp = None
        measured_lra = None
        measured_thresh = None
        json_start = stderr_text.rfind('{')
        json_end = stderr_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            try:
                loudnorm_stats = _server.json.loads(stderr_text[json_start:json_end])
                measured_i = str(loudnorm_stats.get('input_i', ''))
                measured_tp = str(loudnorm_stats.get('input_tp', ''))
                measured_lra = str(loudnorm_stats.get('input_lra', ''))
                measured_thresh = str(loudnorm_stats.get('input_thresh', ''))
            except (_server.json.JSONDecodeError, ValueError):
                pass
        _server._set_job_progress(job_id, 40.0, message='Normalizing audio (pass 2)')
        working_dir = working_root / speaker
        working_dir.mkdir(parents=True, exist_ok=True)
        output_path = _server.build_normalized_output_path(audio_path, working_dir)
        try:
            inplace = output_path.resolve() == audio_path.resolve()
        except OSError:
            inplace = str(output_path) == str(audio_path)
        if inplace:
            write_path = output_path.with_name(output_path.stem + '.normalized.tmp.wav')
        else:
            write_path = output_path
        normalize_filter = 'loudnorm=I={target}'.format(target=_server.NORMALIZE_LUFS_TARGET)
        if measured_i and measured_tp and measured_lra and measured_thresh:
            normalize_filter = 'loudnorm=I={target}:measured_I={mi}:measured_TP={mtp}:measured_LRA={mlra}:measured_thresh={mt}:linear=true'.format(target=_server.NORMALIZE_LUFS_TARGET, mi=measured_i, mtp=measured_tp, mlra=measured_lra, mt=measured_thresh)
        normalize_cmd = ['ffmpeg', '-y', '-i', str(audio_path), '-af', normalize_filter, '-ar', _server.NORMALIZE_SAMPLE_RATE, '-ac', _server.NORMALIZE_CHANNELS, '-c:a', _server.NORMALIZE_AUDIO_CODEC, '-sample_fmt', _server.NORMALIZE_SAMPLE_FORMAT, str(write_path)]
        proc = _server.subprocess.run(normalize_cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            error_tail = (proc.stderr or '')[-800:]
            if inplace and write_path.exists():
                try:
                    write_path.unlink()
                except OSError:
                    pass
            raise RuntimeError('ffmpeg normalize failed (exit {0}): {1}'.format(proc.returncode, error_tail))
        if not write_path.exists():
            raise RuntimeError('ffmpeg produced no output file')
        if inplace:
            _server.os.replace(str(write_path), str(output_path))
        _server._set_job_progress(job_id, 95.0, message='Finalizing')
        output_relative = str(output_path.relative_to(_server._project_root()))
        result: _server.Dict[str, _server.Any] = {'speaker': speaker, 'sourcePath': source_wav, 'normalizedPath': output_relative}
        _server._set_job_complete(job_id, result, message='Normalization complete')
    except Exception as exc:
        _server._set_job_error(job_id, str(exc))

def _compute_training_job(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Stub for the wav2vec2 / IPA fine-tuning training job.

    Wired into the compute dispatcher so the frontend / API can already
    POST `/api/compute/train_ipa_model`. The actual run will delegate to
    the `ipa-phonetic-autoresearch` harness (runs in the persistent worker
    once that integration lands — GPU training will be fully supported here).
    """
    _server._set_job_progress(job_id, 0.0, message='Training job accepted (persistent-worker GPU harness pending)')
    return {'status': 'pending', 'message': 'train_ipa_model not yet implemented — harness integration pending.', 'payload_keys': sorted(list(payload.keys())) if isinstance(payload, dict) else []}

def _api_post_onboard_speaker(self) -> None:
    """Handle multipart POST /api/onboard/speaker — upload WAV + optional CSV."""
    content_type = self.headers.get('Content-Type', '')
    if 'multipart/form-data' not in content_type:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Content-Type must be multipart/form-data')
    raw_length = self.headers.get('Content-Length', '')
    try:
        content_length = int(raw_length)
    except (ValueError, TypeError):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Content-Length header is required')
    if content_length > _server.ONBOARD_MAX_UPLOAD_BYTES:
        raise _server.ApiError(_server.HTTPStatus.REQUEST_ENTITY_TOO_LARGE, 'Upload exceeds {0} byte limit'.format(_server.ONBOARD_MAX_UPLOAD_BYTES))
    environ = {'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': content_type, 'CONTENT_LENGTH': str(content_length)}
    form = _server.cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=environ, keep_blank_values=True)
    speaker_id_field = form.getfirst('speaker_id', '')
    if isinstance(speaker_id_field, bytes):
        speaker_id_field = speaker_id_field.decode('utf-8', errors='replace')
    speaker_id_raw = str(speaker_id_field or '').strip()
    try:
        speaker = _server._normalize_speaker_id(speaker_id_raw)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    audio_item = form['audio'] if 'audio' in form else None
    if audio_item is None or not getattr(audio_item, 'filename', None):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'audio file is required')
    audio_filename = _server.os.path.basename(audio_item.filename or 'upload.wav')
    audio_ext = _server.pathlib.Path(audio_filename).suffix.lower()
    if audio_ext not in _server.ONBOARD_AUDIO_EXTENSIONS:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Unsupported audio format: {0} (allowed: {1})'.format(audio_ext, ', '.join(sorted(_server.ONBOARD_AUDIO_EXTENSIONS))))
    csv_dest: _server.Optional[_server.pathlib.Path] = None
    comments_csv_dest: _server.Optional[_server.pathlib.Path] = None
    csv_item = form['csv'] if 'csv' in form else None
    comments_item = form['commentsCsv'] if 'commentsCsv' in form else None
    has_csv = csv_item is not None and bool(getattr(csv_item, 'filename', None))
    has_comments_csv = comments_item is not None and bool(getattr(comments_item, 'filename', None))
    if has_comments_csv and not has_csv:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'commentsCsv requires csv cue file')
    speaker_audio_dir = _server._project_root() / 'audio' / 'original' / speaker
    speaker_audio_dir.mkdir(parents=True, exist_ok=True)
    wav_dest = speaker_audio_dir / audio_filename
    audio_data = audio_item.file.read()
    wav_dest.write_bytes(audio_data)
    if has_csv:
        csv_filename = _server.os.path.basename(csv_item.filename or 'elicitation.csv')
        csv_dest = speaker_audio_dir / csv_filename
        csv_data = csv_item.file.read()
        csv_dest.write_bytes(csv_data)
    if has_comments_csv and csv_dest is not None:
        csv_path = _server.pathlib.Path(csv_dest.name)
        suffix = csv_path.suffix or '.csv'
        comments_filename = '{0}.comments{1}'.format(csv_path.stem, suffix)
        comments_csv_dest = speaker_audio_dir / comments_filename
        comments_csv_data = comments_item.file.read()
        comments_csv_dest.write_bytes(comments_csv_data)
    try:
        job_payload = {'speaker': speaker, 'wavPath': str(wav_dest.relative_to(_server._project_root())), 'csvPath': str(csv_dest.relative_to(_server._project_root())) if csv_dest else None, 'commentsCsvPath': str(comments_csv_dest.relative_to(_server._project_root())) if comments_csv_dest else None}
        job_id = _server._create_job('onboard:speaker', job_payload)
    except _server.JobResourceConflictError as exc:
        raise _server.ApiError(_server.HTTPStatus.CONFLICT, str(exc))
    thread = _server.threading.Thread(target=_server._run_onboard_speaker_job, args=(job_id, speaker, wav_dest, csv_dest, comments_csv_dest), daemon=True)
    thread.start()
    self._send_json(_server.HTTPStatus.OK, {'job_id': job_id, 'jobId': job_id, 'status': 'running', 'speaker': speaker})

def _api_post_normalize(self) -> None:
    """Handle POST /api/normalize — start audio normalization job."""
    body = self._expect_object(self._read_json_body(), 'Request body')
    callback_url = _server._job_callback_url_from_mapping(body)

    def _launch_normalize_job(job_id: str, speaker: str, source_wav: str) -> None:
        thread = _server.threading.Thread(target=_server._run_normalize_job, args=(job_id, speaker, source_wav), daemon=True)
        thread.start()
    try:
        response = _server._app_build_post_normalize_response(body, callback_url=callback_url, normalize_speaker_id=_server._normalize_speaker_id, annotation_primary_source_wav=_server._annotation_primary_source_wav, create_job=_server._create_job, launch_normalize_job=_launch_normalize_job, job_conflict_error_cls=_server.JobResourceConflictError)
    except _server._app_SpeechAnnotationHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_onboard_speaker_status(self) -> None:
    """Poll status for an onboard:speaker job."""
    body = self._expect_object(self._read_json_body(), 'Request body')
    job_id = str(body.get('jobId') or body.get('job_id') or '').strip()
    if not job_id:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'job_id is required')
    job = _server._get_job_snapshot(job_id)
    if job is None:
        raise _server.ApiError(_server.HTTPStatus.NOT_FOUND, 'Unknown job_id')
    if str(job.get('type') or '') != 'onboard:speaker':
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'job_id is not an onboard:speaker job')
    self._send_json(_server.HTTPStatus.OK, _server._job_response_payload(job))

def _api_post_normalize_status(self) -> None:
    """Poll status for a normalize job."""
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_normalize_status_response(body, get_job_snapshot=_server._get_job_snapshot, job_response_payload=_server._job_response_payload)
    except _server._app_SpeechAnnotationHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_stt_start(self) -> None:
    body = self._expect_object(self._read_json_body(), 'Request body')
    callback_url = _server._job_callback_url_from_mapping(body)
    try:
        response = _server._app_build_post_stt_start_response(body, callback_url=callback_url, create_job=_server._create_job, launch_compute_runner=_server._launch_compute_runner, job_conflict_error_cls=_server.JobResourceConflictError)
    except _server._app_SpeechAnnotationHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_stt_status(self) -> None:
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_stt_status_response(body, get_job_snapshot=_server._get_job_snapshot, job_response_payload=_server._job_response_payload)
    except _server._app_SpeechAnnotationHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_suggest(self) -> None:
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_suggest_response(body, get_llm_provider=_server.get_llm_provider, load_cached_suggestions=_server._load_cached_suggestions, coerce_concept_id_list=_server._coerce_concept_id_list)
    except _server._app_SpeechAnnotationHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_spectrogram(self) -> None:
    """Return (or generate) a PNG spectrogram for a clip; cached on disk."""
    import spectrograms as spectro_module
    try:
        response = _server._app_build_get_spectrogram_response(self.path, spectro_module=spectro_module, normalize_speaker_id=_server._normalize_speaker_id, resolve_project_path=_server._resolve_project_path, project_root=_server._project_root(), annotation_primary_source_wav=_server._annotation_primary_source_wav, cors_headers=_server.CORS_HEADERS)
    except _server._app_MediaSearchHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self.send_response(response.status)
    for key, value in response.headers.items():
        self.send_header(key, value)
    self.end_headers()
    try:
        self.wfile.write(response.body)
    except BrokenPipeError:
        pass

__all__ = ['_load_cached_suggestions', '_run_stt_job', '_compute_stt', '_parse_concepts_csv', '_merge_concepts_into_root_csv', '_register_speaker_in_project_json', '_run_onboard_speaker_job', '_run_normalize_job', '_compute_training_job', '_api_post_onboard_speaker', '_api_post_normalize', '_api_post_onboard_speaker_status', '_api_post_normalize_status', '_api_post_stt_start', '_api_post_stt_status', '_api_post_suggest', '_api_get_spectrogram']

