"""PARSE server route-domain module: annotate."""
from __future__ import annotations

from typing import Callable

import hashlib
import server as _server
from ai.provider import AIProvider
from concept_registry import load_concept_registry, persist_concept_registry, resolve_or_allocate_concept_id


def _release_registered_ipa_aligner() -> None:
    aligner = getattr(_server, '_IPA_ALIGNER', None)
    setattr(_server, '_IPA_ALIGNER', None)
    release = getattr(aligner, 'release', None)
    if callable(release):
        release()


if not callable(_server.__dict__.get('_release_ipa_aligner')):
    setattr(_server, '_release_ipa_aligner', _release_registered_ipa_aligner)


def _annotation_empty_tier(display_order: int) -> _server.Dict[str, _server.Any]:
    return {'type': 'interval', 'display_order': int(display_order), 'intervals': []}

_OPTIONAL_INTERVAL_PASSTHROUGH_FIELDS = (
    'concept_id',
    'import_index',
    'audition_prefix',
    'conceptId',
    'source',
)


def _annotation_sort_intervals(intervals: _server.List[_server.Dict[str, _server.Any]]) -> None:
    # Sorts by (start, end). CSV row order is preserved separately via the
    # `import_index` field on each interval (PR #200); clients that need
    # original CSV order should reconstruct it from import_index, not position.
    intervals.sort(key=lambda interval: (float(interval.get('start', 0.0)), float(interval.get('end', 0.0))))

def _annotation_normalize_interval(raw_interval: _server.Any) -> _server.Optional[_server.Dict[str, _server.Any]]:
    if not isinstance(raw_interval, dict):
        return None
    start = _server._coerce_finite_float(raw_interval.get('start', raw_interval.get('xmin')))
    end = _server._coerce_finite_float(raw_interval.get('end', raw_interval.get('xmax')))
    if start is None or end is None:
        return None
    if end < start:
        return None
    normalized = {'start': float(start), 'end': float(end), 'text': '' if raw_interval.get('text') is None else str(raw_interval.get('text')), 'manuallyAdjusted': bool(raw_interval.get('manuallyAdjusted'))}
    for field in _OPTIONAL_INTERVAL_PASSTHROUGH_FIELDS:
        value = raw_interval.get(field)
        if value is None:
            continue
        if field == 'import_index':
            try:
                normalized[field] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            normalized[field] = str(value)
    return normalized

def _annotation_tier_key(raw_name: _server.Any) -> str:
    tier_name = str(raw_name or '').strip()
    if not tier_name:
        return ''
    lowered = tier_name.lower()
    if lowered in _server.ANNOTATION_TIER_ORDER:
        return lowered
    return tier_name

def _annotation_normalize_tier(raw_tier: _server.Any, default_display_order: int) -> _server.Dict[str, _server.Any]:
    tier_payload = raw_tier if isinstance(raw_tier, dict) else {}
    display_order_raw = _server._coerce_finite_float(tier_payload.get('display_order'))
    if display_order_raw is None or display_order_raw <= 0:
        display_order = int(default_display_order)
    else:
        display_order = int(display_order_raw)
    intervals_raw = tier_payload.get('intervals')
    intervals_out: _server.List[_server.Dict[str, _server.Any]] = []
    if isinstance(intervals_raw, list):
        for raw_interval in intervals_raw:
            interval = _server._annotation_normalize_interval(raw_interval)
            if interval is not None:
                intervals_out.append(interval)
    _server._annotation_sort_intervals(intervals_out)
    return {'type': 'interval', 'display_order': display_order, 'intervals': intervals_out}


def _annotation_normalize_ipa_candidates(raw_candidates: _server.Any) -> _server.Optional[_server.Dict[str, _server.List[_server.Dict[str, _server.Any]]]]:
    """Round-trip IPA candidate sidecars without changing model output text."""
    if not isinstance(raw_candidates, dict):
        return None
    normalized: _server.Dict[str, _server.List[_server.Dict[str, _server.Any]]] = {}
    for raw_key, raw_list in raw_candidates.items():
        if not isinstance(raw_list, list):
            continue
        candidates: _server.List[_server.Dict[str, _server.Any]] = []
        for candidate in raw_list:
            if isinstance(candidate, dict):
                candidates.append(dict(candidate))
        normalized[str(raw_key)] = candidates
    return normalized


def _annotation_normalize_ipa_review(raw_review: _server.Any) -> _server.Optional[_server.Dict[str, _server.Dict[str, _server.Any]]]:
    if not isinstance(raw_review, dict):
        return None
    normalized: _server.Dict[str, _server.Dict[str, _server.Any]] = {}
    for raw_key, review_state in raw_review.items():
        if isinstance(review_state, dict):
            normalized[str(raw_key)] = dict(review_state)
    return normalized


def _annotation_max_end(record: _server.Dict[str, _server.Any]) -> float:
    tiers = record.get('tiers') if isinstance(record, dict) else {}
    if not isinstance(tiers, dict):
        return 0.0
    max_end = 0.0
    for tier in tiers.values():
        if not isinstance(tier, dict):
            continue
        intervals = tier.get('intervals')
        if not isinstance(intervals, list):
            continue
        for raw_interval in intervals:
            interval = _server._annotation_normalize_interval(raw_interval)
            if interval is None:
                continue
            if interval['end'] > max_end:
                max_end = interval['end']
    return max_end

def _annotation_sort_all_intervals(record: _server.Dict[str, _server.Any]) -> None:
    tiers = record.get('tiers')
    if not isinstance(tiers, dict):
        return
    for tier in tiers.values():
        if not isinstance(tier, dict):
            continue
        intervals = tier.get('intervals')
        if isinstance(intervals, list):
            _server._annotation_sort_intervals(intervals)

def _annotation_collect_speaker_intervals(record: _server.Dict[str, _server.Any]) -> _server.List[_server.Dict[str, float]]:
    tiers = record.get('tiers') if isinstance(record, dict) else {}
    if not isinstance(tiers, dict):
        return []
    for tier_key in ('concept', 'ipa', 'ortho'):
        tier = tiers.get(tier_key)
        if not isinstance(tier, dict):
            continue
        intervals = tier.get('intervals')
        if not isinstance(intervals, list):
            continue
        dedupe: _server.Dict[str, bool] = {}
        aligned: _server.List[_server.Dict[str, float]] = []
        for raw_interval in intervals:
            interval = _server._annotation_normalize_interval(raw_interval)
            if interval is None:
                continue
            if not str(interval.get('text') or '').strip():
                continue
            dedupe_key = '{0:.6f}|{1:.6f}'.format(interval['start'], interval['end'])
            if dedupe_key in dedupe:
                continue
            dedupe[dedupe_key] = True
            aligned.append({'start': interval['start'], 'end': interval['end']})
        if aligned:
            return aligned
    speaker_tier = tiers.get('speaker')
    if not isinstance(speaker_tier, dict):
        return []
    fallback_intervals = speaker_tier.get('intervals')
    if not isinstance(fallback_intervals, list):
        return []
    fallback: _server.List[_server.Dict[str, float]] = []
    for raw_interval in fallback_intervals:
        interval = _server._annotation_normalize_interval(raw_interval)
        if interval is None:
            continue
        fallback.append({'start': interval['start'], 'end': interval['end']})
    return fallback

def _offset_detect_payload(*, speaker: str, offset_sec: float, confidence: float, n_matched: int, total_anchors: int, total_segments: int, method: str, spread_sec: float, matches: _server.List[_server.Dict[str, _server.Any]], anchor_distribution: str) -> _server.Dict[str, _server.Any]:
    """Shape the response body for /api/offset/detect{,-from-pair}.

    Direction is reported in plain language so MCP / chat clients can read
    it back to the user without sign confusion. The numeric ``offsetSec``
    is the value to pass to /api/offset/apply unchanged.
    """
    if abs(offset_sec) < 0.001:
        direction = 'none'
        direction_label = 'no shift needed'
    elif offset_sec > 0:
        direction = 'later'
        direction_label = '{0:.3f} s later (toward the end)'.format(offset_sec)
    else:
        direction = 'earlier'
        direction_label = '{0:.3f} s earlier (toward the start)'.format(abs(offset_sec))
    reliable = bool(n_matched >= 3 and confidence >= 0.5 and (spread_sec <= 2.0 or n_matched == 1))
    warnings: _server.List[str] = []
    if n_matched < 3 and method != 'manual_pair':
        warnings.append('Only {0} anchor match{1} were found — apply with caution.'.format(n_matched, '' if n_matched == 1 else 'es'))
    if spread_sec > 2.0:
        warnings.append('Match offsets disagree by ±{0:.2f}s — the detected value may be noisy.'.format(spread_sec))
    if confidence < 0.5 and method != 'manual_pair':
        warnings.append('Low confidence; consider re-running STT or using a manual single-anchor pair.')
    if method == 'bucket_vote':
        warnings.append('Monotonic alignment failed; fell back to bucket vote which is more vulnerable to false matches.')
    return {'speaker': speaker, 'offsetSec': float(offset_sec), 'confidence': float(confidence), 'nAnchors': int(n_matched), 'totalAnchors': int(total_anchors), 'totalSegments': int(total_segments), 'method': method, 'spreadSec': float(spread_sec), 'direction': direction, 'directionLabel': direction_label, 'anchorDistribution': anchor_distribution, 'reliable': reliable, 'warnings': warnings, 'matches': matches}

def _annotation_find_concept_interval(record: _server.Dict[str, _server.Any], concept_id: str) -> _server.Optional[_server.Dict[str, _server.Any]]:
    """Return the first interval whose ``concept_id`` (or text) matches.

    Searches concept tier first (where the id naturally lives), then ortho
    and ipa tiers as fallback for legacy records that stored the concept id
    in the text field.
    """
    if not isinstance(record, dict) or not concept_id:
        return None
    needle = str(concept_id).strip()
    if not needle:
        return None
    tiers = record.get('tiers')
    if not isinstance(tiers, dict):
        return None
    for tier_key in ('concept', 'ortho', 'ipa'):
        tier = tiers.get(tier_key)
        if not isinstance(tier, dict):
            continue
        intervals = tier.get('intervals')
        if not isinstance(intervals, list):
            continue
        for raw in intervals:
            normalized = _server._annotation_normalize_interval(raw)
            if normalized is None:
                continue
            cid = str(raw.get('concept_id') or raw.get('conceptId') or '').strip()
            text = str(normalized.get('text') or '').strip()
            if cid == needle or text == needle:
                return normalized
    return None

def _annotation_offset_anchor_intervals(record: _server.Dict[str, _server.Any]) -> _server.List[_server.Dict[str, _server.Any]]:
    """Return interval dicts (start/end/text) suitable as offset-detection anchors.

    Prefers ``ortho`` and ``ipa`` tiers (transcribed forms that should match
    STT output); falls back to ``concept`` only if neither is populated.
    """
    if not isinstance(record, dict):
        return []
    tiers = record.get('tiers')
    if not isinstance(tiers, dict):
        return []
    for tier_key in ('ortho', 'ipa', 'concept'):
        tier = tiers.get(tier_key)
        if not isinstance(tier, dict):
            continue
        intervals_raw = tier.get('intervals')
        if not isinstance(intervals_raw, list):
            continue
        collected: _server.List[_server.Dict[str, _server.Any]] = []
        for raw in intervals_raw:
            normalized = _server._annotation_normalize_interval(raw)
            if normalized is None:
                continue
            text = str(normalized.get('text') or '').strip()
            if not text:
                continue
            collected.append({'start': normalized['start'], 'end': normalized['end'], 'text': text})
        if collected:
            return collected
    return []

def _annotation_interval_concept_identity(tier_key: str, raw: _server.Dict[str, _server.Any], index: int) -> str:
    for key in ('concept_id', 'conceptId', 'concept', 'conceptKey', 'id'):
        value = raw.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    if tier_key == 'concept':
        text = str(raw.get('text') or '').strip()
        return text or 'concept-index:{0}'.format(index)
    return ''


def _annotation_shift_intervals(record: _server.Dict[str, _server.Any], offset_sec: float) -> _server.Tuple[int, int, int]:
    """Add ``offset_sec`` to every interval's start/end. Negative values clamp to 0.

    Mutates the record in place. Intervals flagged ``manuallyAdjusted`` are
    skipped — once the annotator has locked a lexeme's timing (direct edit or
    a captured anchor pair) a later global shift must not move it again.

    Returns ``(shifted_intervals, skipped_protected, shifted_concepts)``.
    """
    if not isinstance(record, dict):
        return (0, 0, 0)
    tiers = record.get('tiers')
    if not isinstance(tiers, dict):
        return (0, 0, 0)
    shifted = 0
    skipped_protected = 0
    shifted_concept_keys = set()
    for tier_key, tier in tiers.items():
        if not isinstance(tier, dict):
            continue
        intervals = tier.get('intervals')
        if not isinstance(intervals, list):
            continue
        for index, raw in enumerate(intervals):
            if not isinstance(raw, dict):
                continue
            start = _server._coerce_finite_float(raw.get('start', raw.get('xmin')))
            end = _server._coerce_finite_float(raw.get('end', raw.get('xmax')))
            if start is None or end is None:
                continue
            if bool(raw.get('manuallyAdjusted')):
                skipped_protected += 1
                continue
            new_start = max(0.0, float(start) + float(offset_sec))
            new_end = max(new_start, float(end) + float(offset_sec))
            raw['start'] = new_start
            raw['end'] = new_end
            if 'xmin' in raw:
                raw['xmin'] = new_start
            if 'xmax' in raw:
                raw['xmax'] = new_end
            shifted += 1
            concept_identity = _annotation_interval_concept_identity(str(tier_key), raw, index)
            if concept_identity:
                shifted_concept_keys.add(concept_identity)
    _server._annotation_sort_all_intervals(record)
    return (shifted, skipped_protected, len(shifted_concept_keys))

def _stt_cache_path(speaker: str) -> _server.pathlib.Path:
    return _server._project_root() / 'coarse_transcripts' / '{0}.json'.format(speaker)

def _write_stt_cache(
    speaker: str,
    source_wav: str,
    language: _server.Optional[str],
    segments: _server.List[_server.Dict[str, _server.Any]],
    *,
    source: _server.Optional[str] = None,
) -> None:
    speaker_norm = str(speaker or '').strip()
    if not speaker_norm or not isinstance(segments, list) or (not segments):
        return
    cache_path = _server._stt_cache_path(speaker_norm)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload: _server.Dict[str, _server.Any] = {
            'speaker': speaker_norm,
            'source_wav': source_wav,
            'language': language,
            'segments': segments,
        }
        if source:
            payload['source'] = source
        with open(cache_path, 'w', encoding='utf-8') as fh:
            _server.json.dump(payload, fh, ensure_ascii=False)
    except OSError as exc:
        print('[stt] failed to cache segments for {0!r}: {1}'.format(speaker_norm, exc), file=_server.sys.stderr, flush=True)

def _read_stt_cache(speaker: str) -> _server.Optional[_server.List[_server.Dict[str, _server.Any]]]:
    cache_path = _server._stt_cache_path(speaker)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, 'r', encoding='utf-8') as fh:
            data = _server.json.load(fh)
    except (OSError, ValueError):
        return None
    segments = data.get('segments') if isinstance(data, dict) else None
    if not isinstance(segments, list) or not segments:
        return None
    return segments

def _latest_stt_segments_for_speaker(speaker: str) -> _server.Optional[_server.List[_server.Dict[str, _server.Any]]]:
    """Find the most recent completed STT job for ``speaker`` and return its segments.

    Prefers the current session's in-memory job. Falls back to the on-disk
    ``coarse_transcripts/<speaker>.json`` cache so actions like offset-detect
    still work after a server restart.
    """
    speaker_norm = str(speaker or '').strip()
    if not speaker_norm:
        return None
    candidates: _server.List[_server.Tuple[float, _server.List[_server.Dict[str, _server.Any]]]] = []
    with _server._jobs_lock:
        for job in _server._jobs.values():
            if str(job.get('type') or '') != 'stt':
                continue
            if str(job.get('status') or '') != 'complete':
                continue
            meta = job.get('meta') if isinstance(job.get('meta'), dict) else {}
            if str(meta.get('speaker') or '') != speaker_norm:
                continue
            result = job.get('result') if isinstance(job.get('result'), dict) else {}
            segments = result.get('segments')
            if not isinstance(segments, list) or not segments:
                continue
            ts = float(job.get('completed_ts') or job.get('updated_ts') or 0.0)
            candidates.append((ts, _server.copy.deepcopy(segments)))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    return _server._read_stt_cache(speaker_norm)

def _annotation_sync_speaker_tier(record: _server.Dict[str, _server.Any]) -> None:
    if not isinstance(record, dict):
        return
    tiers = record.get('tiers')
    if not isinstance(tiers, dict):
        tiers = {}
        record['tiers'] = tiers
    speaker_tier = tiers.get('speaker')
    if not isinstance(speaker_tier, dict):
        speaker_tier = _server._annotation_empty_tier(_server.ANNOTATION_TIER_ORDER['speaker'])
        tiers['speaker'] = speaker_tier
    speaker_tier['type'] = 'interval'
    speaker_tier['display_order'] = _server.ANNOTATION_TIER_ORDER['speaker']
    duration = _server._coerce_finite_float(record.get('source_audio_duration_sec'))
    if duration is None or duration < 0:
        duration = 0.0
    record['source_audio_duration_sec'] = float(duration)
    speaker_text = str(record.get('speaker') or '').strip()
    aligned_intervals = _server._annotation_collect_speaker_intervals(record)
    speaker_tier['intervals'] = [{'start': interval['start'], 'end': interval['end'], 'text': speaker_text} for interval in aligned_intervals]

def _annotation_touch_metadata(record: _server.Dict[str, _server.Any], preserve_created: bool) -> None:
    metadata = record.get('metadata') if isinstance(record, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
        record['metadata'] = metadata
    if not preserve_created or not str(metadata.get('created') or '').strip():
        metadata['created'] = _server._utc_now_iso()
    metadata['modified'] = _server._utc_now_iso()
    language_code = str(metadata.get('language_code') or '').strip()
    if not language_code:
        metadata['language_code'] = _server._annotation_language_code(record)


def _annotation_enforce_concept_ids(record: _server.Dict[str, _server.Any], speaker: str) -> None:
    tiers = record.get('tiers') if isinstance(record, dict) else {}
    if not isinstance(tiers, dict):
        return
    concept_tier = tiers.get('concept')
    if not isinstance(concept_tier, dict):
        return
    intervals = concept_tier.get('intervals')
    if not isinstance(intervals, list):
        return
    registry = None
    registry_changed = False
    speaker_name = str(speaker or record.get('speaker') or '').strip()
    for index, interval in enumerate(intervals):
        if not isinstance(interval, dict):
            continue
        if str(interval.get('concept_id') or '').strip():
            continue
        text = str(interval.get('text') or '').strip()
        if not text:
            print('[normalize] {0} concept-tier interval {1} has empty text; concept_id left blank'.format(speaker_name, index), file=_server.sys.stderr, flush=True)
            continue
        if registry is None:
            registry = load_concept_registry(_server._project_root())
        concept_id, was_allocated = resolve_or_allocate_concept_id(registry, text)
        if concept_id:
            interval['concept_id'] = concept_id
        registry_changed = registry_changed or was_allocated
    if registry is not None and registry_changed:
        persist_concept_registry(_server._project_root(), registry)


def _annotation_empty_record(speaker: str, source_audio: _server.Optional[str], duration_sec: _server.Optional[float], existing_record: _server.Optional[_server.Dict[str, _server.Any]]) -> _server.Dict[str, _server.Any]:
    now_iso = _server._utc_now_iso()
    speaker_text = str(speaker or '').strip()
    duration = _server._coerce_finite_float(duration_sec)
    if duration is None or duration < 0:
        duration = 0.0
    source_audio_text = str(source_audio or '').strip()
    if not source_audio_text:
        source_audio_text = _server._annotation_primary_source_wav(speaker_text)
    return {'version': 1, 'project_id': _server._annotation_project_id(), 'speaker': speaker_text, 'source_audio': source_audio_text, 'source_audio_duration_sec': float(duration), 'tiers': {'ipa': _server._annotation_empty_tier(_server.ANNOTATION_TIER_ORDER['ipa']), 'ortho': _server._annotation_empty_tier(_server.ANNOTATION_TIER_ORDER['ortho']), 'concept': _server._annotation_empty_tier(_server.ANNOTATION_TIER_ORDER['concept']), 'speaker': _server._annotation_empty_tier(_server.ANNOTATION_TIER_ORDER['speaker'])}, 'confirmed_anchors': {}, 'metadata': {'language_code': _server._annotation_language_code(existing_record), 'created': now_iso, 'modified': now_iso}}


def _annotation_normalize_concept_tags(raw_tags: _server.Any) -> _server.Dict[str, _server.List[str]]:
    if not isinstance(raw_tags, dict):
        return {}
    clean_tags: _server.Dict[str, _server.List[str]] = {}
    for raw_concept_id, raw_tag_ids in raw_tags.items():
        if not isinstance(raw_tag_ids, list):
            continue
        tag_ids: _server.List[str] = []
        seen: set[str] = set()
        for raw_tag_id in raw_tag_ids:
            if not isinstance(raw_tag_id, str) or raw_tag_id in seen:
                continue
            seen.add(raw_tag_id)
            tag_ids.append(raw_tag_id)
        if tag_ids:
            clean_tags[str(raw_concept_id)] = tag_ids
    return clean_tags

def _annotation_upsert_interval(intervals: _server.List[_server.Dict[str, _server.Any]], start: float, end: float, text: str) -> None:
    for interval in intervals:
        if abs(float(interval.get('start', 0.0)) - start) <= _server.ANNOTATION_MATCH_EPSILON and abs(float(interval.get('end', 0.0)) - end) <= _server.ANNOTATION_MATCH_EPSILON:
            interval['text'] = text
            return
    intervals.append({'start': start, 'end': end, 'text': text})
    _server._annotation_sort_intervals(intervals)

def _normalize_flat_annotation_entry(raw_entry: _server.Any, defaults: _server.Dict[str, _server.Any]) -> _server.Optional[_server.Dict[str, _server.Any]]:
    if not isinstance(raw_entry, dict):
        return None
    start = _server._coerce_finite_float(raw_entry.get('startSec', raw_entry.get('start_sec', raw_entry.get('start', raw_entry.get('xmin')))))
    end = _server._coerce_finite_float(raw_entry.get('endSec', raw_entry.get('end_sec', raw_entry.get('end', raw_entry.get('xmax')))))
    if start is None or end is None or end < start:
        return None
    concept_text = ''
    for key in ('concept', 'concept_text', 'conceptLabel', 'concept_id', 'conceptId'):
        value = raw_entry.get(key)
        if value is not None:
            concept_text = str(value)
            break
    concept_id_raw = raw_entry.get('conceptId')
    if concept_id_raw is None:
        concept_id_raw = raw_entry.get('concept_id')
    concept_id = str(concept_id_raw) if concept_id_raw is not None else _server._normalize_concept_id(concept_text)
    source_wav = raw_entry.get('sourceWav')
    if source_wav is None:
        source_wav = raw_entry.get('source_wav')
    return {'speaker': str(raw_entry.get('speaker') or defaults.get('speaker') or '').strip(), 'conceptId': str(concept_id or '').strip(), 'concept': concept_text, 'startSec': float(start), 'endSec': float(end), 'ipa': '' if raw_entry.get('ipa') is None else str(raw_entry.get('ipa')), 'ortho': '' if raw_entry.get('ortho') is None else str(raw_entry.get('ortho')), 'sourceWav': str(source_wav or defaults.get('sourceWav') or '').strip()}

def _annotation_record_from_flat_entries(raw_entries: _server.Any, speaker_hint: str, source_wav_hint: str) -> _server.Dict[str, _server.Any]:
    speaker = str(speaker_hint or '').strip()
    source_wav = str(source_wav_hint or '').strip() or _server._annotation_primary_source_wav(speaker)
    record = _server._annotation_empty_record(speaker, source_wav, 0.0, None)
    entries = raw_entries if isinstance(raw_entries, list) else []
    for raw_entry in entries:
        normalized = _server._normalize_flat_annotation_entry(raw_entry, {'speaker': speaker, 'sourceWav': source_wav})
        if normalized is None:
            continue
        if normalized['sourceWav'] and (not str(record.get('source_audio') or '').strip()):
            record['source_audio'] = normalized['sourceWav']
        if normalized['endSec'] > float(record.get('source_audio_duration_sec') or 0.0):
            record['source_audio_duration_sec'] = float(normalized['endSec'])
        concept_text = str(normalized.get('concept') or '').strip() or str(normalized.get('conceptId') or '').strip()
        _server._annotation_upsert_interval(record['tiers']['ipa']['intervals'], normalized['startSec'], normalized['endSec'], str(normalized.get('ipa') or ''))
        _server._annotation_upsert_interval(record['tiers']['ortho']['intervals'], normalized['startSec'], normalized['endSec'], str(normalized.get('ortho') or ''))
        _server._annotation_upsert_interval(record['tiers']['concept']['intervals'], normalized['startSec'], normalized['endSec'], concept_text)
    _server._annotation_sync_speaker_tier(record)
    _annotation_enforce_concept_ids(record, speaker)
    _server._annotation_touch_metadata(record, preserve_created=True)
    return record

def _normalize_annotation_record(raw_record: _server.Any, speaker_hint: str) -> _server.Dict[str, _server.Any]:
    speaker_from_hint = str(speaker_hint or '').strip()
    if isinstance(raw_record, list):
        return _server._annotation_record_from_flat_entries(raw_record, speaker_from_hint, '')
    if not isinstance(raw_record, dict):
        source_audio = _server._annotation_primary_source_wav(speaker_from_hint)
        source_duration = _server._annotation_source_duration(speaker_from_hint, source_audio)
        return _server._annotation_empty_record(speaker_from_hint, source_audio, source_duration or 0.0, None)
    annotations_block = raw_record.get('annotations')
    if isinstance(annotations_block, list):
        speaker_from_record = str(raw_record.get('speaker') or speaker_from_hint).strip()
        source_from_record = str(raw_record.get('source_audio') or raw_record.get('sourceWav') or raw_record.get('source_wav') or '').strip()
        return _server._annotation_record_from_flat_entries(annotations_block, speaker_from_record, source_from_record)
    speaker = str(raw_record.get('speaker') or speaker_from_hint).strip()
    source_audio = str(raw_record.get('source_audio') or raw_record.get('sourceWav') or raw_record.get('source_wav') or '').strip()
    source_duration = _server._coerce_finite_float(raw_record.get('source_audio_duration_sec'))
    if source_duration is None or source_duration < 0:
        source_duration = _server._annotation_source_duration(speaker, source_audio) or 0.0
    normalized = _server._annotation_empty_record(speaker, source_audio, source_duration, raw_record)
    normalized['version'] = 1
    project_id = str(raw_record.get('project_id') or '').strip()
    normalized['project_id'] = project_id or _server._annotation_project_id()
    tiers_in = raw_record.get('tiers')
    if not isinstance(tiers_in, dict):
        tiers_in = {}
    next_custom_display_order = max(_server.ANNOTATION_TIER_ORDER.values()) + 1
    for original_key, raw_tier in tiers_in.items():
        tier_key = _server._annotation_tier_key(original_key)
        if not tier_key:
            continue
        default_order = _server.ANNOTATION_TIER_ORDER.get(tier_key, next_custom_display_order)
        tier = _server._annotation_normalize_tier(raw_tier, default_order)
        normalized['tiers'][tier_key] = tier
        if tier_key not in _server.ANNOTATION_TIER_ORDER:
            next_custom_display_order = max(next_custom_display_order, int(tier.get('display_order', default_order)) + 1)
    for tier_key, display_order in _server.ANNOTATION_TIER_ORDER.items():
        if tier_key not in normalized['tiers']:
            normalized['tiers'][tier_key] = _server._annotation_empty_tier(display_order)
    raw_anchors = raw_record.get('confirmed_anchors')
    if isinstance(raw_anchors, dict):
        clean_anchors: _server.Dict[str, _server.Any] = {}
        for key, val in raw_anchors.items():
            if not isinstance(val, dict):
                continue
            start = _server._coerce_finite_float(val.get('start'))
            end = _server._coerce_finite_float(val.get('end'))
            if start is None or end is None or end < start:
                continue
            entry: _server.Dict[str, _server.Any] = {'start': float(start), 'end': float(end)}
            for field in ('source', 'confirmed_at', 'matched_text', 'matched_variant'):
                if field in val and val[field] is not None:
                    entry[field] = val[field]
            variants_used = val.get('variants_used')
            if isinstance(variants_used, list):
                entry['variants_used'] = [str(x) for x in variants_used]
            clean_anchors[str(key)] = entry
        normalized['confirmed_anchors'] = clean_anchors
    raw_concept_tags = raw_record.get('concept_tags')
    if isinstance(raw_concept_tags, dict):
        clean_concept_tags = _annotation_normalize_concept_tags(raw_concept_tags)
        if clean_concept_tags:
            normalized['concept_tags'] = clean_concept_tags
    raw_ipa_candidates = raw_record.get('ipa_candidates')
    clean_ipa_candidates = _annotation_normalize_ipa_candidates(raw_ipa_candidates)
    if clean_ipa_candidates is not None:
        normalized['ipa_candidates'] = clean_ipa_candidates
    raw_ipa_review = raw_record.get('ipa_review')
    clean_ipa_review = _annotation_normalize_ipa_review(raw_ipa_review)
    if clean_ipa_review is not None:
        normalized['ipa_review'] = clean_ipa_review
    metadata_in = raw_record.get('metadata')
    if not isinstance(metadata_in, dict):
        metadata_in = {}
    now_iso = _server._utc_now_iso()
    language_code = str(metadata_in.get('language_code') or _server._annotation_language_code(raw_record) or 'und').strip()
    if not language_code:
        language_code = 'und'
    normalized['metadata'] = {'language_code': language_code, 'created': str(metadata_in.get('created') or now_iso), 'modified': str(metadata_in.get('modified') or now_iso)}
    max_end = _server._annotation_max_end(normalized)
    if max_end > float(normalized.get('source_audio_duration_sec') or 0.0):
        normalized['source_audio_duration_sec'] = float(max_end)
    source_index_duration = _server._annotation_source_duration(speaker, str(normalized.get('source_audio') or ''))
    if source_index_duration is not None and source_index_duration > float(normalized.get('source_audio_duration_sec') or 0.0):
        normalized['source_audio_duration_sec'] = float(source_index_duration)
    if not str(normalized.get('source_audio') or '').strip():
        normalized['source_audio'] = _server._annotation_primary_source_wav(speaker)
    _annotation_enforce_concept_ids(normalized, speaker)
    _server._annotation_sync_speaker_tier(normalized)
    _server._annotation_sort_all_intervals(normalized)
    return normalized

def _normalize_speaker_id(raw_speaker: _server.Any) -> str:
    speaker = str(raw_speaker or '').strip()
    if not speaker:
        raise ValueError('speaker is required')
    if speaker in {'.', '..'}:
        raise ValueError('Invalid speaker id')
    if '\x00' in speaker:
        raise ValueError('speaker contains an invalid null byte')
    if '/' in speaker or '\\' in speaker:
        raise ValueError('speaker must not contain path separators')
    if len(speaker) > 200:
        raise ValueError('speaker is too long')
    return speaker

def _annotation_record_relative_path(speaker: str) -> _server.pathlib.Path:
    return _server.pathlib.Path('annotations') / '{0}{1}'.format(speaker, _server.ANNOTATION_FILENAME_SUFFIX)

def _annotation_legacy_record_relative_path(speaker: str) -> _server.pathlib.Path:
    return _server.pathlib.Path('annotations') / '{0}{1}'.format(speaker, _server.ANNOTATION_LEGACY_FILENAME_SUFFIX)

def _annotation_resolve_relative_path(relative_path: _server.pathlib.Path) -> _server.pathlib.Path:
    annotations_dir = _server._annotations_dir_path()
    candidate = _server._resolve_project_path(str(relative_path))
    try:
        candidate.relative_to(annotations_dir)
    except ValueError as exc:
        raise ValueError('Annotation path escapes annotations directory') from exc
    return candidate

def _annotation_record_path_for_speaker(speaker: str) -> _server.pathlib.Path:
    return _server._annotation_resolve_relative_path(_server._annotation_record_relative_path(speaker))

def _annotation_legacy_record_path_for_speaker(speaker: str) -> _server.pathlib.Path:
    return _server._annotation_resolve_relative_path(_server._annotation_legacy_record_relative_path(speaker))

def _annotation_read_path_for_speaker(speaker: str) -> _server.pathlib.Path:
    canonical_path = _server._annotation_record_path_for_speaker(speaker)
    if canonical_path.is_file():
        return canonical_path
    legacy_path = _server._annotation_legacy_record_path_for_speaker(speaker)
    if legacy_path.is_file():
        return legacy_path
    return canonical_path

def _annotation_payload_from_request_body(raw_payload: _server.Any) -> _server.Any:
    if isinstance(raw_payload, list):
        return raw_payload
    if isinstance(raw_payload, dict):
        annotation_candidate = raw_payload.get('annotation')
        if isinstance(annotation_candidate, (dict, list)):
            return annotation_candidate
        record_candidate = raw_payload.get('record')
        if isinstance(record_candidate, (dict, list)):
            return record_candidate
        return raw_payload
    raise ValueError('Annotation payload must be a JSON object or array')

def _pipeline_audio_path_for_speaker(speaker: str) -> _server.pathlib.Path:
    """Resolve the best audio file to feed a Whisper-family model for a speaker.

    Prefers the normalized working copy under ``audio/working/<speaker>/`` if it
    exists; otherwise falls back to the raw source recording recorded in the
    annotation's ``source_audio`` field. Raises ``FileNotFoundError`` if neither
    is reachable.
    """
    annotation_path = _server._annotation_read_path_for_speaker(speaker)
    if not annotation_path.is_file():
        raise RuntimeError('No annotation found for speaker {0!r}'.format(speaker))
    record = _server._read_json_file(annotation_path, {})
    source_rel = ''
    if isinstance(record, dict):
        source_rel = str(record.get('source_audio') or record.get('source_wav') or '').strip()
    if not source_rel:
        source_rel = _server._annotation_primary_source_wav(speaker)
    if not source_rel:
        raise RuntimeError('No source_audio on annotation for {0!r}; import or onboard the speaker first'.format(speaker))
    source_path = _server._resolve_project_path(source_rel)
    working_dir = _server._project_root() / 'audio' / 'working' / speaker
    normalized_path = _server.build_normalized_output_path(source_path, working_dir)
    if normalized_path.exists():
        return normalized_path
    if source_path.exists():
        return source_path
    raise FileNotFoundError('Neither normalized ({0}) nor source audio ({1}) exists for {2!r}'.format(normalized_path, source_path, speaker))

def _audio_duration_sec(path: _server.pathlib.Path) -> _server.Optional[float]:
    """Best-effort audio duration in seconds.

    Reads the WAV RIFF header via the stdlib ``wave`` module — no optional
    deps, no decode overhead. Returns ``None`` when the file is missing,
    unreadable, or not a standard PCM WAV (the caller falls back to the
    annotation's ``source_audio_duration_sec`` hint).
    """
    try:
        if not path.is_file():
            return None
        import wave
        with wave.open(str(path), 'rb') as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if not rate:
                return None
            return float(frames) / float(rate)
    except Exception:
        return None

def _tier_coverage(intervals: _server.Any, duration_sec: _server.Optional[float]) -> _server.Dict[str, _server.Any]:
    """Summarise how much of a file a tier's intervals cover.

    Returns a dict with ``coverage_start_sec``, ``coverage_end_sec``,
    ``coverage_fraction`` (None when duration is unknown), and
    ``full_coverage`` (None when duration is unknown, else bool).

    This is the signal that answers "was the whole WAV processed, or just
    the slice where pre-existing concept timestamps happened to live?"
    Non-empty text is required — empty intervals don't count as coverage.
    """
    coverage_start: _server.Optional[float] = None
    coverage_end: _server.Optional[float] = None
    if isinstance(intervals, list):
        for iv in intervals:
            if not isinstance(iv, dict):
                continue
            if not str(iv.get('text') or '').strip():
                continue
            try:
                start = float(iv.get('start') or 0.0)
                end = float(iv.get('end') or start)
            except (TypeError, ValueError):
                continue
            if coverage_start is None or start < coverage_start:
                coverage_start = start
            if coverage_end is None or end > coverage_end:
                coverage_end = end
    fraction: _server.Optional[float] = None
    full: _server.Optional[bool] = None
    if duration_sec is not None and duration_sec > 0 and (coverage_end is not None):
        fraction = max(0.0, min(1.0, coverage_end / duration_sec))
        full = bool(fraction >= _server._COVERAGE_FRACTION_THRESHOLD or duration_sec - coverage_end < _server._COVERAGE_ABSOLUTE_TOLERANCE_SEC)
    elif duration_sec is not None and duration_sec > 0 and (coverage_end is None):
        fraction = 0.0
        full = False
    return {'coverage_start_sec': coverage_start, 'coverage_end_sec': coverage_end, 'coverage_fraction': fraction, 'full_coverage': full}

def _pipeline_state_for_speaker(speaker: str) -> _server.Dict[str, _server.Any]:
    """Return what's already been done for a speaker, per pipeline step.

    Shape (per step)::

        {
          "done": true,            # tier has ≥1 non-empty interval (or normalize WAV exists)
          "intervals": 84,         # or "segments" for stt, "path" for normalize
          "can_run": true,         # step can be invoked right now
          "reason": null,          # populated when can_run is false

          # Full-file coverage (new — the "whole WAV processed?" signal):
          "coverage_start_sec": 0.12,   # first non-empty interval start
          "coverage_end_sec": 351.44,   # last non-empty interval end
          "coverage_fraction": 0.98,    # coverage_end / duration
          "full_coverage": true         # true when coverage spans ≥95% OR
                                        # within 3s of the audio end
        }

    Top-level adds ``duration_sec`` so callers can reason about absolute
    coverage.

    ``done`` is a cheap "has any data?" signal — useful for the UI's
    "will overwrite" warning. ``full_coverage`` is the signal an agent
    should check before declaring the step truly complete: a tier with
    128 intervals that cover only the first 30 seconds of a 6-minute
    recording reports ``done=True`` + ``full_coverage=False``, and the
    tier should be re-run.

    ``can_run`` is computed against the *current* filesystem; for a
    batch that runs multiple steps, ``ipa.can_run`` may be false today
    but will succeed after the ORTH step in the same batch runs.
    """
    speaker_norm = _server._normalize_speaker_id(speaker)
    result: _server.Dict[str, _server.Any] = {'speaker': speaker_norm}
    try:
        annotation_path = _server._annotation_read_path_for_speaker(speaker_norm)
        record = _server._read_json_file(annotation_path, {}) if annotation_path.is_file() else {}
    except Exception:
        record = {}
    has_annotation = isinstance(record, dict) and bool(record)
    source_rel = ''
    if isinstance(record, dict):
        source_rel = str(record.get('source_audio') or record.get('source_wav') or '').strip()
    source_path: _server.Optional[_server.pathlib.Path] = None
    source_exists = False
    normalized_path: _server.Optional[_server.pathlib.Path] = None
    normalized_exists = False
    if source_rel:
        try:
            source_path = _server._resolve_project_path(source_rel)
            source_exists = source_path.exists()
            working_dir = _server._project_root() / 'audio' / 'working' / speaker_norm
            normalized_path = _server.build_normalized_output_path(source_path, working_dir)
            normalized_exists = normalized_path.exists()
        except Exception:
            pass
    duration_sec: _server.Optional[float] = None
    for candidate in (normalized_path, source_path):
        if candidate is not None and candidate.is_file():
            duration_sec = _server._audio_duration_sec(candidate)
            if duration_sec:
                break
    if duration_sec is None and isinstance(record, dict):
        meta_dur = record.get('source_audio_duration_sec')
        try:
            meta_float = float(meta_dur) if meta_dur is not None else None
        except (TypeError, ValueError):
            meta_float = None
        if meta_float and meta_float > 0:
            duration_sec = meta_float
    result['duration_sec'] = duration_sec
    normalize_info: _server.Dict[str, _server.Any] = {'done': normalized_exists, 'path': str(normalized_path.relative_to(_server._project_root())) if normalized_exists and normalized_path is not None else None, 'can_run': False, 'reason': None}
    if not has_annotation:
        normalize_info['reason'] = 'No annotation for speaker'
    elif not source_rel:
        normalize_info['reason'] = 'No source_audio on annotation'
    elif not source_exists:
        normalize_info['reason'] = 'Source audio not found: {0}'.format(source_rel)
    else:
        normalize_info['can_run'] = True
    result['normalize'] = normalize_info
    cached_stt = _server._latest_stt_segments_for_speaker(speaker_norm)
    stt_info: _server.Dict[str, _server.Any] = {'done': bool(cached_stt), 'segments': len(cached_stt) if cached_stt else 0, 'can_run': False, 'reason': None}
    stt_info.update(_server._tier_coverage(cached_stt, duration_sec))
    if not has_annotation:
        stt_info['reason'] = 'No annotation for speaker'
    elif not (normalized_exists or source_exists):
        stt_info['reason'] = 'No audio file reachable (neither normalized nor source exists)'
    else:
        stt_info['can_run'] = True
    result['stt'] = stt_info
    tiers = {}
    if isinstance(record, dict):
        tiers = record.get('tiers') if isinstance(record.get('tiers'), dict) else {}

    def _non_empty_count(tier_name: str) -> int:
        tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
        if not isinstance(tier, dict):
            return 0
        intervals = tier.get('intervals') or []
        if not isinstance(intervals, list):
            return 0
        return sum((1 for iv in intervals if isinstance(iv, dict) and str(iv.get('text') or '').strip()))

    def _tier_intervals(tier_name: str) -> _server.Any:
        tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
        return tier.get('intervals') if isinstance(tier, dict) else None
    ortho_intervals = _tier_intervals('ortho')
    ipa_intervals = _tier_intervals('ipa')
    ortho_count = _non_empty_count('ortho')
    ipa_count = _non_empty_count('ipa')
    ortho_info: _server.Dict[str, _server.Any] = {'done': ortho_count > 0, 'intervals': ortho_count, 'can_run': False, 'reason': None}
    ortho_info.update(_server._tier_coverage(ortho_intervals, duration_sec))
    if not has_annotation:
        ortho_info['reason'] = 'No annotation for speaker'
    elif not (normalized_exists or source_exists):
        ortho_info['reason'] = 'No audio file reachable (neither normalized nor source exists)'
    else:
        ortho_info['can_run'] = True
    result['ortho'] = ortho_info
    ipa_info: _server.Dict[str, _server.Any] = {'done': ipa_count > 0, 'intervals': ipa_count, 'can_run': False, 'reason': None}
    ipa_info.update(_server._tier_coverage(ipa_intervals, duration_sec))
    if not has_annotation:
        ipa_info['reason'] = 'No annotation for speaker'
    elif ortho_count == 0:
        ipa_info['reason'] = 'No ortho intervals yet — run ORTH first (or include it in this batch)'
    else:
        ipa_info['can_run'] = True
    result['ipa'] = ipa_info
    return result

def _ortho_tier2_align_to_words(audio_path: _server.pathlib.Path, segments: _server.List[_server.Dict[str, _server.Any]]) -> _server.List[_server.Dict[str, _server.Any]]:
    """Run Tier-2 forced alignment on ORTH segments, returning a flat word tier.

    Takes the full raw segment list (with Whisper ``words[]`` per segment)
    and returns a flat sorted list of ``{start, end, text, confidence,
    source}`` dicts suitable for ``tiers.ortho_words.intervals``.

    Any exception is logged and an empty list is returned — alignment is a
    refinement pass, not a gate; the coarse ortho tier has already been
    written by the caller.
    """
    if not segments:
        return []
    has_any_words = any((seg.get('words') for seg in segments))
    if not has_any_words:
        print('[ORTH] Tier-2 skipped: no word-level timestamps on any segment', file=_server.sys.stderr)
        return []
    try:
        from ai.forced_align import align_segments
    except Exception as exc:
        print('[ORTH] Tier-2 import failed: {0}'.format(exc), file=_server.sys.stderr)
        return []
    try:
        aligned = align_segments(audio_path=audio_path, segments=segments)
    except Exception as exc:
        print('[ORTH] Tier-2 alignment failed: {0}'.format(exc), file=_server.sys.stderr)
        return []
    flat: _server.List[_server.Dict[str, _server.Any]] = []
    for seg_words in aligned:
        for word in seg_words or []:
            text = str(word.get('word', '') or '').strip()
            if not text:
                continue
            try:
                start = float(word.get('start', 0.0) or 0.0)
                end = float(word.get('end', start) or start)
            except (TypeError, ValueError):
                continue
            if end < start:
                continue
            interval: _server.Dict[str, _server.Any] = {'start': start, 'end': end, 'text': text, 'source': 'forced_align'}
            conf = word.get('confidence')
            if conf is not None:
                try:
                    interval['confidence'] = float(conf)
                except (TypeError, ValueError):
                    pass
            flat.append(interval)
    flat.sort(key=lambda iv: (float(iv['start']), float(iv['end'])))
    return flat


_CONCEPT_COMPUTE_RUN_MODES = {'full', 'concept-windows', 'edited-only'}


def _transcription_language_from_payload_or_annotation(
    payload: _server.Dict[str, _server.Any],
    annotation: _server.Dict[str, _server.Any],
    *,
    speaker: str,
    step: str,
) -> _server.Optional[str]:
    """Resolve Whisper language with annotation metadata as a safe fallback.

    PARSE compute payloads may omit ``language``. For fieldwork corpora whose
    annotations already record ``metadata.language_code`` (for example Fail01 →
    ``ku``), forwarding that code is safer than asking Whisper to auto-detect a
    short Kurdish clip.
    """
    raw_language = payload.get('language') if isinstance(payload, dict) else None
    if isinstance(raw_language, str) and raw_language.strip():
        return raw_language.strip()

    metadata = annotation.get('metadata') if isinstance(annotation, dict) else None
    meta_language = metadata.get('language_code') if isinstance(metadata, dict) else None
    if isinstance(meta_language, str):
        language_code = meta_language.strip()
        if language_code and language_code.lower() != 'und':
            return language_code

    print(
        '[{0}][WARN] no payload.language or annotation metadata.language_code for speaker={1!r}; using Whisper auto-detect'.format(
            str(step or 'transcription').upper(),
            speaker,
        ),
        file=_server.sys.stderr,
        flush=True,
    )
    return None


def _set_compute_progress(job_id: str, progress: float, **kwargs: _server.Any) -> None:
    try:
        _server._set_job_progress(job_id, progress, **kwargs)
    except RecursionError:
        # Direct unit tests can reach annotate exports before the jobs-route
        # progress implementation replaces server.py's lazy wrapper. Progress is
        # observability-only, so keep compute behavior deterministic.
        return


def _normalize_compute_run_mode(raw_value: _server.Any) -> str:
    value = str(raw_value or 'full').strip().lower().replace('_', '-')
    if not value:
        value = 'full'
    if value not in _CONCEPT_COMPUTE_RUN_MODES:
        raise RuntimeError("run_mode must be one of 'full', 'concept-windows', or 'edited-only'")
    return value


def _payload_concept_ids(payload: _server.Dict[str, _server.Any]) -> _server.Optional[_server.List[str]]:
    raw = payload.get('concept_ids')
    if raw is None:
        raw = payload.get('conceptIds')
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise RuntimeError('concept_ids must be a list of strings')
    ids: _server.List[str] = []
    for item in raw:
        concept_id = str(item or '').strip()
        if concept_id and concept_id not in ids:
            ids.append(concept_id)
    return ids


def _concept_id_from_interval(interval: _server.Dict[str, _server.Any]) -> str:
    for key in ('conceptId', 'concept_id', 'id', 'text'):
        raw = interval.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return ''


def _ipa_candidate_key(interval: _server.Dict[str, _server.Any], tier: str, interval_index: int) -> str:
    concept_id = ''
    for key in ('conceptId', 'concept_id', 'id'):
        raw = interval.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            concept_id = value
            break
    if not concept_id and tier == 'concept':
        concept_id = str(interval.get('text') or '').strip()
    if not concept_id:
        concept_id = str(interval_index)
    return '{0}::{1}::{2}'.format(concept_id, tier, interval_index)


def _ipa_candidate_from_structured(structured: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    raw_value = structured.get('raw_ipa')
    raw_ipa = raw_value if isinstance(raw_value, str) else str(raw_value or '')
    decoded_at = str(structured.get('decoded_at') or _server._utc_now_iso())
    digest = hashlib.sha256((raw_ipa + decoded_at).encode('utf-8')).hexdigest()[:8]
    return {
        'candidate_id': 'cand_xlsr_{0}'.format(digest),
        'model': str(structured.get('model') or 'wav2vec2-xlsr-53-espeak-cv-ft'),
        'model_version': str(structured.get('model_version') or 'facebook/wav2vec2-xlsr-53-espeak-cv-ft'),
        'raw_ipa': raw_ipa,
        'decoded_at': decoded_at,
        'timing_basis': 'audition_cue',
        'confidence': None,
    }


def _transcribe_ipa_window_structured(provider: _server.Any, window: _server.Any) -> _server.Dict[str, _server.Any]:
    structured_fn = getattr(provider, 'transcribe_window_structured', None)
    if callable(structured_fn):
        structured = structured_fn(window)
        if isinstance(structured, dict):
            return dict(structured)
    raw_ipa = provider.transcribe_window(window)
    return {
        'raw_ipa': raw_ipa,
        'model': 'wav2vec2-xlsr-53-espeak-cv-ft',
        'model_version': 'facebook/wav2vec2-xlsr-53-espeak-cv-ft',
        'decoded_at': _server._utc_now_iso(),
    }


def _annotation_append_ipa_candidate(annotation: _server.Dict[str, _server.Any], key: str, candidate: _server.Dict[str, _server.Any]) -> None:
    candidates = annotation.get('ipa_candidates')
    if not isinstance(candidates, dict):
        candidates = {}
        annotation['ipa_candidates'] = candidates
    candidate_list = candidates.get(key)
    if not isinstance(candidate_list, list):
        candidate_list = []
        candidates[key] = candidate_list
    candidate_list.append(candidate)


def _concept_intervals_for_run_mode(
    annotation: _server.Dict[str, _server.Any],
    run_mode: str,
    concept_ids: _server.Optional[_server.Sequence[str]] = None,
) -> _server.List[_server.Dict[str, _server.Any]]:
    tiers = annotation.get('tiers') if isinstance(annotation.get('tiers'), dict) else {}
    concept_tier = tiers.get('concept') if isinstance(tiers.get('concept'), dict) else None
    raw_intervals = concept_tier.get('intervals') if concept_tier else []
    allowed = set(str(item or '').strip() for item in (concept_ids or []) if str(item or '').strip())
    selected: _server.List[_server.Dict[str, _server.Any]] = []
    for interval in raw_intervals or []:
        if not isinstance(interval, dict):
            continue
        if run_mode == 'edited-only' and not bool(interval.get('manuallyAdjusted')):
            continue
        concept_id = _concept_id_from_interval(interval)
        if allowed and concept_id not in allowed:
            continue
        try:
            start_sec = float(interval.get('start', 0.0) or 0.0)
            end_sec = float(interval.get('end', start_sec) or start_sec)
        except (TypeError, ValueError):
            continue
        if end_sec <= start_sec:
            continue
        copied = dict(interval)
        copied['start'] = start_sec
        copied['end'] = end_sec
        if concept_id:
            copied['conceptId'] = concept_id
        selected.append(copied)
    selected.sort(key=lambda iv: (float(iv.get('start', 0.0) or 0.0), float(iv.get('end', 0.0) or 0.0)))
    return selected


def _affected_concepts_payload(concept_intervals: _server.Sequence[_server.Dict[str, _server.Any]]) -> _server.List[_server.Dict[str, _server.Any]]:
    affected: _server.List[_server.Dict[str, _server.Any]] = []
    for interval in concept_intervals:
        if not isinstance(interval, dict):
            continue
        try:
            start_sec = float(interval.get('start', 0.0) or 0.0)
            end_sec = float(interval.get('end', start_sec) or start_sec)
        except (TypeError, ValueError):
            continue
        affected.append({'concept_id': _concept_id_from_interval(interval), 'start': start_sec, 'end': end_sec})
    return affected


def _concept_window_no_op_result(speaker: str, run_mode: str, step: str, reason: str) -> _server.Dict[str, _server.Any]:
    return {
        'speaker': speaker,
        'step': step,
        'run_mode': run_mode,
        'skipped': True,
        'no_op': True,
        'concept_windows': 0,
        'affected_concepts': [],
        'reason': reason,
    }


def _concept_windows_empty_reason(run_mode: str, concept_ids: _server.Optional[_server.Sequence[str]]) -> str:
    if run_mode == 'edited-only':
        return 'No edited concepts matched the requested scope.'
    if concept_ids:
        return 'No concept intervals matched the requested concept_ids.'
    return 'No concept intervals are available for concept-windowed compute.'


def _interval_overlaps_any_window(interval: _server.Dict[str, _server.Any], windows: _server.Sequence[_server.Dict[str, _server.Any]]) -> bool:
    try:
        start_sec = float(interval.get('start', 0.0) or 0.0)
        end_sec = float(interval.get('end', start_sec) or start_sec)
    except (TypeError, ValueError):
        return False
    for window in windows:
        try:
            win_start = float(window.get('start', 0.0) or 0.0)
            win_end = float(window.get('end', win_start) or win_start)
        except (TypeError, ValueError):
            continue
        if start_sec < win_end and end_sec > win_start:
            return True
    return False


def _merge_concept_window_rows(
    existing: _server.Sequence[_server.Dict[str, _server.Any]],
    replacements: _server.Sequence[_server.Dict[str, _server.Any]],
    concept_windows: _server.Sequence[_server.Dict[str, _server.Any]],
) -> _server.List[_server.Dict[str, _server.Any]]:
    kept = [dict(row) for row in existing if isinstance(row, dict) and not _interval_overlaps_any_window(row, concept_windows)]
    combined = kept + [dict(row) for row in replacements if isinstance(row, dict)]
    combined.sort(key=lambda iv: (float(iv.get('start', 0.0) or 0.0), float(iv.get('end', 0.0) or 0.0)))
    return combined


def _run_step_on_concept_windows(
    audio_path: _server.pathlib.Path,
    concept_intervals: _server.List[_server.Dict[str, _server.Any]],
    provider: _server.Any,
    step: str,
    job_id: _server.Optional[str],
    *,
    language: _server.Optional[str] = None,
    pad_sec: float = 0.8,
    should_cancel: _server.Optional[Callable[[], bool]] = None,
) -> _server.List[_server.Dict[str, _server.Any]]:
    """Run one provider over ±pad_sec short clips around concept intervals.

    The emitted rows keep the concept interval's exact start/end bounds while the
    model receives a padded clip for acoustic context. ``step`` is one of
    ``stt``, ``ortho``, ``ortho_refine``, or ``ipa``.
    """
    if not concept_intervals:
        return []
    step_name = str(step or '').strip().lower()
    if step_name not in {'stt', 'ortho', 'ortho_refine', 'ipa'}:
        raise RuntimeError('Unsupported concept-window step: {0}'.format(step))
    try:
        from ai.forced_align import _load_audio_mono_16k, DEFAULT_SAMPLE_RATE
    except Exception as exc:
        print('[{0}] concept-window audio import failed: {1}'.format(step_name.upper(), exc), file=_server.sys.stderr)
        return []
    waveform = _load_audio_mono_16k(audio_path)
    tensor = waveform.squeeze() if hasattr(waveform, 'squeeze') else waveform
    import numpy as np
    try:
        np_source = tensor.detach().cpu() if hasattr(tensor, 'detach') else (tensor.cpu() if hasattr(tensor, 'cpu') else tensor)
        audio_np = np_source.numpy() if hasattr(np_source, 'numpy') else np.asarray(np_source)
        audio_np = np.asarray(audio_np, dtype=np.float32).reshape(-1)
    except Exception as exc:
        print('[{0}] concept-window audio conversion failed: {1}'.format(step_name.upper(), exc), file=_server.sys.stderr)
        return []
    total_samples = int(audio_np.shape[0])
    duration_sec = total_samples / float(DEFAULT_SAMPLE_RATE) if total_samples else 0.0
    if duration_sec <= 0.0:
        return []
    # Deliberately avoid seeding Whisper with PARSE concept IDs/glosses here.
    # They are often English labels ("head", "arm", "knee") and caused
    # Razhan to drift into English/Latin-script loops on short Kurdish clips.
    initial_prompt = None
    rows: _server.List[_server.Dict[str, _server.Any]] = []
    source_by_step = {
        'stt': 'concept_window_stt',
        'ortho': 'concept_window_ortho',
        'ortho_refine': 'short_clip_fallback',
        'ipa': 'concept_window_ipa',
    }
    total = len(concept_intervals)
    for idx, concept_iv in enumerate(concept_intervals):
        if not isinstance(concept_iv, dict):
            continue
        try:
            c_start = float(concept_iv.get('start', 0.0) or 0.0)
            c_end = float(concept_iv.get('end', c_start) or c_start)
        except (TypeError, ValueError):
            continue
        if c_end <= c_start:
            continue
        if should_cancel is not None and should_cancel():
            print(
                "[{0}] cancel requested at concept window {1}/{2} ({3:.2f}-{4:.2f}s); returning {5} partial rows".format(
                    step_name.upper(),
                    idx + 1,
                    total,
                    c_start,
                    c_end,
                    len(rows),
                ),
                file=_server.sys.stderr,
                flush=True,
            )
            break
        slice_start = max(0.0, c_start - pad_sec)
        slice_end = min(duration_sec, c_end + pad_sec)
        if slice_end <= slice_start:
            continue
        s0 = max(0, int(round(slice_start * DEFAULT_SAMPLE_RATE)))
        s1 = min(total_samples, int(round(slice_end * DEFAULT_SAMPLE_RATE)))
        if s1 <= s0:
            continue
        concept_id = _concept_id_from_interval(concept_iv)
        confidence: _server.Optional[float] = None
        ipa_candidate: _server.Optional[_server.Dict[str, _server.Any]] = None
        ipa_candidate_key = ''
        if step_name == 'ipa':
            try:
                clip_for_ipa = tensor[s0:s1]
            except Exception:
                clip_for_ipa = audio_np[s0:s1]
            structured_ipa = _transcribe_ipa_window_structured(provider, clip_for_ipa)
            text = structured_ipa.get('raw_ipa')
            ipa_candidate = _ipa_candidate_from_structured(structured_ipa)
            ipa_candidate_key = _ipa_candidate_key(concept_iv, 'concept', idx)
        else:
            clip_np = audio_np[s0:s1]
            if clip_np.size == 0:
                continue
            try:
                result = provider.transcribe_clip(clip_np, initial_prompt=initial_prompt, language=language)
            except TypeError:
                result = provider.transcribe_clip(clip_np, initial_prompt=initial_prompt)
            if isinstance(result, (list, tuple)):
                text = result[0] if result else ''
                if len(result) > 1:
                    try:
                        confidence = float(result[1])
                    except (TypeError, ValueError):
                        confidence = None
            elif isinstance(result, dict):
                text = result.get('text') or result.get('transcript') or ''
                raw_conf = result.get('confidence')
                if raw_conf is not None:
                    try:
                        confidence = float(raw_conf)
                    except (TypeError, ValueError):
                        confidence = None
            else:
                text = result
        text = str(text or '').strip()
        if not text:
            continue
        row: _server.Dict[str, _server.Any] = {
            'start': c_start,
            'end': c_end,
            'text': text,
            'source': source_by_step[step_name],
        }
        if concept_id:
            row['conceptId'] = concept_id
        if confidence is not None:
            row['confidence'] = confidence
        if ipa_candidate is not None and ipa_candidate_key:
            row['_ipa_candidate_key'] = ipa_candidate_key
            row['_ipa_candidate'] = ipa_candidate
        rows.append(row)
        print("[{0}] concept-window {1}/{2} concept='{3}' → '{4}'".format(step_name.upper(), idx + 1, total, concept_id[:40], text[:40]), file=_server.sys.stderr, flush=True)
        if job_id:
            pct = 10.0 + 85.0 * (idx + 1) / max(total, 1)
            _set_compute_progress(job_id, pct, message='{0} concept window {1}/{2}'.format(step_name.upper(), idx + 1, total))
    return rows

def _short_clip_refine_lexemes(audio_path: _server.pathlib.Path, concept_intervals: _server.List[_server.Dict[str, _server.Any]], ortho_words: _server.List[_server.Dict[str, _server.Any]], provider: _server.Any, *, pad_sec: float=0.8, weak_conf: float=0.5, job_id: _server.Optional[str]=None, language: _server.Optional[str]=None) -> _server.List[_server.Dict[str, _server.Any]]:
    """Re-transcribe weak/missing concept-aligned lexeme windows.

    This keeps the original refine_lexemes gating semantics, but delegates the
    shared audio-load + padded-clip + ``transcribe_clip`` loop to
    ``_run_step_on_concept_windows`` so STT/ORTH/IPA concept modes use the
    same field-tested clipping path.
    """
    if not concept_intervals:
        return []
    ortho_sorted = sorted((w for w in ortho_words if isinstance(w, dict)), key=lambda w: (float(w.get('start', 0.0) or 0.0), float(w.get('end', 0.0) or 0.0)))

    def _best_match(concept_iv: _server.Dict[str, _server.Any]) -> _server.Optional[_server.Dict[str, _server.Any]]:
        c_start = float(concept_iv.get('start', 0.0) or 0.0)
        c_end = float(concept_iv.get('end', c_start) or c_start)
        if c_end <= c_start:
            return None
        best: _server.Optional[_server.Dict[str, _server.Any]] = None
        best_overlap = 0.0
        for w in ortho_sorted:
            w_start = float(w.get('start', 0.0) or 0.0)
            w_end = float(w.get('end', w_start) or w_start)
            if w_end <= c_start or w_start >= c_end:
                continue
            ov = min(c_end, w_end) - max(c_start, w_start)
            if ov > best_overlap:
                best_overlap = ov
                best = w
        return best

    weak_concepts: _server.List[_server.Dict[str, _server.Any]] = []
    for concept_iv in concept_intervals:
        if not isinstance(concept_iv, dict):
            continue
        try:
            c_start = float(concept_iv.get('start', 0.0) or 0.0)
            c_end = float(concept_iv.get('end', c_start) or c_start)
        except (TypeError, ValueError):
            continue
        if c_end <= c_start:
            continue
        match = _best_match(concept_iv)
        if match is not None:
            try:
                match_conf = float(match.get('confidence') or 0.0)
            except (TypeError, ValueError):
                match_conf = 0.0
            if match_conf >= weak_conf and str(match.get('text') or '').strip():
                continue
        weak_concepts.append(concept_iv)
    if not weak_concepts:
        return []
    return _server._run_step_on_concept_windows(
        audio_path=audio_path,
        concept_intervals=weak_concepts,
        provider=provider,
        step='ortho_refine',
        job_id=job_id,
        pad_sec=pad_sec,
        language=language,
    )

def _merge_ortho_words(aligned: _server.List[_server.Dict[str, _server.Any]], refined: _server.List[_server.Dict[str, _server.Any]]) -> _server.List[_server.Dict[str, _server.Any]]:
    """Merge short-clip refined entries into the forced-alignment list.

    Refined entries replace any aligned entry whose span falls inside the
    refined ``[start, end]`` window; aligned entries not covered by any
    refined window are preserved.
    """
    if not refined:
        return list(aligned)

    def _iv_bounds(iv: _server.Dict[str, _server.Any]) -> _server.Tuple[float, float]:
        return (float(iv.get('start', 0.0) or 0.0), float(iv.get('end', 0.0) or 0.0))
    kept: _server.List[_server.Dict[str, _server.Any]] = []
    for a in aligned:
        a_start, a_end = _iv_bounds(a)
        covered = False
        for r in refined:
            r_start, r_end = _iv_bounds(r)
            if a_start >= r_start and a_end <= r_end:
                covered = True
                break
        if not covered:
            kept.append(a)
    combined = kept + list(refined)
    combined.sort(key=lambda iv: (float(iv.get('start', 0.0) or 0.0), float(iv.get('end', 0.0) or 0.0)))
    return combined


def _annotation_paths_for_speaker(speaker: str) -> _server.Tuple[_server.pathlib.Path, _server.pathlib.Path, _server.pathlib.Path]:
    canonical_path = _server._project_root() / _server._annotation_record_relative_path(speaker)
    legacy_path = _server._project_root() / _server._annotation_legacy_record_relative_path(speaker)
    if canonical_path.is_file():
        return canonical_path, canonical_path, legacy_path
    if legacy_path.is_file():
        return legacy_path, canonical_path, legacy_path
    raise RuntimeError('No annotation found for speaker {0!r}'.format(speaker))


def _write_annotation_to_canonical_and_legacy(
    annotation_path: _server.pathlib.Path,
    canonical_path: _server.pathlib.Path,
    legacy_path: _server.pathlib.Path,
    annotation: _server.Dict[str, _server.Any],
) -> None:
    _server._write_json_file(annotation_path, annotation)
    if canonical_path != annotation_path:
        _server._write_json_file(canonical_path, annotation)
    if legacy_path != annotation_path:
        _server._write_json_file(legacy_path, annotation)


def _compute_speaker_stt(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    speaker = _server._normalize_speaker_id(payload.get('speaker'))
    run_mode = _server._normalize_compute_run_mode(payload.get('run_mode') if payload.get('run_mode') is not None else payload.get('runMode'))
    annotation_path: _server.Optional[_server.pathlib.Path] = None
    try:
        annotation_path, _canonical_path, _legacy_path = _server._annotation_paths_for_speaker(speaker)
    except RuntimeError:
        if run_mode != 'full':
            raise
        annotation: _server.Dict[str, _server.Any] = {}
    else:
        annotation = _server._read_json_file(annotation_path, {})
        if not isinstance(annotation, dict):
            raise RuntimeError('Annotation is not a JSON object')
    language = _transcription_language_from_payload_or_annotation(payload, annotation, speaker=speaker, step='stt')

    if run_mode == 'full':
        source_wav = str(payload.get('sourceWav') or payload.get('source_wav') or '').strip()
        if not source_wav:
            source_wav = str(_server._pipeline_audio_path_for_speaker(speaker))
        return _server._run_stt_job(job_id, speaker, source_wav, language)

    concept_ids = _server._payload_concept_ids(payload)
    if annotation_path is None:
        raise RuntimeError('No annotation found for speaker {0!r}'.format(speaker))
    concept_intervals = _server._concept_intervals_for_run_mode(annotation, run_mode, concept_ids)
    if not concept_intervals:
        return _server._concept_window_no_op_result(
            speaker,
            run_mode,
            'stt',
            _server._concept_windows_empty_reason(run_mode, concept_ids),
        )
    audio_path = _server._pipeline_audio_path_for_speaker(speaker)
    provider = _server.get_stt_provider()
    segments = _server._run_step_on_concept_windows(
        audio_path=audio_path,
        concept_intervals=concept_intervals,
        provider=provider,
        step='stt',
        job_id=job_id,
        language=language,
    )
    _server._write_stt_cache(speaker, str(audio_path), language, segments, source=run_mode)
    return {
        'speaker': speaker,
        'language': language,
        'run_mode': run_mode,
        'concept_windows': len(concept_intervals),
        'segments_written': len(segments),
        'source': run_mode,
        'affected_concepts': _server._affected_concepts_payload(concept_intervals),
    }


def _compute_speaker_ortho_concept_windows(
    job_id: str,
    *,
    speaker: str,
    annotation_path: _server.pathlib.Path,
    canonical_path: _server.pathlib.Path,
    legacy_path: _server.pathlib.Path,
    annotation: _server.Dict[str, _server.Any],
    tiers: _server.Dict[str, _server.Any],
    run_mode: str,
    concept_ids: _server.Optional[_server.Sequence[str]],
    language: _server.Optional[str],
    has_existing_text: bool,
    provider: _server.Optional[AIProvider] = None,
) -> _server.Dict[str, _server.Any]:
    if not language:
        language = _transcription_language_from_payload_or_annotation({}, annotation, speaker=speaker, step='ortho')
    concept_intervals = _server._concept_intervals_for_run_mode(annotation, run_mode, concept_ids)
    if not concept_intervals:
        return _server._concept_window_no_op_result(
            speaker,
            run_mode,
            'ortho',
            _server._concept_windows_empty_reason(run_mode, concept_ids),
        )
    audio_path = _server._pipeline_audio_path_for_speaker(speaker)
    if provider is None:
        provider = _server.get_ortho_provider()
    from ai.job_cancel import clear_cancel, make_should_cancel

    should_cancel = make_should_cancel(job_id)
    cancelled_requested = False
    try:
        rows = _server._run_step_on_concept_windows(
            audio_path=audio_path,
            concept_intervals=concept_intervals,
            provider=provider,
            step='ortho',
            job_id=job_id,
            language=language,
            should_cancel=should_cancel,
        )
        cancelled_requested = should_cancel()
    finally:
        clear_cancel(job_id)
    ortho_tier = tiers.get('ortho') if isinstance(tiers.get('ortho'), dict) else None
    if ortho_tier is None:
        ortho_tier = {'type': 'interval', 'display_order': 3, 'intervals': []}
    existing = [iv for iv in ortho_tier.get('intervals') or [] if isinstance(iv, dict)]
    ortho_tier['intervals'] = _server._merge_concept_window_rows(existing, rows, concept_intervals)
    tiers['ortho'] = ortho_tier
    annotation['tiers'] = tiers
    _server._annotation_touch_metadata(annotation, preserve_created=True)
    _server._write_annotation_to_canonical_and_legacy(annotation_path, canonical_path, legacy_path, annotation)
    result_payload = {
        'speaker': speaker,
        'run_mode': run_mode,
        'concept_windows': len(concept_intervals),
        'filled': len(rows),
        'total': len(rows),
        'skipped': False,
        'replaced_existing': has_existing_text,
        'audio_path': str(audio_path),
        'affected_concepts': _server._affected_concepts_payload(concept_intervals),
    }
    if cancelled_requested and len(rows) < len(concept_intervals):
        result_payload['status'] = 'partial_cancelled' if rows else 'cancelled'
        result_payload['cancelled_at_interval'] = len(rows)
    return result_payload


def _compute_speaker_ipa_concept_windows(
    job_id: str,
    *,
    speaker: str,
    annotation_path: _server.pathlib.Path,
    canonical_path: _server.pathlib.Path,
    legacy_path: _server.pathlib.Path,
    annotation: _server.Dict[str, _server.Any],
    tiers: _server.Dict[str, _server.Any],
    run_mode: str,
    concept_ids: _server.Optional[_server.Sequence[str]],
) -> _server.Dict[str, _server.Any]:
    concept_intervals = _server._concept_intervals_for_run_mode(annotation, run_mode, concept_ids)
    if not concept_intervals:
        return _server._concept_window_no_op_result(
            speaker,
            run_mode,
            'ipa',
            _server._concept_windows_empty_reason(run_mode, concept_ids),
        )
    ipa_tier = tiers.get('ipa') if isinstance(tiers.get('ipa'), dict) else None
    if ipa_tier is None:
        ipa_tier = {'type': 'interval', 'display_order': 1, 'intervals': []}
    existing = [iv for iv in ipa_tier.get('intervals') or [] if isinstance(iv, dict)]
    audio_path = _server._pipeline_audio_path_for_speaker(speaker)
    _set_compute_progress(job_id, 5.0, message='Loading IPA aligner')
    aligner = _server._get_ipa_aligner()
    rows = _server._run_step_on_concept_windows(
        audio_path=audio_path,
        concept_intervals=concept_intervals,
        provider=aligner,
        step='ipa',
        job_id=job_id,
    )
    clean_rows: _server.List[_server.Dict[str, _server.Any]] = []
    for row in rows:
        clean_row = dict(row)
        candidate_key = clean_row.pop('_ipa_candidate_key', '')
        candidate = clean_row.pop('_ipa_candidate', None)
        if isinstance(candidate_key, str) and candidate_key and isinstance(candidate, dict):
            _annotation_append_ipa_candidate(annotation, candidate_key, candidate)
        clean_rows.append(clean_row)
    ipa_tier['intervals'] = _server._merge_concept_window_rows(existing, clean_rows, concept_intervals)
    tiers['ipa'] = ipa_tier
    annotation['tiers'] = tiers
    _server._annotation_touch_metadata(annotation, preserve_created=True)
    _server._write_annotation_to_canonical_and_legacy(annotation_path, canonical_path, legacy_path, annotation)
    skipped = max(0, len(concept_intervals) - len(rows))
    return {
        'speaker': speaker,
        'run_mode': run_mode,
        'concept_windows': len(concept_intervals),
        'filled': len(rows),
        'skipped': skipped,
        'total': len(concept_intervals),
        'ortho_source': 'concept',
        'skip_breakdown': {'empty_ipa_from_model': skipped},
        'exception_samples': [],
        'affected_concepts': _server._affected_concepts_payload(concept_intervals),
    }

def _compute_speaker_ipa(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Fill missing IPA cells on a speaker's annotation via acoustic wav2vec2.

    Tier 3 of the acoustic alignment pipeline: for each ortho interval, run
    ``facebook/wav2vec2-xlsr-53-espeak-cv-ft`` CTC directly on the audio
    window ``[start, end]`` and write the greedy-decoded phoneme string
    into the IPA tier. No text → IPA conversion happens anywhere — the
    ortho text is used only to decide whether the interval is worth
    transcribing (empty ortho → skip).

    Intervals with existing non-empty IPA are left alone unless
    ``overwrite=True`` — so this can be re-run safely without clobbering
    manual edits.

    When ``run_mode='full'`` is requested but ortho/ortho_words is empty AND
    concept-tier intervals exist, the call is auto-routed to
    ``_compute_speaker_ipa_concept_windows(run_mode='concept-windows')`` so
    CSV-imported workflows don't require ORTH first.

    Payload: ``{ "speaker": "Fail02", "overwrite": false }``.
    """
    _server._compute_checkpoint('IPA.enter', payload=payload)
    print('[IPA] enter _compute_speaker_ipa payload={0}'.format(payload), file=_server.sys.stderr, flush=True)
    speaker = _server._normalize_speaker_id(payload.get('speaker'))
    overwrite = bool(payload.get('overwrite', False))
    run_mode = _server._normalize_compute_run_mode(payload.get('run_mode') if payload.get('run_mode') is not None else payload.get('runMode'))
    concept_ids = _server._payload_concept_ids(payload)
    _server._compute_checkpoint('IPA.parsed_args', speaker=speaker, overwrite=overwrite, run_mode=run_mode)
    canonical_path = _server._project_root() / _server._annotation_record_relative_path(speaker)
    legacy_path = _server._project_root() / _server._annotation_legacy_record_relative_path(speaker)
    _server._compute_checkpoint('IPA.resolved_paths', canonical=str(canonical_path), legacy=str(legacy_path))
    _server._compute_checkpoint('IPA.is_file_begin')
    if canonical_path.is_file():
        annotation_path = canonical_path
    elif legacy_path.is_file():
        annotation_path = legacy_path
    else:
        raise RuntimeError('No annotation found for speaker {0!r}'.format(speaker))
    _server._compute_checkpoint('IPA.is_file_done', annotation_path=str(annotation_path))
    print('[IPA] loaded annotation_path={0}'.format(annotation_path), file=_server.sys.stderr, flush=True)
    _server._compute_checkpoint('IPA.read_json_begin')
    annotation = _server._read_json_file(annotation_path, {})
    _server._compute_checkpoint('IPA.read_json_done')
    if not isinstance(annotation, dict):
        raise RuntimeError('Annotation is not a JSON object')
    tiers = annotation.get('tiers') or {}
    if run_mode != 'full':
        return _server._compute_speaker_ipa_concept_windows(
            job_id,
            speaker=speaker,
            annotation_path=annotation_path,
            canonical_path=canonical_path,
            legacy_path=legacy_path,
            annotation=annotation,
            tiers=tiers,
            run_mode=run_mode,
            concept_ids=concept_ids,
        )
    ortho_words_tier = tiers.get('ortho_words') or {}
    ortho_words_intervals = list(ortho_words_tier.get('intervals') or [])
    if ortho_words_intervals:
        ortho_intervals = ortho_words_intervals
        ortho_source = 'ortho_words'
    else:
        ortho_tier = tiers.get('ortho') or {}
        ortho_intervals = list(ortho_tier.get('intervals') or [])
        ortho_source = 'ortho'
    if not ortho_intervals:
        concept_tier = tiers.get('concept') if isinstance(tiers.get('concept'), dict) else None
        if bool(concept_tier and concept_tier.get('intervals')):
            print(
                '[IPA] no ortho/ortho_words intervals; auto-routing to concept-windows mode',
                file=_server.sys.stderr,
                flush=True,
            )
            result = _server._compute_speaker_ipa_concept_windows(
                job_id,
                speaker=speaker,
                annotation_path=annotation_path,
                canonical_path=canonical_path,
                legacy_path=legacy_path,
                annotation=annotation,
                tiers=tiers,
                run_mode='concept-windows',
                concept_ids=concept_ids,
            )
            result['message'] = (
                'Auto-routed to concept-windows mode: no ortho/ortho_words '
                'intervals; concept tier used as audio windows.'
            )
            return result
        print('[IPA] no ortho/ortho_words intervals — early return', file=_server.sys.stderr, flush=True)
        return {'speaker': speaker, 'filled': 0, 'skipped': 0, 'total': 0, 'message': 'No ortho intervals.'}
    ipa_tier = tiers.setdefault('ipa', {'type': 'interval', 'display_order': 1, 'intervals': []})
    ipa_intervals: _server.List[_server.Dict[str, _server.Any]] = list(ipa_tier.get('intervals') or [])

    def _key(interval: _server.Dict[str, _server.Any]) -> _server.Tuple[float, float]:
        return (round(float(interval.get('start', 0.0)), 3), round(float(interval.get('end', 0.0)), 3))
    ipa_by_key: _server.Dict[_server.Tuple[float, float], _server.Dict[str, _server.Any]] = {_key(i): i for i in ipa_intervals}
    print('[IPA] ortho_intervals={0} existing_ipa_intervals={1}'.format(len(ortho_intervals), len(ipa_intervals)), file=_server.sys.stderr, flush=True)
    _server._compute_checkpoint('IPA.resolve_audio_begin', speaker=speaker)
    print('[IPA] resolving audio path for speaker={0}…'.format(speaker), file=_server.sys.stderr, flush=True)
    audio_path = _server._pipeline_audio_path_for_speaker(speaker)
    _server._compute_checkpoint('IPA.resolve_audio_done', audio_path=str(audio_path))
    print('[IPA] audio_path={0} — importing ai.forced_align'.format(audio_path), file=_server.sys.stderr, flush=True)
    _server._compute_checkpoint('IPA.import_forced_align_begin')
    from ai.forced_align import _load_audio_mono_16k
    _server._compute_checkpoint('IPA.import_forced_align_done')
    print('[IPA] import ok — calling _load_audio_mono_16k()', file=_server.sys.stderr, flush=True)
    import time as _t_load
    _server._compute_checkpoint('IPA.load_audio_begin')
    _t0 = _t_load.time()
    audio_tensor = _load_audio_mono_16k(audio_path)
    _load_elapsed = _t_load.time() - _t0
    try:
        _numel = int(audio_tensor.numel())
    except Exception:
        _numel = -1
    _server._compute_checkpoint('IPA.load_audio_done', elapsed=round(_load_elapsed, 2), numel=_numel)
    print('[IPA] audio loaded in {0:.1f}s numel={1} (~{2:.1f}s of 16 kHz mono)'.format(_load_elapsed, _numel, _numel / 16000.0 if _numel > 0 else 0.0), file=_server.sys.stderr, flush=True)
    print('[IPA] calling _get_ipa_aligner()…', file=_server.sys.stderr, flush=True)
    _server._compute_checkpoint('IPA.get_aligner_begin')
    aligner = _server._get_ipa_aligner()
    _server._compute_checkpoint('IPA.get_aligner_done')
    if ortho_source == 'ortho_words':
        stt_segments: _server.List[_server.Dict[str, _server.Any]] = []
        has_words = False
    else:
        stt_segments = _server._read_stt_cache(speaker)
        has_words = bool(stt_segments and any((seg.get('words') for seg in stt_segments)))
    exception_samples: _server.List[str] = []
    skipped_empty_ortho = 0
    skipped_existing_ipa = 0
    skipped_zero_range = 0
    skipped_exception = 0
    skipped_empty_ipa = 0
    if has_words:
        print('[IPA] STT cache has words — using full forced-align path (Tier 2+3)', file=_server.sys.stderr, flush=True)
        _server._compute_checkpoint('IPA.forced_align_begin')
        from ai.ipa_transcribe import transcribe_words_with_forced_align
        total_words = sum((len(seg.get('words') or []) for seg in stt_segments))

        def _word_progress(pct: float, n: int) -> None:
            _set_compute_progress(job_id, 5.0 + pct * 0.9, message='IPA {0}/{1} words'.format(n, total_words))
        try:
            import json as _json2
            _ai_cfg2 = _json2.loads((_server._project_root() / 'config' / 'ai_config.json').read_text())
            _chunk_size = int(_ai_cfg2.get('wav2vec2', {}).get('chunk_size', 150))
        except Exception:
            _chunk_size = 150
        word_results = transcribe_words_with_forced_align(audio_path, stt_segments, aligner=aligner, progress_callback=_word_progress, chunk_size=_chunk_size, include_candidates=True)
        _server._compute_checkpoint('IPA.forced_align_done', word_count=len(word_results))
        print('[IPA] forced-align IPA: {0} word intervals'.format(len(word_results)), file=_server.sys.stderr, flush=True)
        ipa_intervals = []
        for idx, result in enumerate(word_results):
            ipa_text = str(result.get('ipa') or '').strip()
            interval = {'start': result['start'], 'end': result['end'], 'text': ipa_text}
            ipa_intervals.append(interval)
            structured_candidate = result.get('ipa_candidate')
            if ipa_text and isinstance(structured_candidate, dict):
                _annotation_append_ipa_candidate(
                    annotation,
                    _ipa_candidate_key(interval, 'ortho_words', idx),
                    _ipa_candidate_from_structured(structured_candidate),
                )
        filled = sum((1 for r in word_results if r['ipa']))
        skipped_empty_ipa = sum((1 for r in word_results if not r['ipa']))
        skipped = skipped_empty_ipa
        total = len(word_results)
    else:
        print(
            '[IPA] using {0}-interval CTC ({1} intervals)'.format(
                ortho_source,
                len(ortho_intervals),
            ),
            file=_server.sys.stderr,
            flush=True,
        )
        _server._compute_checkpoint('IPA.loop_begin', source=ortho_source, n=len(ortho_intervals))
        filled = 0
        skipped = 0
        total = len(ortho_intervals)
        for idx, ortho in enumerate(ortho_intervals):
            text = str(ortho.get('text') or '').strip()
            start_sec = float(ortho.get('start', 0.0) or 0.0)
            end_sec = float(ortho.get('end', start_sec) or start_sec)
            key = _key(ortho)
            existing = ipa_by_key.get(key)
            existing_text = str((existing or {}).get('text') or '').strip()
            if not text:
                skipped += 1
                skipped_empty_ortho += 1
                continue
            if existing_text and (not overwrite):
                skipped += 1
                skipped_existing_ipa += 1
                continue
            if end_sec <= start_sec:
                skipped += 1
                skipped_zero_range += 1
                continue
            _trace_iv = idx < 3 or idx % 10 == 0
            if _trace_iv:
                _server._compute_checkpoint('IPA.iv_begin', idx=idx, start=start_sec, end=end_sec)
            try:
                from ai.ipa_transcribe import transcribe_slice_structured
                structured_ipa = transcribe_slice_structured(audio_tensor, start_sec, end_sec, aligner)
                new_ipa = structured_ipa.get('raw_ipa')
            except Exception as exc:
                skipped += 1
                skipped_exception += 1
                if _trace_iv:
                    _server._compute_checkpoint('IPA.iv_exc', idx=idx, exc_type=type(exc).__name__, exc=str(exc)[:200])
                if len(exception_samples) < 3:
                    exception_samples.append('interval[{0}] {1:.2f}-{2:.2f}: {3}: {4}'.format(idx, start_sec, end_sec, type(exc).__name__, exc))
                continue
            if _trace_iv:
                _server._compute_checkpoint('IPA.iv_done', idx=idx, out_len=len(str(new_ipa or '')))
            new_ipa = str(new_ipa or '').strip()
            if not new_ipa:
                skipped += 1
                skipped_empty_ipa += 1
                continue
            if existing is not None:
                existing['text'] = new_ipa
            else:
                new_interval = {'start': ortho['start'], 'end': ortho['end'], 'text': new_ipa}
                ipa_intervals.append(new_interval)
                ipa_by_key[key] = new_interval
            _annotation_append_ipa_candidate(
                annotation,
                _ipa_candidate_key(ortho, ortho_source, idx),
                _ipa_candidate_from_structured(structured_ipa),
            )
            filled += 1
            progress = 5.0 + (idx + 1) / total * 90.0
            _set_compute_progress(job_id, progress, message='IPA {0}/{1}'.format(idx + 1, total))
    ipa_intervals.sort(key=lambda i: (float(i.get('start', 0.0)), float(i.get('end', 0.0))))
    ipa_tier['intervals'] = ipa_intervals
    tiers['ipa'] = ipa_tier
    annotation['tiers'] = tiers
    _server._annotation_touch_metadata(annotation, preserve_created=True)
    _server._write_json_file(annotation_path, annotation)
    if canonical_path != annotation_path:
        _server._write_json_file(canonical_path, annotation)
    if legacy_path != annotation_path:
        _server._write_json_file(legacy_path, annotation)
    skip_breakdown = {'empty_ortho': skipped_empty_ortho, 'existing_ipa_no_overwrite': skipped_existing_ipa, 'zero_range': skipped_zero_range, 'exception': skipped_exception, 'empty_ipa_from_model': skipped_empty_ipa}
    print('[IPA] speaker={0} filled={1} skipped={2} total={3} breakdown={4}'.format(speaker, filled, skipped, total, skip_breakdown), file=_server.sys.stderr, flush=True)
    if exception_samples:
        for sample in exception_samples:
            print('[IPA][EXC] {0}'.format(sample), file=_server.sys.stderr, flush=True)
    return {'speaker': speaker, 'filled': filled, 'skipped': skipped, 'total': total, 'ortho_source': ortho_source, 'skip_breakdown': skip_breakdown, 'exception_samples': exception_samples}

def _compute_speaker_forced_align(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Run Tier 2 forced alignment for a speaker.

    Looks up the speaker's most recent STT artifact (which carries nested
    segments[].words[] from Tier 1), refines each word window with
    torchaudio.functional.forced_align + xlsr-53-espeak-cv-ft, and writes
    the refined spans back next to the input artifact as
    ``*.aligned.json``. Ortho / IPA tiers in the annotation are left
    untouched — this job only produces the refined boundary artifact
    that Tier 3 (or a manual UI step) can then consume.
    """
    speaker = _server._normalize_speaker_id(payload.get('speaker'))
    overwrite = bool(payload.get('overwrite', False))
    language = str(payload.get('language') or 'ku').strip() or 'ku'
    try:
        pad_ms = int(payload.get('padMs', 100) or 100)
    except (TypeError, ValueError):
        pad_ms = 100
    pad_ms = max(0, min(500, pad_ms))
    emit_phonemes = bool(payload.get('emitPhonemes', True))
    audio_path = _server._pipeline_audio_path_for_speaker(speaker)
    stt_candidates = [_server._project_root() / 'stt_output' / '{0}.stt.json'.format(speaker), _server._project_root() / 'stt_output' / speaker / 'stt.json']
    stt_artifact_path: _server.Optional[_server.pathlib.Path] = next((p for p in stt_candidates if p.is_file()), None)
    if stt_artifact_path is None:
        raise RuntimeError('No Tier 1 STT artifact found for {0!r}. Run stt_word_level_start first so segments[].words[] are available as alignment seeds.'.format(speaker))
    artifact = _server._read_json_file(stt_artifact_path, {})
    if not isinstance(artifact, dict):
        raise RuntimeError('STT artifact is not a JSON object: {0}'.format(stt_artifact_path))
    segments = artifact.get('segments') or []
    if not isinstance(segments, list):
        raise RuntimeError('STT artifact segments[] is missing or malformed')
    _set_compute_progress(job_id, 10.0, message='Loading wav2vec2 aligner')
    from ai.forced_align import align_segments
    aligned = align_segments(audio_path=_server.pathlib.Path(audio_path), segments=segments, language=language, pad_ms=pad_ms, emit_phonemes=emit_phonemes)
    aligned_segments: _server.List[_server.Dict[str, _server.Any]] = []
    method_counts: _server.Dict[str, int] = {}
    for seg_idx, seg in enumerate(segments):
        refined_words = aligned[seg_idx] if seg_idx < len(aligned) else []
        merged: _server.Dict[str, _server.Any] = dict(seg)
        if refined_words:
            merged['words'] = list(refined_words)
            for w in refined_words:
                m = str(w.get('method', '') or 'unknown')
                method_counts[m] = method_counts.get(m, 0) + 1
        aligned_segments.append(merged)
    output_path = stt_artifact_path.with_suffix('')
    if output_path.suffix == '.stt':
        output_path = output_path.with_suffix('')
    output_path = output_path.parent / '{0}.aligned.json'.format(output_path.name)
    if output_path.is_file() and (not overwrite):
        existing = _server._read_json_file(output_path, {})
        return {'speaker': speaker, 'skipped': True, 'reason': 'aligned artifact already exists; pass overwrite=true to replace', 'alignedArtifact': str(output_path), 'segmentCount': len(existing.get('segments') or [])}
    out_payload = {**artifact, 'segments': aligned_segments, 'alignment': {'tier': 'tier2_forced_align', 'model': 'facebook/wav2vec2-xlsr-53-espeak-cv-ft', 'language': language, 'padMs': pad_ms, 'emitPhonemes': emit_phonemes, 'methodCounts': method_counts}}
    _server._write_json_file(output_path, out_payload)
    _set_compute_progress(job_id, 95.0, message='Wrote aligned artifact')
    return {'speaker': speaker, 'sttArtifact': str(stt_artifact_path), 'alignedArtifact': str(output_path), 'segmentCount': len(aligned_segments), 'methodCounts': method_counts}


def _compute_speaker_boundaries(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    speaker = _server._normalize_speaker_id(payload.get('speaker'))
    overwrite = bool(payload.get('overwrite', False))
    canonical_path = _server._project_root() / _server._annotation_record_relative_path(speaker)
    legacy_path = _server._project_root() / _server._annotation_legacy_record_relative_path(speaker)
    if canonical_path.is_file():
        annotation_path = canonical_path
    elif legacy_path.is_file():
        annotation_path = legacy_path
    else:
        raise RuntimeError('No annotation found for speaker {0!r}'.format(speaker))

    annotation = _server._read_json_file(annotation_path, {})
    if not isinstance(annotation, dict):
        raise RuntimeError('Annotation is not a JSON object')

    tiers = annotation.get('tiers') or {}
    _set_compute_progress(job_id, 5.0, message='Reading STT cache')
    stt_segments = _server._read_stt_cache(speaker) or []
    has_words = bool(stt_segments and any(seg.get('words') for seg in stt_segments))
    if not has_words:
        raise RuntimeError(
            'No STT word-level timestamps cached for {0!r}. Run STT first before refining boundaries.'.format(speaker)
        )

    existing_tier_raw = tiers.get('ortho_words')
    existing_tier = existing_tier_raw if isinstance(existing_tier_raw, dict) else None
    existing_intervals = list((existing_tier or {}).get('intervals') or [])
    if overwrite:
        manual_intervals: _server.List[_server.Dict[str, _server.Any]] = []
    else:
        manual_intervals = [
            interval
            for interval in existing_intervals
            if isinstance(interval, dict) and bool(interval.get('manuallyAdjusted'))
        ]

    _set_compute_progress(job_id, 15.0, message='Resolving audio')
    audio_path = _server._pipeline_audio_path_for_speaker(speaker)

    _set_compute_progress(job_id, 30.0, message='Running forced alignment')
    aligned_words = _server._ortho_tier2_align_to_words(audio_path, stt_segments)

    def _overlaps(a: _server.Dict[str, _server.Any], b: _server.Dict[str, _server.Any]) -> bool:
        try:
            a_start = float(a.get('start', 0.0) or 0.0)
            a_end = float(a.get('end', a_start) or a_start)
            b_start = float(b.get('start', 0.0) or 0.0)
            b_end = float(b.get('end', b_start) or b_start)
        except (TypeError, ValueError):
            return False
        return a_start < b_end and a_end > b_start

    if manual_intervals:
        aligned_words = [
            word
            for word in aligned_words
            if not any(_overlaps(word, manual) for manual in manual_intervals)
        ]

    for word in aligned_words:
        word['manuallyAdjusted'] = False

    combined = sorted(
        manual_intervals + aligned_words,
        key=lambda interval: (
            float(interval.get('start', 0.0) or 0.0),
            float(interval.get('end', 0.0) or 0.0),
        ),
    )

    _set_compute_progress(job_id, 90.0, message='Writing tiers.ortho_words')
    if existing_tier is None:
        existing_tier = {'type': 'interval', 'display_order': 4, 'intervals': []}
    existing_tier['intervals'] = combined
    tiers['ortho_words'] = existing_tier
    annotation['tiers'] = tiers
    _server._annotation_touch_metadata(annotation, preserve_created=True)

    _server._write_json_file(annotation_path, annotation)
    if canonical_path != annotation_path and canonical_path.is_file():
        _server._write_json_file(canonical_path, annotation)
    if legacy_path != annotation_path and legacy_path.is_file():
        _server._write_json_file(legacy_path, annotation)

    return {
        'speaker': speaker,
        'generated': len(aligned_words),
        'preserved_manual': len(manual_intervals),
        'total': len(combined),
    }


def _compute_speaker_retranscribe_with_boundaries(
    job_id: str,
    payload: _server.Dict[str, _server.Any],
) -> _server.Dict[str, _server.Any]:
    speaker = _server._normalize_speaker_id(payload.get('speaker'))
    language_raw = payload.get('language')
    language = str(language_raw).strip() if language_raw is not None else None
    if not language:
        language = None

    canonical_path = _server._project_root() / _server._annotation_record_relative_path(speaker)
    legacy_path = _server._project_root() / _server._annotation_legacy_record_relative_path(speaker)
    if canonical_path.is_file():
        annotation_path = canonical_path
    elif legacy_path.is_file():
        annotation_path = legacy_path
    else:
        raise RuntimeError('No annotation found for speaker {0!r}'.format(speaker))

    annotation = _server._read_json_file(annotation_path, {})
    if not isinstance(annotation, dict):
        raise RuntimeError('Annotation is not a JSON object')

    tiers = annotation.get('tiers') or {}
    ortho_words_tier = tiers.get('ortho_words') if isinstance(tiers.get('ortho_words'), dict) else None
    raw_intervals = list((ortho_words_tier or {}).get('intervals') or [])
    intervals: _server.List[_server.Tuple[float, float]] = []
    for interval in raw_intervals:
        if not isinstance(interval, dict):
            continue
        try:
            start_sec = float(interval.get('start', 0.0) or 0.0)
            end_sec = float(interval.get('end', start_sec) or start_sec)
        except (TypeError, ValueError):
            continue
        if end_sec <= start_sec:
            continue
        intervals.append((start_sec, end_sec))
    if not intervals:
        raise RuntimeError(
            'No BND intervals available for {0!r}. Refine boundaries first before re-running STT with boundary constraints.'.format(speaker)
        )
    intervals.sort(key=lambda item: (item[0], item[1]))

    _set_compute_progress(job_id, 5.0, message='Resolving audio')
    audio_path = _server._pipeline_audio_path_for_speaker(speaker)

    _set_compute_progress(job_id, 10.0, message='Loading audio')
    from ai.forced_align import _load_audio_mono_16k

    audio_tensor = _load_audio_mono_16k(audio_path)

    _set_compute_progress(job_id, 15.0, message='Loading STT provider')
    provider = _server.get_stt_provider()
    if not hasattr(provider, 'transcribe_segments_in_memory'):
        raise RuntimeError(
            'Boundary-constrained STT requires a provider that supports in-memory segment transcription (LocalWhisperProvider). The active provider {0!r} does not.'.format(type(provider).__name__)
        )

    interval_total = len(intervals)

    def _on_progress(pct: float, done: int) -> None:
        scaled = 15.0 + max(0.0, min(100.0, pct)) * 0.80
        _set_compute_progress(
            job_id,
            scaled,
            message='Re-transcribing {0}/{1}'.format(done, interval_total),
        )

    segments = provider.transcribe_segments_in_memory(
        audio_tensor,
        intervals,
        language=language,
        progress_callback=_on_progress,
    )

    _set_compute_progress(job_id, 96.0, message='Writing STT cache')
    _write_stt_cache(
        speaker,
        str(audio_path),
        language,
        segments,
        source='boundary_constrained',
    )
    return {
        'speaker': speaker,
        'language': language,
        'boundary_intervals': interval_total,
        'segments_written': len(segments),
        'source': 'boundary_constrained',
    }


def _compute_speaker_ortho(
    job_id: str,
    payload: _server.Dict[str, _server.Any],
    *,
    provider: _server.Optional[AIProvider] = None,
) -> _server.Dict[str, _server.Any]:
    """Generate an orthographic transcript for a speaker using the razhan model.

    Runs the ORTH provider (faster-whisper with razhan/whisper-base-sdh)
    full-file against the speaker's working WAV (normalized copy preferred,
    raw source as fallback) and writes razhan's own segments to the
    ``ortho`` tier of the annotation. After the coarse tier is written, a
    Tier-2 forced-alignment pass refines the Whisper word-level timestamps
    into ``tiers.ortho_words`` for precise per-lexeme lookup in the UI.

    Payload: ``{"speaker": "Fail02", "overwrite": false, "refine_lexemes": bool?}``.

    If ``refine_lexemes`` is omitted the provider's config default (from
    ai_config.json) is used.

    Overwrite semantics differ from IPA: razhan's segmentation isn't stable
    across runs, so we can't pair segments by ``(start, end)`` the way IPA
    does. Rule: if the ortho tier already has any non-empty text intervals,
    the caller must set ``overwrite=True`` to replace the whole tier;
    otherwise the run is a no-op and returns ``skipped=True``. Empty tiers
    are always populated. When overwrite runs, ``tiers.ortho_words`` is
    always rebuilt from scratch alongside ``tiers.ortho``.
    """
    speaker = _server._normalize_speaker_id(payload.get('speaker'))
    overwrite = bool(payload.get('overwrite', False))
    refine_payload = payload.get('refine_lexemes')
    run_mode = _server._normalize_compute_run_mode(payload.get('run_mode') if payload.get('run_mode') is not None else payload.get('runMode'))
    concept_ids = _server._payload_concept_ids(payload)
    canonical_path = _server._project_root() / _server._annotation_record_relative_path(speaker)
    legacy_path = _server._project_root() / _server._annotation_legacy_record_relative_path(speaker)
    if canonical_path.is_file():
        annotation_path = canonical_path
    elif legacy_path.is_file():
        annotation_path = legacy_path
    else:
        raise RuntimeError('No annotation found for speaker {0!r}'.format(speaker))
    annotation = _server._read_json_file(annotation_path, {})
    if not isinstance(annotation, dict):
        raise RuntimeError('Annotation is not a JSON object')
    language_str = _transcription_language_from_payload_or_annotation(payload, annotation, speaker=speaker, step='ortho')
    tiers = annotation.get('tiers') or {}
    ortho_tier = tiers.get('ortho') if isinstance(tiers.get('ortho'), dict) else None
    existing_intervals: _server.List[_server.Dict[str, _server.Any]] = []
    if isinstance(ortho_tier, dict):
        existing_intervals = [iv for iv in ortho_tier.get('intervals') or [] if isinstance(iv, dict)]
    has_existing_text = any((str(iv.get('text') or '').strip() for iv in existing_intervals))
    if run_mode != 'full':
        return _server._compute_speaker_ortho_concept_windows(
            job_id,
            speaker=speaker,
            annotation_path=annotation_path,
            canonical_path=canonical_path,
            legacy_path=legacy_path,
            annotation=annotation,
            tiers=tiers,
            run_mode=run_mode,
            concept_ids=concept_ids,
            language=language_str,
            has_existing_text=has_existing_text,
            provider=provider,
        )
    if has_existing_text and (not overwrite):
        return {'speaker': speaker, 'filled': 0, 'skipped': True, 'reason': 'ortho tier already populated; pass overwrite=True to replace', 'existing_intervals': len(existing_intervals)}
    audio_path = _server._pipeline_audio_path_for_speaker(speaker)
    _set_compute_progress(job_id, 2.0, message='Loading ortho model (razhan)')
    if provider is None:
        provider = _server.get_ortho_provider()

    def _progress_callback(progress: float, segments_processed: int) -> None:
        clamped = min(float(progress) if progress is not None else 0.0, 94.0)
        _set_compute_progress(job_id, max(2.0, clamped), message='ORTH transcribing ({0} segments)'.format(segments_processed), segments_processed=segments_processed)
    from ai.job_cancel import clear_cancel, make_should_cancel

    should_cancel = make_should_cancel(job_id)
    cancelled_requested = False
    try:
        try:
            segments = provider.transcribe(audio_path=audio_path, language=language_str, progress_callback=_progress_callback, should_cancel=should_cancel)
        except TypeError as exc:
            if 'should_cancel' not in str(exc):
                raise
            segments = provider.transcribe(audio_path=audio_path, language=language_str, progress_callback=_progress_callback)
        cancelled_requested = should_cancel()
    finally:
        clear_cancel(job_id)
    new_intervals: _server.List[_server.Dict[str, _server.Any]] = []
    for seg in segments:
        start = float(seg.get('start', 0.0) or 0.0)
        end = float(seg.get('end', start) or start)
        text = str(seg.get('text', '') or '').strip()
        if not text:
            continue
        new_intervals.append({'start': start, 'end': end, 'text': text})
    new_intervals.sort(key=lambda iv: (float(iv['start']), float(iv['end'])))
    if ortho_tier is None:
        ortho_tier = {'type': 'interval', 'display_order': 3, 'intervals': []}
    ortho_tier['intervals'] = new_intervals
    tiers['ortho'] = ortho_tier
    if refine_payload is None:
        refine_lexemes = bool(getattr(provider, 'refine_lexemes', False))
    else:
        refine_lexemes = bool(refine_payload)
    if cancelled_requested:
        ortho_words_tier = tiers.get('ortho_words') if isinstance(tiers.get('ortho_words'), dict) else None
        if ortho_words_tier is None:
            ortho_words_tier = {'type': 'interval', 'display_order': 4, 'intervals': []}
        ortho_words_tier['intervals'] = []
        tiers['ortho_words'] = ortho_words_tier
        annotation['tiers'] = tiers
        _server._annotation_touch_metadata(annotation, preserve_created=True)
        _server._write_json_file(annotation_path, annotation)
        if canonical_path != annotation_path:
            _server._write_json_file(canonical_path, annotation)
        if legacy_path != annotation_path:
            _server._write_json_file(legacy_path, annotation)
        result_payload = {
            'speaker': speaker,
            'filled': len(new_intervals),
            'ortho_words': 0,
            'refined_lexemes': 0,
            'refine_lexemes_enabled': refine_lexemes,
            'skipped': False,
            'replaced_existing': has_existing_text,
            'audio_path': str(audio_path),
            'total': len(new_intervals),
            'status': 'partial_cancelled' if new_intervals else 'cancelled',
            'cancelled_at_interval': len(new_intervals),
        }
        _set_compute_progress(job_id, 99.0, message='ORTH cancelled after {0} intervals'.format(len(new_intervals)))
        return result_payload
    _set_compute_progress(job_id, 95.0, message='ORTH Tier-2 forced alignment')
    ortho_words = _server._ortho_tier2_align_to_words(audio_path, segments)
    refined_additions: _server.List[_server.Dict[str, _server.Any]] = []
    if refine_lexemes:
        concept_tier = tiers.get('concept') if isinstance(tiers.get('concept'), dict) else None
        concept_intervals = [iv for iv in (concept_tier.get('intervals') or [] if concept_tier else []) if isinstance(iv, dict)]
        if concept_intervals:
            _set_compute_progress(job_id, 97.0, message='ORTH refine_lexemes (short-clip, {0} concepts)'.format(len(concept_intervals)))
            refined_additions = _server._short_clip_refine_lexemes(audio_path=audio_path, concept_intervals=concept_intervals, ortho_words=ortho_words, provider=provider, job_id=job_id, language=language_str)
    merged_words = _server._merge_ortho_words(ortho_words, refined_additions)
    ortho_words_tier = tiers.get('ortho_words') if isinstance(tiers.get('ortho_words'), dict) else None
    if ortho_words_tier is None:
        ortho_words_tier = {'type': 'interval', 'display_order': 4, 'intervals': []}
    ortho_words_tier['intervals'] = merged_words
    tiers['ortho_words'] = ortho_words_tier
    annotation['tiers'] = tiers
    _server._annotation_touch_metadata(annotation, preserve_created=True)
    _server._write_json_file(annotation_path, annotation)
    if canonical_path != annotation_path:
        _server._write_json_file(canonical_path, annotation)
    if legacy_path != annotation_path:
        _server._write_json_file(legacy_path, annotation)
    _set_compute_progress(job_id, 99.0, message='ORTH written ({0} intervals, {1} word-level, {2} refined)'.format(len(new_intervals), len(merged_words), len(refined_additions)))
    return {'speaker': speaker, 'filled': len(new_intervals), 'ortho_words': len(merged_words), 'refined_lexemes': len(refined_additions), 'refine_lexemes_enabled': refine_lexemes, 'skipped': False, 'replaced_existing': has_existing_text, 'audio_path': str(audio_path), 'total': len(new_intervals)}


_MIN_FREE_GB_FOR_IPA = 4.0  # Conservative, tunable guard before wav2vec2 loads.
_DEFAULT_FULL_PIPELINE_MIN_MEM_GB = 12.0
_FULL_PIPELINE_HOST_MEMORY_STEPS = {'stt', 'ortho', 'ipa'}


class FullPipelineMemoryPreflightError(RuntimeError):
    """Structured full-pipeline host-memory preflight failure."""

    error_code = 'oom_suspect'

    def __init__(self, *, mem_available_gb: float, required_gb: float, swap_total_gb: float) -> None:
        self.mem_available_gb = float(mem_available_gb)
        self.required_gb = float(required_gb)
        self.swap_total_gb = float(swap_total_gb)
        super().__init__(
            'Insufficient host memory for full pipeline: {0:.1f} GiB available, {1:.1f} GiB required. '
            'Close other memory-heavy processes, run smaller step subsets, or adjust PARSE_FULL_PIPELINE_MIN_MEM_GB '
            'only if you have validated this machine can survive the run.'.format(
                self.mem_available_gb,
                self.required_gb,
            )
        )

    @property
    def details(self) -> _server.Dict[str, float]:
        return {
            'mem_available_gb': self.mem_available_gb,
            'required_gb': self.required_gb,
            'swap_total_gb': self.swap_total_gb,
        }


def _full_pipeline_min_host_memory_gb() -> float:
    raw_value = str(_server.os.environ.get('PARSE_FULL_PIPELINE_MIN_MEM_GB') or '').strip()
    if not raw_value:
        return _DEFAULT_FULL_PIPELINE_MIN_MEM_GB
    try:
        return max(0.0, float(raw_value))
    except (TypeError, ValueError):
        return _DEFAULT_FULL_PIPELINE_MIN_MEM_GB


def _host_memory_info() -> _server.Optional[_server.Dict[str, float]]:
    """Return currently available host RAM and total swap in GiB.

    ``MemAvailable`` is the right field for this guard: it estimates memory
    reclaimable without swapping, which is what matters before loading the
    full ORTH→IPA stack for long field recordings. If the platform cannot
    report it, the preflight degrades open rather than blocking compute.
    """
    try:
        mem_available_gb: _server.Optional[float] = None
        swap_total_gb = 0.0
        with open('/proc/meminfo', 'r', encoding='utf-8') as handle:
            for line in handle:
                if not (line.startswith('MemAvailable:') or line.startswith('SwapTotal:')):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                kib = float(parts[1])
                if line.startswith('MemAvailable:'):
                    mem_available_gb = kib / float(1024 ** 2)
                elif line.startswith('SwapTotal:'):
                    swap_total_gb = kib / float(1024 ** 2)
        if mem_available_gb is None:
            return None
        return {'mem_available_gb': mem_available_gb, 'swap_total_gb': swap_total_gb}
    except (OSError, ValueError, TypeError):
        return None


def _host_available_memory_gb() -> _server.Optional[float]:
    info = _host_memory_info()
    if info is None:
        return None
    return float(info.get('mem_available_gb', 0.0))


def _ensure_host_memory_for_full_pipeline(selected_steps: _server.Sequence[str]) -> None:
    selected = {str(step or '').strip().lower() for step in selected_steps}
    if not (selected & _FULL_PIPELINE_HOST_MEMORY_STEPS):
        return
    required_gb = _server._full_pipeline_min_host_memory_gb()
    if required_gb <= 0:
        return
    info = _server._host_memory_info()
    swap_total_gb = float(info.get('swap_total_gb', 0.0)) if isinstance(info, dict) else 0.0
    available_gb = _server._host_available_memory_gb()
    if available_gb is None or available_gb >= required_gb:
        return
    raise FullPipelineMemoryPreflightError(
        mem_available_gb=float(available_gb),
        required_gb=float(required_gb),
        swap_total_gb=swap_total_gb,
    )


def _gpu_free_memory_gb() -> _server.Optional[float]:
    """Return free CUDA memory in GiB, or None when CUDA is unavailable."""
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return None
        free, _total = torch.cuda.mem_get_info()
        return float(free) / float(1024 ** 3)
    except (ImportError, RuntimeError, AttributeError, TypeError, ValueError):
        return None


def _ensure_free_gpu_memory_for_ipa() -> None:
    free_gb = _gpu_free_memory_gb()
    if free_gb is not None and free_gb < _MIN_FREE_GB_FOR_IPA:
        raise RuntimeError(
            'Insufficient free GPU memory for IPA step: {0:.1f} GB free, need {1:.1f} GB. '
            'Run ortho and ipa as separate jobs, or close other GPU consumers.'.format(
                free_gb,
                _MIN_FREE_GB_FOR_IPA,
            )
        )

def _compute_full_pipeline(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Run a user-selected subset of the speaker pipeline sequentially.

    Payload::

        {
          "speaker": "Fail02",
          "steps": ["normalize", "stt", "ortho", "ipa"],
          "overwrites": {"normalize": false, "stt": false, "ortho": true, "ipa": false},
          "language": "sd"       // optional, forwarded to STT + ORTH
        }

    Steps run in canonical order (normalize → stt → ortho → ipa). Unselected
    steps are skipped silently. Overwrite flags only matter for steps whose
    prior state already has data — an unchecked "overwrite" on a populated
    tier causes that step to skip with ``skipped=True`` in its sub-result.

    **Step-level resilience:** each step runs in its own try/except. A
    failure in STT does NOT stop ORTH / IPA from being attempted for this
    speaker. Each step's result includes ``status`` (``"ok"`` /
    ``"skipped"`` / ``"error"``), and errors capture the full traceback
    for post-mortem in the UI. The pipeline job completes successfully
    even if every step failed — the caller inspects the per-step
    ``status`` field. This is a walk-away-friendly design: the user can
    kick off a batch of 10 speakers × 4 steps, come back, and see
    exactly what worked and what didn't.
    """
    speaker = _server._normalize_speaker_id(payload.get('speaker'))
    raw_steps = payload.get('steps')
    if raw_steps is None:
        selected = list(_server.PIPELINE_STEPS)
    elif isinstance(raw_steps, (list, tuple)):
        selected_set = {str(s).strip().lower() for s in raw_steps if str(s).strip()}
        selected = [s for s in _server.PIPELINE_STEPS if s in selected_set]
    else:
        raise RuntimeError('steps must be a list, got {0}'.format(type(raw_steps).__name__))
    if not selected:
        return {'speaker': speaker, 'steps_run': [], 'results': {}, 'message': 'No steps selected'}
    _set_compute_progress(job_id, 1.0, message='Full pipeline host-memory preflight')
    _server._ensure_host_memory_for_full_pipeline(selected)
    overwrites_raw = payload.get('overwrites') or {}
    if not isinstance(overwrites_raw, dict):
        overwrites_raw = {}
    overwrites = {str(k).strip().lower(): bool(v) for k, v in overwrites_raw.items()}
    language = payload.get('language')
    language_str = str(language).strip() if isinstance(language, str) and language.strip() else None
    run_mode = _server._normalize_compute_run_mode(payload.get('run_mode') if payload.get('run_mode') is not None else payload.get('runMode'))
    concept_ids = _server._payload_concept_ids(payload)
    import traceback as _traceback_module
    results: _server.Dict[str, _server.Any] = {}
    steps_run: _server.List[str] = []
    total = len(selected)
    ortho_provider: _server.Optional[AIProvider] = None

    def _capture_error(exc: BaseException) -> _server.Dict[str, _server.Any]:
        return {'status': 'error', 'error': str(exc), 'traceback': _traceback_module.format_exc()}

    def _unload_ortho_provider() -> None:
        nonlocal ortho_provider
        provider = ortho_provider
        if provider is None:
            return
        try:
            unload = getattr(provider, 'unload_model', None)
            if callable(unload):
                unload()
        except Exception:
            pass
        finally:
            ortho_provider = None

    def _release_full_pipeline_ipa_aligner() -> None:
        try:
            release = getattr(_server, '_release_ipa_aligner', None)
            if callable(release):
                release()
        except Exception:
            pass

    try:
        for idx, step in enumerate(selected):
            step_base_pct = 5.0 + idx / total * 90.0
            _set_compute_progress(job_id, step_base_pct, message='Pipeline step {0}/{1}: {2}'.format(idx + 1, total, step))
            try:
                if step == 'normalize':
                    source_rel = _server._annotation_primary_source_wav(speaker)
                    if not source_rel:
                        raise RuntimeError('Cannot normalize {0!r}: no source_audio on annotation'.format(speaker))
                    audio_path = _server._resolve_project_path(source_rel)
                    working_dir = _server._project_root() / 'audio' / 'working' / speaker
                    normalized_path = _server.build_normalized_output_path(audio_path, working_dir)
                    if normalized_path.exists() and (not overwrites.get('normalize', False)):
                        results['normalize'] = {'status': 'skipped', 'reason': 'normalized output already exists; overwrite=False', 'path': str(normalized_path.relative_to(_server._project_root()))}
                        steps_run.append(step)
                        continue
                    _server._run_normalize_job(job_id, speaker, source_rel)
                    snapshot = _server._get_job_snapshot(job_id) or {}
                    if str(snapshot.get('status') or '') == 'error':
                        raise RuntimeError('normalize step failed: {0}'.format(snapshot.get('error') or 'unknown error'))
                    sub_result = snapshot.get('result') if isinstance(snapshot.get('result'), dict) else {}
                    results['normalize'] = {'status': 'ok', **(dict(sub_result) if sub_result else {'done': True})}
                    _server._reset_job_to_running(job_id)
                    steps_run.append(step)
                elif step == 'stt':
                    if run_mode == 'full':
                        cached = _server._latest_stt_segments_for_speaker(speaker)
                        if cached and (not overwrites.get('stt', False)):
                            results['stt'] = {'status': 'skipped', 'reason': 'STT cache already exists; overwrite=False', 'segments': len(cached)}
                            steps_run.append(step)
                            continue
                        try:
                            audio_path = _server._pipeline_audio_path_for_speaker(speaker)
                        except (RuntimeError, FileNotFoundError) as exc:
                            raise RuntimeError('Cannot run STT for {0!r}: {1}'.format(speaker, exc))
                        try:
                            stt_result = _server._run_stt_job(job_id, speaker, str(audio_path), language_str)
                        except Exception as exc:
                            raise RuntimeError('stt step failed: {0}'.format(exc)) from exc
                        results['stt'] = {'status': 'ok', 'segments': len(stt_result.get('segments') or []), 'done': True}
                    else:
                        stt_payload: _server.Dict[str, _server.Any] = {'speaker': speaker, 'run_mode': run_mode, 'language': language_str}
                        if concept_ids is not None:
                            stt_payload['concept_ids'] = list(concept_ids)
                        sub_result = _server._compute_speaker_stt(job_id, stt_payload)
                        if sub_result.get('skipped'):
                            results['stt'] = {'status': 'skipped', **sub_result}
                        else:
                            results['stt'] = {'status': 'ok', **sub_result}
                    steps_run.append(step)
                elif step == 'ortho':
                    if ortho_provider is None:
                        ortho_provider = _server.get_ortho_provider()
                    ortho_sub_payload: _server.Dict[str, _server.Any] = {'speaker': speaker, 'overwrite': overwrites.get('ortho', False), 'language': language_str, 'run_mode': run_mode}
                    if concept_ids is not None:
                        ortho_sub_payload['concept_ids'] = list(concept_ids)
                    if payload.get('refine_lexemes') is not None:
                        ortho_sub_payload['refine_lexemes'] = bool(payload.get('refine_lexemes'))
                    sub_result = _server._compute_speaker_ortho(job_id, ortho_sub_payload, provider=ortho_provider)
                    if sub_result.get('skipped'):
                        results['ortho'] = {'status': 'skipped', **sub_result}
                    else:
                        results['ortho'] = {'status': 'ok', **sub_result}
                    steps_run.append(step)
                    if 'ipa' in selected:
                        _unload_ortho_provider()
                elif step == 'ipa':
                    if 'ortho' in selected:
                        _ensure_free_gpu_memory_for_ipa()
                    ipa_sub_payload: _server.Dict[str, _server.Any] = {'speaker': speaker, 'overwrite': overwrites.get('ipa', False), 'run_mode': run_mode}
                    if concept_ids is not None:
                        ipa_sub_payload['concept_ids'] = list(concept_ids)
                    sub_result = _server._compute_speaker_ipa(job_id, ipa_sub_payload)
                    if 'message' in sub_result and sub_result.get('total', 0) == 0:
                        results['ipa'] = {'status': 'skipped', 'reason': sub_result['message'], **sub_result}
                    else:
                        results['ipa'] = {'status': 'ok', **sub_result}
                    steps_run.append(step)
                    _release_full_pipeline_ipa_aligner()
                else:
                    results[step] = {'status': 'error', 'error': 'Unknown pipeline step: {0}'.format(step), 'traceback': None}
            except Exception as exc:
                results[step] = _capture_error(exc)
                steps_run.append(step)
                if step == 'ortho' and 'ipa' in selected:
                    _unload_ortho_provider()
                elif step == 'ipa':
                    _release_full_pipeline_ipa_aligner()
                _server._reset_job_to_running(job_id)
    finally:
        _unload_ortho_provider()
        if 'ipa' in selected:
            _release_full_pipeline_ipa_aligner()

    _set_compute_progress(job_id, 99.0, message='Pipeline complete')
    summary = {'ok': sum((1 for r in results.values() if r.get('status') == 'ok')), 'skipped': sum((1 for r in results.values() if r.get('status') == 'skipped')), 'error': sum((1 for r in results.values() if r.get('status') == 'error'))}
    print('[PIPELINE] speaker={0} steps={1} summary={2}'.format(speaker, steps_run, summary), file=_server.sys.stderr, flush=True)
    for step_name, step_result in results.items():
        status = step_result.get('status')
        if status == 'ok':
            concise = {k: v for k, v in step_result.items() if k not in ('status', 'traceback')}
            print('[PIPELINE][{0}] ok {1}'.format(step_name, concise), file=_server.sys.stderr, flush=True)
        elif status == 'skipped':
            print('[PIPELINE][{0}] skipped reason={1}'.format(step_name, step_result.get('reason')), file=_server.sys.stderr, flush=True)
        elif status == 'error':
            print('[PIPELINE][{0}] ERROR {1}'.format(step_name, step_result.get('error')), file=_server.sys.stderr, flush=True)
            tb = step_result.get('traceback')
            if tb:
                print(tb, file=_server.sys.stderr, flush=True)
    payload_out: _server.Dict[str, _server.Any] = {'speaker': speaker, 'steps_run': steps_run, 'results': results, 'summary': summary}
    if run_mode != 'full':
        payload_out['run_mode'] = run_mode
        scoped_affected: _server.List[_server.Dict[str, _server.Any]] = []
        for result in results.values():
            if isinstance(result, dict) and isinstance(result.get('affected_concepts'), list):
                scoped_affected = list(result.get('affected_concepts') or [])
                break
        payload_out['affected_concepts'] = scoped_affected
    return payload_out


def _compute_concept_scoped_noop_payload(compute_type: str, payload: _server.Dict[str, _server.Any]) -> _server.Optional[_server.Dict[str, _server.Any]]:
    """Return a no-job response when a scoped compute request has no windows.

    The HTTP compute-start path calls this before allocating a background job so
    edited-only requests with no manually adjusted concepts are cheap and
    deterministic rather than spawning an immediate no-op worker.
    """
    run_mode = _server._normalize_compute_run_mode(payload.get('run_mode') if payload.get('run_mode') is not None else payload.get('runMode'))
    if run_mode == 'full':
        return None
    normalized_type = str(compute_type or '').strip().lower()
    scoped_types = {'stt', 'ortho', 'ortho_only', 'ortho-only', 'ipa', 'ipa_only', 'ipa-only'}
    if normalized_type in {'full_pipeline', 'full-pipeline', 'pipeline'}:
        raw_steps = payload.get('steps')
        if isinstance(raw_steps, (list, tuple)):
            selected = {str(step or '').strip().lower() for step in raw_steps}
        else:
            selected = {'stt', 'ortho', 'ipa'}
        if not (selected & {'stt', 'ortho', 'ipa'}):
            return None
        scoped_step = 'full_pipeline'
    elif normalized_type in scoped_types:
        scoped_step = normalized_type.replace('_only', '').replace('-only', '')
    else:
        return None
    try:
        speaker = _server._normalize_speaker_id(payload.get('speaker'))
        concept_ids = _server._payload_concept_ids(payload)
        annotation_path, _canonical_path, _legacy_path = _server._annotation_paths_for_speaker(speaker)
        annotation = _server._read_json_file(annotation_path, {})
        if not isinstance(annotation, dict):
            return None
        concept_intervals = _server._concept_intervals_for_run_mode(annotation, run_mode, concept_ids)
    except Exception:
        return None
    if concept_intervals:
        return None
    result = _server._concept_window_no_op_result(
        speaker,
        run_mode,
        scoped_step,
        _server._concept_windows_empty_reason(run_mode, concept_ids),
    )
    result['status'] = 'skipped'
    result['jobId'] = None
    result['computeType'] = normalized_type
    return result

def _offset_detect_timeout_sec() -> float:
    """Hard cap on offset-detection runtime. Defaults to 10 minutes.
    Override via ``PARSE_OFFSET_DETECT_TIMEOUT_SEC``. Covers both
    ``offset_detect`` and ``offset_detect_from_pair`` — the manual path
    is normally sub-second but shares the guard for consistency."""
    try:
        raw = _server.os.environ.get('PARSE_OFFSET_DETECT_TIMEOUT_SEC', '').strip()
        if not raw:
            return _server._OFFSET_DETECT_TIMEOUT_SEC_DEFAULT
        val = float(raw)
        if val <= 0 or not _server.math.isfinite(val):
            return _server._OFFSET_DETECT_TIMEOUT_SEC_DEFAULT
        return val
    except (TypeError, ValueError):
        return _server._OFFSET_DETECT_TIMEOUT_SEC_DEFAULT

def _enforce_offset_deadline(deadline: float, label: str) -> None:
    """Raise TimeoutError if ``deadline`` (monotonic sec) has passed.

    Called at progress checkpoints inside the offset compute functions.
    Doesn't interrupt in-flight work on its own — Python can't kill a
    thread mid-numerics — but guarantees the UI gets a clean "timed out"
    error with the full traceback instead of an indefinite detecting
    modal. The compute worker survives the TimeoutError like any other
    raised exception (worker_main's try/except captures + emits it)."""
    if _server.time.monotonic() > deadline:
        raise TimeoutError("Offset detection exceeded {0:.0f}s hard timeout at stage '{1}'. Raise PARSE_OFFSET_DETECT_TIMEOUT_SEC if your corpus legitimately needs more time.".format(_server._offset_detect_timeout_sec(), label))

def _compute_offset_detect(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Compute-dispatcher adapter for timestamp offset detection.

    Runs the lightweight pure-Python offset algorithm asynchronously so the
    header progress bar appears while annotation and STT data are correlated.
    No GPU work — intentionally CPU-only.
    """
    deadline = _server.time.monotonic() + _server._offset_detect_timeout_sec()
    speaker = str(payload.get('speaker') or '').strip()
    if not speaker:
        raise ValueError("offset_detect payload missing 'speaker'")
    try:
        n_anchors = max(2, min(50, int(payload.get('nAnchors') or payload.get('n_anchors') or 12)))
    except (TypeError, ValueError):
        n_anchors = 12
    try:
        bucket_sec = max(0.1, float(payload.get('bucketSec') or payload.get('bucket_sec') or 1.0))
    except (TypeError, ValueError):
        bucket_sec = 1.0
    try:
        min_match_score = max(0.0, min(1.0, float(payload.get('minMatchScore') or payload.get('min_match_score') or 0.56)))
    except (TypeError, ValueError):
        min_match_score = 0.56
    distribution_raw = str(payload.get('distribution') or payload.get('anchorDistribution') or 'quantile').strip().lower()
    if distribution_raw not in {'quantile', 'earliest'}:
        distribution_raw = 'quantile'
    _set_compute_progress(job_id, 10, message='Loading annotation')
    annotation_path = _server._annotation_read_path_for_speaker(speaker)
    annotation = _server._normalize_annotation_record(_server._read_json_any_file(annotation_path), speaker)
    intervals = _server._annotation_offset_anchor_intervals(annotation)
    if not intervals:
        raise ValueError("Speaker '{0}' has no annotated intervals to use as offset anchors".format(speaker))
    _set_compute_progress(job_id, 25, message='Resolving STT segments')
    stt_segments_payload = payload.get('sttSegments') or payload.get('stt_segments')
    stt_job_id = str(payload.get('sttJobId') or payload.get('stt_job_id') or '').strip()
    if stt_segments_payload is None and stt_job_id:
        stt_job = _server._get_job_snapshot(stt_job_id)
        if stt_job is None:
            raise ValueError('Unknown sttJobId: {0}'.format(stt_job_id))
        if str(stt_job.get('type') or '') != 'stt':
            raise ValueError('sttJobId is not an STT job')
        if str(stt_job.get('status') or '') != 'complete':
            raise ValueError('STT job has not completed')
        stt_result = stt_job.get('result') if isinstance(stt_job.get('result'), dict) else {}
        stt_segments_payload = stt_result.get('segments')
    if stt_segments_payload is None:
        stt_segments_payload = _server._latest_stt_segments_for_speaker(speaker)
    if not stt_segments_payload:
        raise ValueError('No STT segments available. Run STT first or pass sttJobId / sttSegments.')
    from compare import anchors_from_intervals as _anchors_from_intervals, detect_offset_detailed as _detect_offset_detailed, load_rules_from_file as _load_rules, segments_from_raw as _segments_from_raw
    _set_compute_progress(job_id, 40, message='Loading phonetic rules')
    rules_path = _server._project_root() / 'config' / 'phonetic_rules.json'
    try:
        rules = _load_rules(rules_path) if rules_path.exists() else []
    except Exception:
        rules = []
    _set_compute_progress(job_id, 55, message='Selecting anchors')
    anchors = _anchors_from_intervals(intervals, n_anchors, distribution=distribution_raw)
    if not anchors:
        raise ValueError('No usable anchors with both timestamp and text in annotation')
    _set_compute_progress(job_id, 65, message='Parsing STT segments')
    segments = _segments_from_raw(stt_segments_payload)
    if not segments:
        raise ValueError('STT input contained no usable segments')
    _server._enforce_offset_deadline(deadline, 'pre-match')
    _set_compute_progress(job_id, 75, message='Computing timestamp offset')
    try:
        detailed = _detect_offset_detailed(anchors=anchors, segments=segments, rules=rules, bucket_sec=bucket_sec, min_match_score=min_match_score)
    except ValueError as exc:
        raise ValueError('Offset detection failed: {0}'.format(exc)) from exc
    _server._enforce_offset_deadline(deadline, 'post-match')
    _set_compute_progress(job_id, 92, message='Finalizing result')
    return _server._offset_detect_payload(speaker=speaker, offset_sec=float(detailed.offset_sec), confidence=float(detailed.confidence), n_matched=int(detailed.n_matched), total_anchors=len(anchors), total_segments=len(segments), method=detailed.method, spread_sec=float(detailed.spread_sec), matches=detailed.matches, anchor_distribution=distribution_raw)

def _compute_offset_detect_from_pair(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Compute-dispatcher adapter for manual-pair timestamp offset detection.

    Accepts one or more (audioTimeSec, csvTimeSec/conceptId) pairs and returns
    the median offset. Pure arithmetic — no STT or GPU work.
    """
    deadline = _server.time.monotonic() + _server._offset_detect_timeout_sec()
    speaker = str(payload.get('speaker') or '').strip()
    if not speaker:
        raise ValueError("offset_detect_from_pair payload missing 'speaker'")
    raw_pairs: _server.Any = payload.get('pairs')
    if raw_pairs is None:
        raw_pairs = [{'audioTimeSec': payload.get('audioTimeSec') or payload.get('audio_time_sec'), 'csvTimeSec': payload.get('csvTimeSec') or payload.get('csv_time_sec'), 'conceptId': payload.get('conceptId') or payload.get('concept_id')}]
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise ValueError('pairs must be a non-empty list')
    _set_compute_progress(job_id, 20, message='Validating pairs')
    annotation_cache: _server.Optional[_server.Dict[str, _server.Any]] = None

    def _get_annotation() -> _server.Dict[str, _server.Any]:
        nonlocal annotation_cache
        if annotation_cache is None:
            annotation_cache = _server._normalize_annotation_record(_server._read_json_any_file(_server._annotation_read_path_for_speaker(speaker)), speaker)
        return annotation_cache
    matches: _server.List[_server.Dict[str, _server.Any]] = []
    offsets: _server.List[float] = []
    for raw in raw_pairs:
        if not isinstance(raw, dict):
            raise ValueError('Each pair must be a JSON object')
        audio_raw = raw.get('audioTimeSec')
        if audio_raw is None:
            audio_raw = raw.get('audio_time_sec')
        try:
            audio_time = float(audio_raw)
        except (TypeError, ValueError):
            raise ValueError('Each pair needs a numeric audioTimeSec')
        if not _server.math.isfinite(audio_time) or audio_time < 0:
            raise ValueError('audioTimeSec must be finite and non-negative')
        csv_raw = raw.get('csvTimeSec')
        if csv_raw is None:
            csv_raw = raw.get('csv_time_sec')
        concept_raw = raw.get('conceptId') or raw.get('concept_id')
        anchor_csv_time: _server.Optional[float] = None
        anchor_label: _server.Optional[str] = None
        if csv_raw is not None and (not isinstance(csv_raw, str) or csv_raw.strip() != ''):
            try:
                anchor_csv_time = float(csv_raw)
            except (TypeError, ValueError):
                raise ValueError('csvTimeSec must be a number when provided')
            if not _server.math.isfinite(anchor_csv_time) or anchor_csv_time < 0:
                raise ValueError('csvTimeSec must be finite and non-negative')
            anchor_label = 'csvTimeSec={0:.3f}s'.format(anchor_csv_time)
        elif concept_raw is not None and str(concept_raw).strip():
            concept_id = str(concept_raw).strip()
            interval = _server._annotation_find_concept_interval(_get_annotation(), concept_id)
            if interval is None:
                raise ValueError("No annotation interval found for concept '{0}'".format(concept_id))
            anchor_csv_time = float(interval['start'])
            anchor_label = "concept '{0}' @ {1:.3f}s".format(concept_id, anchor_csv_time)
        else:
            raise ValueError('Each pair needs either csvTimeSec or conceptId')
        pair_offset = round(audio_time - float(anchor_csv_time), 3)
        offsets.append(pair_offset)
        matches.append({'anchor_index': -1, 'anchor_text': anchor_label or '', 'anchor_start': float(anchor_csv_time), 'segment_index': -1, 'segment_text': '(user-supplied audio time)', 'segment_start': float(audio_time), 'score': 1.0, 'offset_sec': pair_offset})
    _server._enforce_offset_deadline(deadline, 'pre-median')
    _set_compute_progress(job_id, 75, message='Computing median offset')
    import statistics as _statistics
    median_offset = round(_statistics.median(offsets), 3)
    if len(offsets) >= 2:
        deviations = [abs(o - median_offset) for o in offsets]
        spread = round(_statistics.median(deviations), 3)
        max_deviation = max(deviations)
        confidence = max(0.5, min(0.99, 0.99 - max_deviation / 60.0))
    else:
        spread = 0.0
        confidence = 0.99
    _set_compute_progress(job_id, 92, message='Finalizing result')
    return _server._offset_detect_payload(speaker=speaker, offset_sec=median_offset, confidence=float(confidence), n_matched=len(matches), total_anchors=len(matches), total_segments=0, method='manual_pair', spread_sec=float(spread), matches=matches, anchor_distribution='manual')

def _api_get_annotation(self, speaker: str) -> None:
    """Return annotation JSON for a single speaker.

    Lookup order: ``<speaker>.parse.json`` then ``<speaker>.json``.
    Returns 404 if neither exists.
    """
    safe_speaker = _server.pathlib.Path(speaker).name
    if not safe_speaker:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Invalid speaker id')
    annotations_dir = _server._project_root() / 'annotations'
    canonical = annotations_dir / (safe_speaker + '.parse.json')
    legacy = annotations_dir / (safe_speaker + '.json')
    target: _server.Optional[_server.pathlib.Path] = None
    if canonical.is_file():
        target = canonical
    elif legacy.is_file():
        target = legacy
    if target is None:
        raise _server.ApiError(_server.HTTPStatus.NOT_FOUND, 'No annotation file for speaker: {0}'.format(safe_speaker))
    payload = _server._read_json_file(target, {})
    self._send_json(_server.HTTPStatus.OK, payload)

def _api_get_stt_segments(self, speaker_part: str) -> None:
    """Return cached STT segments for a speaker.

    Reads ``coarse_transcripts/<speaker>.json`` — the cache seeded by
    ``_run_stt_job`` and also used by ``/api/offset/detect``. Always
    returns HTTP 200 with ``{"speaker", "source_wav", "language",
    "segments"}``; missing cache yields ``segments: []``. The frontend
    treats an empty array as "run STT first" — keeping the response
    uniform avoids noisy 404s in the console on every speaker switch.
    """
    try:
        response = _server._app_build_get_stt_segments_response(speaker_part, normalize_speaker_id=_server._normalize_speaker_id, stt_cache_path=_server._stt_cache_path)
    except _server._app_SpeechAnnotationHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_get_pipeline_state(self, speaker_part: str) -> None:
    """Return per-step pipeline state for a speaker.

    Drives the pre-flight checklist modal shown before ``Run Full Pipeline``.
    Shape is documented on ``_pipeline_state_for_speaker``.
    """
    try:
        speaker = _server._normalize_speaker_id(speaker_part)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    try:
        payload = _server._pipeline_state_for_speaker(speaker)
    except Exception as exc:
        raise _server.ApiError(_server.HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
    self._send_json(_server.HTTPStatus.OK, payload)

def _api_post_annotation(self, speaker_part: str) -> None:
    try:
        speaker = _server._normalize_speaker_id(speaker_part)
        annotation_path = _server._annotation_record_path_for_speaker(speaker)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    body = self._read_json_body(required=True)
    try:
        payload = _server._annotation_payload_from_request_body(body)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    normalized = _server._normalize_annotation_record(payload, speaker)
    normalized['speaker'] = speaker
    _server._annotation_sync_speaker_tier(normalized)
    _server._annotation_touch_metadata(normalized, preserve_created=True)
    _server._write_json_file(annotation_path, normalized)
    self._send_json(_server.HTTPStatus.OK, {'success': True, 'speaker': speaker, 'annotation': normalized})

def _api_post_offset_detect(self) -> None:
    """Submit a compute job to detect a constant timestamp offset for a speaker.

    Validates the speaker field, then queues the detection as a compute job
    and returns the job_id immediately. The caller should poll
    POST /api/compute/offset_detect/status with {jobId} to track progress
    and retrieve the OffsetDetectResult from result when done.

    All original options (nAnchors, bucketSec, minMatchScore, distribution,
    sttJobId, sttSegments) are forwarded to the compute function unchanged.
    """
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_offset_detect_response(body, normalize_speaker_id=_server._normalize_speaker_id, create_job=_server._create_job, launch_compute_runner=_server._launch_compute_runner)
    except _server._app_ComputeOffsetHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_offset_detect_from_pair(self) -> None:
    """Submit a compute job to detect offset from manual (csv_time, audio_time) pairs.

    Accepts the same body shapes as before (single pair or pairs array),
    queues the arithmetic as a compute job, and returns the job_id immediately.
    Poll POST /api/compute/offset_detect_from_pair/status with {jobId} to
    retrieve the OffsetDetectResult from result when the job completes.

    Body shapes accepted:
        Single: {speaker, audioTimeSec, csvTimeSec? | conceptId?}
        Multi:  {speaker, pairs: [{audioTimeSec, csvTimeSec? | conceptId?}, ...]}
    """
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_offset_detect_from_pair_response(body, normalize_speaker_id=_server._normalize_speaker_id, create_job=_server._create_job, launch_compute_runner=_server._launch_compute_runner)
    except _server._app_ComputeOffsetHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_offset_apply(self) -> None:
    """Shift every annotation interval by ``offsetSec`` (start/end += offset).

    For the typical "WAV missing leading audio" case the detected offset is
    negative, so applying it pulls every CSV-sourced timestamp earlier so
    the lexemes line up with the truncated recording.
    """
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_offset_apply_response(body, normalize_speaker_id=_server._normalize_speaker_id, annotation_read_path_for_speaker=_server._annotation_read_path_for_speaker, read_json_any_file=_server._read_json_any_file, normalize_annotation_record=_server._normalize_annotation_record, annotation_shift_intervals=_server._annotation_shift_intervals, annotation_touch_metadata=_server._annotation_touch_metadata, annotation_record_path_for_speaker=_server._annotation_record_path_for_speaker, write_json_file=_server._write_json_file)
    except _server._app_ComputeOffsetHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

__all__ = ['_annotation_empty_tier', '_annotation_sort_intervals', '_annotation_normalize_interval', '_annotation_tier_key', '_annotation_normalize_tier', '_annotation_max_end', '_annotation_sort_all_intervals', '_annotation_collect_speaker_intervals', '_offset_detect_payload', '_annotation_find_concept_interval', '_annotation_offset_anchor_intervals', '_annotation_shift_intervals', '_stt_cache_path', '_write_stt_cache', '_read_stt_cache', '_latest_stt_segments_for_speaker', '_annotation_sync_speaker_tier', '_annotation_touch_metadata', '_annotation_empty_record', '_annotation_upsert_interval', '_normalize_flat_annotation_entry', '_annotation_record_from_flat_entries', '_normalize_annotation_record', '_normalize_speaker_id', '_annotation_record_relative_path', '_annotation_legacy_record_relative_path', '_annotation_resolve_relative_path', '_annotation_record_path_for_speaker', '_annotation_legacy_record_path_for_speaker', '_annotation_read_path_for_speaker', '_annotation_payload_from_request_body', '_pipeline_audio_path_for_speaker', '_audio_duration_sec', '_tier_coverage', '_pipeline_state_for_speaker', '_ortho_tier2_align_to_words', '_normalize_compute_run_mode', '_payload_concept_ids', '_concept_intervals_for_run_mode', '_affected_concepts_payload', '_concept_window_no_op_result', '_concept_windows_empty_reason', '_merge_concept_window_rows', '_run_step_on_concept_windows', '_short_clip_refine_lexemes', '_merge_ortho_words', '_annotation_paths_for_speaker', '_write_annotation_to_canonical_and_legacy', '_compute_speaker_stt', '_compute_speaker_ortho_concept_windows', '_compute_speaker_ipa_concept_windows', '_compute_speaker_ipa', '_compute_speaker_forced_align', '_compute_speaker_boundaries', '_compute_speaker_retranscribe_with_boundaries', '_compute_speaker_ortho', '_full_pipeline_min_host_memory_gb', '_host_memory_info', '_host_available_memory_gb', '_ensure_host_memory_for_full_pipeline', '_gpu_free_memory_gb', '_compute_full_pipeline', '_compute_concept_scoped_noop_payload', '_offset_detect_timeout_sec', '_enforce_offset_deadline', '_compute_offset_detect', '_compute_offset_detect_from_pair', '_api_get_annotation', '_api_get_stt_segments', '_api_get_pipeline_state', '_api_post_annotation', '_api_post_offset_detect', '_api_post_offset_detect_from_pair', '_api_post_offset_apply']

