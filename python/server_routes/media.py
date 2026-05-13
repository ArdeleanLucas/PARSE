"""PARSE server route-domain module: media."""
from __future__ import annotations

import logging

import server as _server
from concept_source_item import concept_row_from_item, read_concepts_csv_rows, source_item_from_audition_row
from concept_registry import concept_label_key, load_concept_registry, merge_concepts_into_root_csv, resolve_or_allocate_concept_id
from survey_overlap import concept_survey_links_for_row, load_survey_overlap_state, normalize_survey_id, update_survey_overlap_state

logger = logging.getLogger(__name__)


def _stt_audio_duration_seconds(path: _server.pathlib.Path) -> float:
    """Return STT chunking duration from soundfile metadata."""
    try:
        import soundfile as sf

        info = sf.info(str(path))
        duration = getattr(info, 'duration', None)
        if duration is not None:
            return max(0.0, float(duration))
    except Exception as exc:
        # Preserve historical unit-test/provider behavior for non-decodable dummy
        # fixtures; real invalid audio will still fail inside the provider.
        logger.warning('Could not read STT audio duration for %s: %r; using single-shot path', path, exc)
    return 0.0


def _write_audio_slice_to_temp_wav(audio_path: _server.pathlib.Path, start_sec: float, end_sec: float) -> str:
    """Write ``[start_sec, end_sec)`` from ``audio_path`` to a caller-owned temp WAV."""
    import soundfile as sf
    import tempfile

    info = sf.info(str(audio_path))
    sample_rate = int(getattr(info, 'samplerate', 0) or 0)
    if sample_rate <= 0:
        raise RuntimeError('Could not determine sample rate for {0}'.format(audio_path))
    start_frame = max(0, int(round(float(start_sec) * sample_rate)))
    stop_frame = max(start_frame, int(round(float(end_sec) * sample_rate)))
    data, read_sample_rate = sf.read(str(audio_path), start=start_frame, stop=stop_frame, always_2d=False)
    handle = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_path = handle.name
    handle.close()
    try:
        sf.write(temp_path, data, int(read_sample_rate or sample_rate))
    except Exception:
        try:
            _server.os.remove(temp_path)
        except OSError:
            pass
        raise
    return temp_path


def _classify_stt_chunk_error(exc: BaseException) -> str:
    message = str(exc).lower()
    if isinstance(exc, MemoryError) or any(marker in message for marker in ('cuda out of memory', 'killed', 'oom', '137')):
        return 'oom_suspect'
    if 'timeout' in message or 'timed out' in message:
        return 'timeout'
    return 'provider_error'


def _stt_default_chunk_seconds() -> float:
    raw_value = str(_server.os.environ.get('PARSE_STT_DEFAULT_CHUNK_MINUTES', '10') or '10').strip()
    try:
        minutes = float(raw_value)
    except (TypeError, ValueError):
        logger.warning('Invalid PARSE_STT_DEFAULT_CHUNK_MINUTES=%r; falling back to 10 minutes', raw_value)
        minutes = 10.0
    return max(0.0, minutes * 60.0)


def _stt_chunk_progress_pct(chunk_idx: int, total_chunks: int) -> float:
    if total_chunks <= 0:
        return 2.0
    return min(94.0, 2.0 + (float(chunk_idx) / float(total_chunks)) * 92.0)


def _stt_coverage_end_sec(segments: _server.List[_server.Dict[str, _server.Any]]) -> float:
    """Return the final non-empty STT segment end timestamp."""
    end_sec = 0.0
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        if not str(segment.get('text') or '').strip():
            continue
        try:
            segment_end = float(segment.get('end') or 0.0)
        except (TypeError, ValueError):
            continue
        end_sec = max(end_sec, segment_end)
    return end_sec


def _emit_stt_summary_log(job_id: str, speaker: str, result: _server.Dict[str, _server.Any]) -> None:
    """Emit the single operator-facing STT completion summary line."""
    segments = result.get('segments') if isinstance(result.get('segments'), list) else []
    chunks = result.get('chunks') if isinstance(result.get('chunks'), list) else []
    try:
        duration_sec = float(result.get('duration_sec') or 0.0)
    except (TypeError, ValueError):
        duration_sec = 0.0
    logger.info(
        '[STT] job=%s speaker=%s chunked=%s chunk_count=%d total_duration_sec=%.2f coverage_end_sec=%.2f segments=%d',
        job_id,
        speaker,
        str(bool(chunks)).lower(),
        len(chunks),
        duration_sec,
        _stt_coverage_end_sec(segments),
        len(segments),
    )


def _offset_stt_segment_timestamps(segment: _server.Dict[str, _server.Any], offset: float) -> _server.Dict[str, _server.Any]:
    shifted = dict(segment)
    for key in ('start', 'end'):
        if key in shifted:
            try:
                shifted[key] = float(shifted[key]) + offset
            except (TypeError, ValueError):
                pass
    words = shifted.get('words')
    if isinstance(words, list):
        shifted_words = []
        for word in words:
            if not isinstance(word, dict):
                shifted_words.append(word)
                continue
            shifted_word = dict(word)
            for key in ('start', 'end'):
                if key in shifted_word:
                    try:
                        shifted_word[key] = float(shifted_word[key]) + offset
                    except (TypeError, ValueError):
                        pass
            shifted_words.append(shifted_word)
        shifted['words'] = shifted_words
    return shifted


def _transcribe_stt_with_callback_fallback(provider: _server.Any, transcribe_kwargs: _server.Dict[str, _server.Any]) -> _server.List[_server.Dict[str, _server.Any]]:
    try:
        return provider.transcribe(**transcribe_kwargs)
    except TypeError as exc:
        if 'segment_callback' not in str(exc):
            raise
        fallback_kwargs = dict(transcribe_kwargs)
        fallback_kwargs.pop('segment_callback', None)
        return provider.transcribe(**fallback_kwargs)

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

    Long full-file STT runs are split into adjacent Tier-1 chunks so each
    provider call gets fresh decoder state. Terminal job state
    (_set_job_complete / _set_job_error) remains the dispatcher's
    responsibility; this function reports in-progress updates and returns the
    result envelope.
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

    def _transcribe_single(path: _server.pathlib.Path, *, progress_callback, segment_callback) -> _server.List[_server.Dict[str, _server.Any]]:
        transcribe_kwargs = {
            'audio_path': path,
            'language': language,
            'progress_callback': progress_callback,
            'segment_callback': segment_callback,
        }
        return _transcribe_stt_with_callback_fallback(provider, transcribe_kwargs)

    duration_sec = _stt_audio_duration_seconds(audio_path)
    chunk_seconds = _stt_default_chunk_seconds()
    chunk_results: _server.List[_server.Dict[str, _server.Any]] = []
    cancelled_requested = False
    try:
        from ai.job_cancel import clear_cancel, make_should_cancel

        should_cancel = make_should_cancel(job_id)
        if chunk_seconds <= 0.0 or duration_sec <= chunk_seconds:
            try:
                segments = _transcribe_single(audio_path, progress_callback=_progress_callback, segment_callback=_segment_callback)
                cancelled_requested = should_cancel()
            except Exception as exc:
                import traceback
                tb = traceback.format_exc()
                print('[stt] transcribe failed for speaker={0!r} path={1!r}: {2}'.format(speaker, str(audio_path), tb), file=_server.sys.stderr, flush=True)
                raise RuntimeError('STT transcription failed: {0}'.format(exc)) from exc
        else:
            from workers.audio_chunking import merge_chunk_segments, split_audio_duration

            spans = split_audio_duration(duration_sec, chunk_seconds)
            per_chunk_segments: _server.List[_server.List[_server.Dict[str, _server.Any]]] = []
            temp_paths: _server.List[str] = []
            try:
                total_chunks = len(spans)
                cumulative_segments = 0
                for span in spans:
                    should_cancel = make_should_cancel(job_id)
                    if should_cancel():
                        cancelled_requested = True
                        for remaining_span in spans[int(span['idx']):]:
                            per_chunk_segments.append([])
                            chunk_results.append({'idx': remaining_span['idx'], 'span': remaining_span, 'status': 'cancelled'})
                        break
                    span_start = float(span['start'])
                    span_end = float(span['end'])
                    _server._set_job_progress(
                        job_id,
                        _stt_chunk_progress_pct(int(span['idx']), total_chunks),
                        message='STT chunk {0}/{1} ({2}s–{3}s)'.format(
                            int(span['idx']) + 1,
                            total_chunks,
                            int(span_start),
                            int(span_end),
                        ),
                        segments_processed=cumulative_segments,
                    )
                    try:
                        slice_path = _write_audio_slice_to_temp_wav(audio_path, span_start, span_end)
                        temp_paths.append(slice_path)

                        def _chunk_segment_callback(segment: _server.Dict[str, _server.Any], *, _offset: float = span_start) -> None:
                            if isinstance(segment, dict):
                                _segment_callback(_offset_stt_segment_timestamps(segment, _offset))

                        chunk_segments = _transcribe_single(
                            _server.pathlib.Path(slice_path),
                            progress_callback=_progress_callback,
                            segment_callback=_chunk_segment_callback,
                        )
                        per_chunk_segments.append(chunk_segments)
                        cumulative_segments += len(chunk_segments)
                        chunk_results.append({'idx': span['idx'], 'span': span, 'status': 'ok'})
                    except MemoryError as exc:
                        per_chunk_segments.append([])
                        chunk_results.append({'idx': span['idx'], 'span': span, 'status': 'error', 'error_code': 'oom_suspect', 'error': str(exc)})
                    except Exception as exc:
                        per_chunk_segments.append([])
                        chunk_results.append({'idx': span['idx'], 'span': span, 'status': 'error', 'error_code': _classify_stt_chunk_error(exc), 'error': str(exc)})
                segments = merge_chunk_segments(per_chunk_segments, spans)
                cancelled_requested = cancelled_requested or make_should_cancel(job_id)()
            finally:
                for temp_path in temp_paths:
                    try:
                        _server.os.remove(temp_path)
                    except OSError:
                        pass
    finally:
        try:
            clear_cancel(job_id)
        except Exception:
            pass
    result = {
        'speaker': speaker,
        'sourceWav': str(audio_path),
        'language': language,
        'segments': segments,
        'chunks': chunk_results,
        'duration_sec': duration_sec,
    }
    if cancelled_requested:
        result['status'] = 'cancelled'
    _emit_stt_summary_log(job_id, speaker, result)
    _server._write_stt_cache(speaker, str(audio_path), language, segments)
    return result


def _run_stt_job_subprocess_entry(job_id: str, payload: _server.Dict[str, _server.Any], result_path: str, checkpoint_path: str) -> None:
    """Spawn-child entry point for full-file STT isolation."""
    import json as _json
    import traceback as _tb

    _server.os.environ['PARSE_COMPUTE_CHECKPOINT_LOG'] = checkpoint_path
    for key, value in (payload.get('env') or {}).items():
        _server.os.environ[str(key)] = str(value)
    outcome: _server.Dict[str, _server.Any] = {'ok': False}
    try:
        _server._compute_checkpoint('STT_CHILD.entry', job_id=job_id)
        result = _run_stt_job(
            job_id,
            str(payload.get('speaker') or ''),
            str(payload.get('source_wav') or payload.get('sourceWav') or ''),
            str(payload.get('language')).strip() if payload.get('language') is not None and str(payload.get('language')).strip() else None,
        )
        _server._compute_checkpoint('STT_CHILD.ok', job_id=job_id)
        outcome = {'ok': True, 'result': result}
    except BaseException as exc:  # noqa: BLE001 - child must serialize any failure instead of killing parent.
        outcome = {'ok': False, 'error': str(exc), 'traceback': _tb.format_exc()}
        try:
            _server._compute_checkpoint('STT_CHILD.error', job_id=job_id, error=str(exc))
        except Exception:
            pass
    try:
        with open(result_path, 'w', encoding='utf-8') as handle:
            _json.dump(outcome, handle)
    except Exception:
        pass


def _run_stt_job_in_subprocess(job_id: str, speaker: str, source_wav: str, language: _server.Optional[str]) -> _server.Dict[str, _server.Any]:
    """Run full-file STT in a spawn child so provider crashes do not kill the parent."""
    result = _server._run_in_isolated_subprocess(
        job_id,
        {
            'speaker': speaker,
            'source_wav': source_wav,
            'language': language,
            'env': {
                'PARSE_STT_DEFAULT_CHUNK_MINUTES': _server.os.environ.get('PARSE_STT_DEFAULT_CHUNK_MINUTES', '10'),
            },
        },
        subprocess_entry=_run_stt_job_subprocess_entry,
        log_prefix='STT_SUBPROCESS',
        result_file_prefix='parse-stt-',
    )
    if result.get('status') == 'error' and not result.get('error_code'):
        result = dict(result)
        result['error_code'] = 'provider_error'
    return result


def _compute_stt(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Compute-dispatcher adapter for STT.

    Unpacks the HTTP/chat payload into ``_run_stt_job_in_subprocess``'s
    positional signature. The dispatcher (or persistent worker) handles the
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
    return _server._run_stt_job_in_subprocess(job_id, speaker, source_wav, language)

def _parse_concepts_csv_text(csv_text: str) -> _server.List[_server.Dict[str, str]]:
    """Parse concepts-style CSV text (id, concept_en); return [] if columns do not match."""
    import csv as _csv
    import io as _io
    try:
        reader = _csv.DictReader(_io.StringIO(csv_text))
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
    except _csv.Error:
        return []


def _parse_concepts_csv(csv_path: _server.pathlib.Path) -> _server.List[_server.Dict[str, str]]:
    """Parse a concepts-style CSV (id, concept_en). Returns [] if columns don't match."""
    try:
        return _parse_concepts_csv_text(csv_path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeDecodeError):
        return []

def _merge_concepts_into_root_csv(new_concepts: _server.List[_server.Dict[str, str]]) -> int:
    """Merge new concepts into root concepts.csv. Existing rows win on id collision. Returns total."""
    return merge_concepts_into_root_csv(
        _server._project_root(),
        new_concepts,
        normalize_concept_id=_server._normalize_concept_id,
        concept_sort_key=_server._concept_sort_key,
    )

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


def _looks_like_audition_csv_text(csv_text: str) -> bool:
    """Return True for Adobe Audition marker CSV text (Name + Start header)."""
    import csv as _csv
    import io as _io
    sample = str(csv_text or '')[:4096]
    try:
        dialect = None
        try:
            dialect = _csv.Sniffer().sniff(sample, delimiters='\t,;')
        except _csv.Error:
            pass
        reader = _csv.DictReader(_io.StringIO(sample), dialect=dialect) if dialect else _csv.DictReader(_io.StringIO(sample), delimiter='\t')
        fieldnames = {str(name or '').strip().lower() for name in (reader.fieldnames or [])}
        return 'name' in fieldnames and 'start' in fieldnames
    except _csv.Error:
        return False


def _looks_like_audition_csv(csv_path: _server.pathlib.Path) -> bool:
    """Return True for Adobe Audition marker exports (Name + Start header)."""
    try:
        return _looks_like_audition_csv_text(csv_path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeDecodeError) as exc:
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
        source_item, source_survey = source_item_from_audition_row(row)
        resolved.append({
            'id': cid,
            'label': label,
            'audition_prefix': audition_prefix,
            'source_item': source_item,
            'source_survey': source_survey,
        })
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


def _field_text(form: _server.Any, name: str) -> str:
    value = form.getfirst(name, '') if hasattr(form, 'getfirst') else ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace').strip()
    return str(value or '').strip()


def _truthy_upload_flag(value: object) -> bool:
    return str(value or '').strip().casefold() in {'1', 'true', 'yes', 'on', 'preview'}


def _preview_requested(self: _server.Any, form: _server.Any) -> bool:
    try:
        query_values = self._request_query_params().get('preview', [])
    except Exception:
        query_values = []
    if any(_truthy_upload_flag(value) for value in query_values):
        return True
    return _truthy_upload_flag(_field_text(form, 'preview'))


def _decode_uploaded_csv(csv_item: _server.Any) -> str:
    if csv_item is None or not getattr(csv_item, 'filename', None):
        return ''
    data = csv_item.file.read()
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return ''


def _concepts_from_csv_text(csv_text: str) -> _server.List[_server.Dict[str, str]]:
    parsed = _parse_concepts_csv_text(csv_text)
    if parsed:
        return parsed
    if not _looks_like_audition_csv_text(csv_text):
        return []
    try:
        from lexeme_notes import parse_audition_csv as _parse_audition_csv
        cue_rows = _parse_audition_csv(csv_text)
    except Exception:
        return []
    if not cue_rows:
        return []
    return _unique_resolved_concepts(_resolve_audition_concepts(cue_rows))


def _concept_label(item: _server.Dict[str, object]) -> str:
    return str(item.get('concept_en') or item.get('label') or '').strip()


def _add_survey_links(target: _server.Dict[str, str], links: _server.Dict[str, object]) -> None:
    for survey_id, source_item in links.items():
        sid = normalize_survey_id(survey_id)
        item = str(source_item or '').strip()
        if sid and item:
            target[sid] = item


def _build_onboard_overlap_preview(speaker: str, csv_text: str) -> _server.Dict[str, _server.Any]:
    project_root = _server._project_root()
    state = load_survey_overlap_state(project_root)
    incoming = _concepts_from_csv_text(csv_text) if csv_text else []
    by_label: _server.Dict[str, _server.Dict[str, _server.Any]] = {}

    def entry_for(label: str, concept_id: str) -> _server.Optional[_server.Dict[str, _server.Any]]:
        clean_label = str(label or '').strip()
        key = concept_label_key(clean_label)
        if not key:
            return None
        entry = by_label.setdefault(key, {'concept_id': str(concept_id or '').strip(), 'concept_en': clean_label, 'surveys': {}, 'incoming_surveys': []})
        if not entry.get('concept_id') and concept_id:
            entry['concept_id'] = str(concept_id or '').strip()
        if not entry.get('concept_en') and clean_label:
            entry['concept_en'] = clean_label
        return entry

    try:
        existing_rows = read_concepts_csv_rows(project_root / 'concepts.csv')
    except Exception:
        existing_rows = []
    for row in existing_rows:
        cid = _server._normalize_concept_id(row.get('id')) or str(row.get('id') or '').strip()
        label = _concept_label(row)
        entry = entry_for(label, cid)
        if entry is None:
            continue
        _add_survey_links(entry['surveys'], concept_survey_links_for_row(row, state))

    for item in incoming:
        cid = _server._normalize_concept_id(item.get('id')) or str(item.get('id') or '').strip()
        label = _concept_label(item)
        entry = entry_for(label, cid)
        if entry is None:
            continue
        source_survey = normalize_survey_id(item.get('source_survey'))
        source_item = str(item.get('source_item') or '').strip()
        if source_survey and source_item:
            entry['surveys'][source_survey] = source_item
            entry['incoming_surveys'].append(source_survey)

    overlap_concepts: _server.List[_server.Dict[str, _server.Any]] = []
    for entry in by_label.values():
        surveys = entry.get('surveys') if isinstance(entry.get('surveys'), dict) else {}
        if len(surveys) < 2:
            continue
        incoming_surveys = [sid for sid in entry.get('incoming_surveys', []) if sid in surveys]
        auto_detected = incoming_surveys[0] if incoming_surveys else sorted(surveys.keys())[0]
        overlap_concepts.append({
            'concept_id': str(entry.get('concept_id') or '').strip(),
            'concept_en': str(entry.get('concept_en') or '').strip(),
            'surveys': dict(surveys),
            'auto_detected': auto_detected,
        })

    overlap_concepts.sort(key=lambda item: _server._concept_sort_key(str(item.get('concept_id') or '')))
    return {'preview': True, 'speaker': speaker, 'overlap_concepts': overlap_concepts}


def _extract_survey_choices(form: _server.Any, speaker: str) -> _server.Optional[_server.Dict[str, str]]:
    raw = _field_text(form, 'survey_choices') or _field_text(form, 'surveyChoices')
    if not raw:
        return None
    try:
        payload = _server.json.loads(raw)
    except _server.json.JSONDecodeError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'survey_choices must be valid JSON') from exc
    if isinstance(payload, dict) and isinstance(payload.get('survey_choices'), dict):
        payload = payload.get('survey_choices')
    if not isinstance(payload, dict):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'survey_choices must be an object')
    speaker_payload = payload.get(speaker)
    choices = speaker_payload if isinstance(speaker_payload, dict) else payload
    clean: _server.Dict[str, str] = {}
    for concept_id, survey_id in choices.items():
        cid = str(concept_id or '').strip()
        sid = normalize_survey_id(survey_id)
        if cid and sid:
            clean[cid] = sid
    return clean or None


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


def _run_onboard_speaker_job(job_id: str, speaker: str, wav_dest: _server.pathlib.Path, csv_dest: _server.Optional[_server.pathlib.Path], comments_csv_dest: _server.Optional[_server.pathlib.Path] = None, survey_choices: _server.Optional[_server.Dict[str, str]] = None) -> None:
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
        if survey_choices:
            update_survey_overlap_state(_server._project_root(), {'speaker_choices': {speaker: survey_choices}})
        _server._set_job_progress(job_id, 90.0, message='Finalizing')
        result: _server.Dict[str, _server.Any] = {'speaker': speaker, 'wavPath': wav_relative, 'csvPath': str(csv_dest.relative_to(_server._project_root())) if csv_dest else None, 'commentsCsvPath': str(comments_csv_dest.relative_to(_server._project_root())) if comments_csv_dest else None, 'annotationPath': str(annotation_path.relative_to(_server._project_root())), 'conceptsAdded': concepts_added, 'conceptTotal': concept_total, 'commentsImported': comments_imported, 'lexemesImported': lexemes_imported}
        complete_message = 'Imported {0} lexemes from {1}'.format(lexemes_imported, csv_dest.name) if lexemes_imported and csv_dest else 'Speaker onboarded'
        _server._set_job_complete(job_id, result, message=complete_message)
    except Exception as exc:
        _server._set_job_error(job_id, str(exc))

def _refresh_source_audio_duration(speaker: str, normalized_path: _server.pathlib.Path) -> bool:
    """Refresh annotation duration from the normalized working WAV.

    Returns True only when the annotation was rewritten. The tolerance avoids
    no-op churn from encoder/decoder duration rounding.
    """
    try:
        import soundfile as sf

        actual_duration = round(float(sf.info(str(normalized_path)).duration), 6)
    except Exception as exc:
        print(
            '[normalize] could not read duration for {0}: {1}'.format(normalized_path, exc),
            file=_server.sys.stderr,
            flush=True,
        )
        return False
    try:
        annotation_path = _server._annotation_read_path_for_speaker(speaker)
    except Exception as exc:
        print(
            '[normalize] could not resolve annotation for {0}: {1}'.format(speaker, exc),
            file=_server.sys.stderr,
            flush=True,
        )
        return False
    if not annotation_path.is_file():
        return False
    annotation = _server._read_json_file(annotation_path, {})
    if not isinstance(annotation, dict):
        return False
    try:
        existing = float(annotation.get('source_audio_duration_sec'))
    except (TypeError, ValueError):
        existing = None
    if existing is not None and abs(existing - actual_duration) < 1.0:
        return False
    annotation['source_audio_duration_sec'] = float(actual_duration)
    _server._write_json_file(annotation_path, annotation)
    canonical_path = _server._annotation_record_path_for_speaker(speaker)
    if canonical_path != annotation_path:
        _server._write_json_file(canonical_path, annotation)
    return True


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
        duration_refreshed = _server._refresh_source_audio_duration(speaker, output_path)
        _server._set_job_progress(job_id, 95.0, message='Finalizing')
        output_relative = str(output_path.relative_to(_server._project_root()))
        result: _server.Dict[str, _server.Any] = {'speaker': speaker, 'sourcePath': source_wav, 'normalizedPath': output_relative, 'sourceAudioDurationRefreshed': duration_refreshed}
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
    if _preview_requested(self, form):
        csv_text = _decode_uploaded_csv(csv_item) if has_csv else ''
        self._send_json(_server.HTTPStatus.OK, _build_onboard_overlap_preview(speaker, csv_text))
        return
    survey_choices = _extract_survey_choices(form, speaker)
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
        if survey_choices:
            job_payload['surveyChoices'] = survey_choices
        job_id = _server._create_job('onboard:speaker', job_payload)
    except _server.JobResourceConflictError as exc:
        raise _server.ApiError(_server.HTTPStatus.CONFLICT, str(exc))
    thread_args = (job_id, speaker, wav_dest, csv_dest, comments_csv_dest, survey_choices) if survey_choices else (job_id, speaker, wav_dest, csv_dest, comments_csv_dest)
    thread = _server.threading.Thread(target=_server._run_onboard_speaker_job, args=thread_args, daemon=True)
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

__all__ = ['_load_cached_suggestions', '_stt_coverage_end_sec', '_emit_stt_summary_log', '_run_stt_job', '_run_stt_job_subprocess_entry', '_run_stt_job_in_subprocess', '_compute_stt', '_parse_concepts_csv', '_merge_concepts_into_root_csv', '_register_speaker_in_project_json', '_run_onboard_speaker_job', '_refresh_source_audio_duration', '_run_normalize_job', '_compute_training_job', '_api_post_onboard_speaker', '_api_post_normalize', '_api_post_onboard_speaker_status', '_api_post_normalize_status', '_api_post_stt_start', '_api_post_stt_status', '_api_post_suggest', '_api_get_spectrogram']

