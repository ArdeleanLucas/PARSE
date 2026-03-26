#!/usr/bin/env python3
"""
generate_ai_suggestions.py — Pre-compute AI concept-finding suggestions for Source Explorer.

For each concept × speaker where the speaker is MISSING that concept,
scans their coarse transcript for matching tokens using three strategies:

    1. Exact orthographic match  →  base score 0.70–1.0 ("high")
    2. Fuzzy orthographic match  →  base score 0.40–0.69 ("medium")
       Levenshtein ≤1 for tokens ≤4 chars, ≤2 for tokens >4 chars
    3. Romanized phonetic match  →  base score 0.20–0.39 ("low")
       IPA → regex (e.g. "jek" → r"[jy][aæeɛ][kgq]")

Outputs ai_suggestions.json with BASE confidence scores only.
Positional re-ranking is applied client-side by suggestions-panel.js.

Usage:
    python generate_ai_suggestions.py \
        --review-data path/to/review_data.json \
        --transcripts-dir path/to/coarse_transcripts/ \
        --anchors path/to/anchors.json \
        --project path/to/project.json \
        --output path/to/ai_suggestions.json
"""

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import unicodedata
from typing import Optional


# ============================================================================
# Unicode Normalization
# ============================================================================

_MATCH_CHAR_FOLD_MAP: dict[str, str] = {
    'ك': 'ک',
    'ي': 'ی',
    'ى': 'ی',
    'ۍ': 'ی',
    'ە': 'ە',
    'ة': 'ە',
    'ۀ': 'ە',
    'ھ': 'ه',
    'أ': 'ا',
    'إ': 'ا',
    'ٱ': 'ا',
    'آ': 'ا',
    'ؤ': 'و',
}

_DROP_FORMAT_CHARS = {
    '\u200c',  # ZWNJ
    '\u200d',  # ZWJ
    '\u200e',  # LRM
    '\u200f',  # RLM
    '\u061c',  # ALM
    'ـ',        # tatweel
}

_MISSING_STATUSES = {
    'missing',
    'unknown',
    '?',
    'absent',
    'not_found',
    'not-found',
    'not found',
}

_VERIFIED_STATUSES = {'accepted', 'reviewed', 'verified', 'correct'}

_MAX_POSITIONAL_BOOST = 0.25

_DEFAULT_AI_PROVIDER = 'anthropic'
_DEFAULT_AI_MODEL = 'claude-sonnet-4-6'
_DEFAULT_AI_API_KEY_ENV = 'ANTHROPIC_API_KEY'


def normalize_text_for_match(text: str) -> str:
    """Normalize Kurdish/Arabic/Persian text for exact/fuzzy matching."""
    if not text:
        return ''

    text = unicodedata.normalize('NFKC', str(text)).lower()

    normalized_chars: list[str] = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch in _DROP_FORMAT_CHARS or category == 'Cf':
            continue
        if category.startswith('M'):
            continue
        normalized_chars.append(_MATCH_CHAR_FOLD_MAP.get(ch, ch))

    return ' '.join(''.join(normalized_chars).split())


# ============================================================================
# Levenshtein distance — stdlib only, two-row DP
# ============================================================================

def levenshtein(s1: str, s2: str) -> int:
    if s1 == s2:
        return 0

    len1, len2 = len(s1), len(s2)
    if len1 > len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1

    if len1 == 0:
        return len2

    prev = list(range(len2 + 1))
    curr = [0] * (len2 + 1)

    for i in range(1, len1 + 1):
        curr[0] = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + cost,
            )
        prev, curr = curr, prev

    return prev[len2]


def fuzzy_threshold(word: str) -> int:
    return 1 if len(word) <= 4 else 2


# ============================================================================
# IPA → romanized phonetic regex
# ============================================================================

_IPA_SEQUENCE_MAP: list[tuple[str, str]] = [
    ('d͡ʒ', r'(?:zh|j|ʒ|dzh|dʒ|ʤ)'),
    ('dʒ', r'(?:zh|j|ʒ|dzh|dʒ|ʤ)'),
    ('ʤ', r'(?:zh|j|ʒ|dzh|dʒ|ʤ)'),
    ('t͡ʃ', r'(?:ch|č|c|tsh|tʃ|ʧ)'),
    ('tʃ', r'(?:ch|č|c|tsh|tʃ|ʧ)'),
    ('ʧ', r'(?:ch|č|c|tsh|tʃ|ʧ)'),
    ('sh', r'(?:sh|ş|ʃ)'),
    ('zh', r'(?:zh|j|ʒ)'),
    ('ch', r'(?:ch|č|c)'),
    ('kh', r'(?:kh|x|χ)'),
    ('gh', r'(?:gh|ɣ|g)'),
]

_IPA_CHAR_MAP: dict[str, str] = {
    'b': r'[bp]',
    'p': r'[bp]',
    'd': r'[dt]',
    't': r'[dt]',
    'k': r'[kgq]',
    'g': r'[kgq]',
    'q': r'[kgq]',
    'ʔ': r'[ʔ]?',
    'f': r'[fv]',
    'v': r'[fv]',
    's': r'[sz]',
    'z': r'[sz]',
    'ʃ': r'(?:sh|ş|ʃ|s)',
    'ʒ': r'(?:zh|j|ʒ|ʤ)',
    'x': r'(?:kh|x|χ)',
    'χ': r'(?:kh|x|χ)',
    'ɣ': r'(?:gh|ɣ|g)',
    'ħ': r'[ħh]',
    'h': r'[h]',
    'č': r'(?:ch|č|c|ʧ)',
    'c': r'(?:ch|č|c|ʧ)',
    'n': r'[nm]',
    'm': r'[nm]',
    'l': r'[lr]',
    'r': r'[lr]',
    'ɾ': r'[lr]',
    'ʁ': r'[rɣ]',
    'w': r'[wv]',
    'j': r'[jy]',
    'y': r'[jy]',
    'a': r'[aæeɛə]',
    'æ': r'[aæe]',
    'e': r'[eæiɛ]',
    'ɛ': r'[eæɛ]',
    'ə': r'[əaeɛ]',
    'i': r'[iɪe]',
    'ɪ': r'[iɪe]',
    'o': r'[ouɔ]',
    'ɔ': r'[oɔu]',
    'u': r'[uoʊ]',
    'ʊ': r'[uʊo]',
    'ê': r'[eæiɛ]',
    'î': r'[iɪ]',
    'û': r'[uʊ]',
}

_IPA_STRIP_CHARS = set('ːˈˌ̥̃̊')

def ipa_to_regex(ipa: str) -> Optional[str]:
    if not ipa:
        return None

    ipa = normalize_text_for_match(ipa)

    for ch in _IPA_STRIP_CHARS:
        ipa = ipa.replace(ch, '')

    ipa = re.sub(r'^[/\[\]]+|[/\[\]]+$', '', ipa).strip()

    if not ipa:
        return None

    parts: list[str] = []
    i = 0
    while i < len(ipa):
        matched_sequence = False
        for seq, pattern in _IPA_SEQUENCE_MAP:
            if ipa.startswith(seq, i):
                parts.append(pattern)
                i += len(seq)
                matched_sequence = True
                break

        if matched_sequence:
            continue

        ch = ipa[i]
        mapped = _IPA_CHAR_MAP.get(ch)
        if mapped:
            parts.append(mapped)
        elif re.match(r'\w', ch, re.UNICODE):
            parts.append(re.escape(ch))
        i += 1

    if not parts:
        return None

    return ''.join(parts)


# ============================================================================
# Tokenisation
# ============================================================================

_STRIP_PUNCT = '.,!?؟،؛:;-–—()[]{}«»"\'\u2026\u200c\u200d'

def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_tok in text.split():
        tok = raw_tok.strip(_STRIP_PUNCT)
        if tok:
            tokens.append(tok)
    return tokens


# ============================================================================
# Match strategies
# ============================================================================

def match_exact(token: str, norm_token: str, reference_forms: list[str], norm_forms: list[str]) -> Optional[tuple[str, float, str]]:
    for form, norm_form in zip(reference_forms, norm_forms):
        if norm_token == norm_form:
            return (token, 0.92, 'exact_ortho_match')
    return None


def match_fuzzy(token: str, norm_token: str, reference_forms: list[str], norm_forms: list[str]) -> Optional[tuple[str, float, str]]:
    threshold = fuzzy_threshold(norm_token)
    best_dist = threshold + 1
    best_form = None

    for form, norm_form in zip(reference_forms, norm_forms):
        if abs(len(norm_token) - len(norm_form)) > threshold:
            continue
        d = levenshtein(norm_token, norm_form)
        if d <= threshold and d < best_dist:
            best_dist = d
            best_form = form

    if best_form is None:
        return None

    score = 0.60 if best_dist <= 1 else 0.45
    return (token, round(score, 3), 'fuzzy_ortho_match')


def match_phonetic(
    token: str,
    norm_token: str,
    phonetic_patterns,
) -> Optional[tuple[str, float, str]]:
    for ipa_str, compiled_pattern in phonetic_patterns:
        if compiled_pattern.fullmatch(norm_token):
            return (token, 0.30, 'romanized_phonetic_match')
    return None


def confidence_label(score: float) -> str:
    if score >= 0.70:
        return 'high'
    elif score >= 0.40:
        return 'medium'
    else:
        return 'low'


# ============================================================================
# Reference form extraction from review_data
# ============================================================================

def _iter_concepts(review_data: dict):
    concepts = review_data.get('concepts', [])
    if isinstance(concepts, dict):
        yield from concepts.values()
    else:
        yield from concepts


def _get_concept_by_id(concept_id: str, review_data: dict) -> Optional[dict]:
    for c in _iter_concepts(review_data):
        c_id = str(c.get('id', c.get('concept_id', '')))
        if c_id == concept_id:
            return c
    return None


def get_all_concept_ids(review_data: dict) -> list[str]:
    ids = []
    for c in _iter_concepts(review_data):
        c_id = str(c.get('id', c.get('concept_id', '')))
        if c_id:
            ids.append(c_id)
    try:
        ids.sort(key=int)
    except ValueError:
        ids.sort()
    return ids


def get_all_speakers(review_data: dict) -> list[str]:
    speakers: set[str] = set()
    for c in _iter_concepts(review_data):
        speakers.update(c.get('speakers', {}).keys())
    return sorted(speakers)


def _expected_anchor_time(
    concept_id: str,
    anchors: dict,
    *,
    exclude_speaker: Optional[str] = None,
) -> Optional[float]:
    """Return the median anchor timestamp for a concept across available speakers."""
    anchor_times: list[float] = []
    for speaker, anchor_entry in anchors.items():
        if exclude_speaker and speaker == exclude_speaker:
            continue
        if not isinstance(anchor_entry, dict):
            continue
        timestamps = anchor_entry.get('timestamps')
        if not isinstance(timestamps, dict):
            continue
        ts = timestamps.get(str(concept_id))
        try:
            ts_val = float(ts)
        except (TypeError, ValueError):
            continue
        if math.isfinite(ts_val) and ts_val >= 0:
            anchor_times.append(ts_val)

    if not anchor_times:
        return None

    anchor_times.sort()
    mid = len(anchor_times) // 2
    if len(anchor_times) % 2 == 1:
        return anchor_times[mid]
    return (anchor_times[mid - 1] + anchor_times[mid]) / 2.0


def _speaker_has_concept(speaker: str, concept_data: dict, require_verified: bool = False) -> bool:
    entry = concept_data.get('speakers', {}).get(speaker)
    if entry is None:
        return False

    status = str(entry.get('status', '')).lower().strip()

    if status in _MISSING_STATUSES:
        return False

    if require_verified and status not in _VERIFIED_STATUSES:
        return False

    ortho = entry.get('ortho', entry.get('transcription', '')).strip()
    ipa = entry.get('ipa', entry.get('phonemic', '')).strip()
    if ortho in ('?', '', '-') and ipa in ('?', '', '-'):
        return False
    return True


def _speaker_is_missing(speaker: str, concept_data: dict) -> bool:
    return not _speaker_has_concept(speaker, concept_data, require_verified=False)


def collect_reference_forms(
    concept_data: dict,
    target_speaker: str,
    require_verified: bool = True,
) -> tuple[list[str], list[str]]:
    ortho: set[str] = set()
    ipa: set[str] = set()

    for speaker, entry in concept_data.get('speakers', {}).items():
        if speaker == target_speaker:
            continue
        if not _speaker_has_concept(speaker, concept_data, require_verified=require_verified):
            continue

        o = entry.get('ortho', entry.get('transcription', '')).strip()
        i = entry.get('ipa', entry.get('phonemic', '')).strip()

        if o and o not in ('?', '-'):
            ortho.add(o)
        if i and i not in ('?', '-'):
            ipa.add(i)

    return sorted(ortho), sorted(ipa)


def get_concept_en(concept_data: dict) -> str:
    for key in ('concept_en', 'gloss_en', 'english', 'gloss'):
        val = concept_data.get(key, '')
        if val:
            return str(val)
    return str(concept_data.get('id', concept_data.get('concept_id', '')))


# ============================================================================
# AI provider configuration
# ============================================================================

def load_ai_config(project_file: Optional[str]) -> dict:
    config: dict = {
        'enabled': bool(os.environ.get(_DEFAULT_AI_API_KEY_ENV, '')),
        'provider': _DEFAULT_AI_PROVIDER,
        'model': _DEFAULT_AI_MODEL,
        'api_key_env': _DEFAULT_AI_API_KEY_ENV,
    }

    if not project_file:
        return config

    project_path = Path(project_file)
    if not project_path.exists():
        print(
            f'[WARN] project.json not found: {project_path} — falling back to default Anthropic config',
            file=sys.stderr,
        )
        return config

    try:
        with project_path.open('r', encoding='utf-8') as fh:
            project_data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f'[WARN] Failed to load project config {project_path}: {exc} — '
            'falling back to default Anthropic config',
            file=sys.stderr,
        )
        return config

    ai_block = project_data.get('ai')
    if not isinstance(ai_block, dict):
        return config

    provider = str(ai_block.get('provider') or _DEFAULT_AI_PROVIDER).strip().lower()
    model = str(ai_block.get('model') or _DEFAULT_AI_MODEL).strip() or _DEFAULT_AI_MODEL
    api_key_env = str(ai_block.get('api_key_env') or _DEFAULT_AI_API_KEY_ENV).strip() or _DEFAULT_AI_API_KEY_ENV

    return {
        'enabled': bool(ai_block.get('enabled', False)),
        'provider': provider,
        'model': model,
        'api_key_env': api_key_env,
    }


def llm_strategy_enabled(ai_config: Optional[dict]) -> bool:
    if not ai_config:
        return False

    if not ai_config.get('enabled', False):
        return False

    provider = str(ai_config.get('provider', _DEFAULT_AI_PROVIDER)).strip().lower()
    api_key_env = str(ai_config.get('api_key_env', _DEFAULT_AI_API_KEY_ENV)).strip() or _DEFAULT_AI_API_KEY_ENV

    if provider not in {'anthropic', 'openai', 'ollama'}:
        print(
            f'[WARN] Strategy 4 disabled: unknown AI provider {provider}',
            file=sys.stderr,
        )
        return False

    if provider in {'anthropic', 'openai'} and not os.environ.get(api_key_env, ''):
        print(
            f'[WARN] Strategy 4 disabled: {provider} requires env var {api_key_env}',
            file=sys.stderr,
        )
        return False

    return True


def call_llm(prompt: str, config: dict) -> str:
    """Call the configured LLM provider and return plain response text."""
    provider = str(config.get('provider', _DEFAULT_AI_PROVIDER)).strip().lower() or _DEFAULT_AI_PROVIDER
    model = str(config.get('model', _DEFAULT_AI_MODEL)).strip() or _DEFAULT_AI_MODEL
    api_key_env = str(config.get('api_key_env', _DEFAULT_AI_API_KEY_ENV)).strip() or _DEFAULT_AI_API_KEY_ENV
    api_key = os.environ.get(api_key_env, '')

    try:
        if provider == 'anthropic':
            if not api_key:
                raise RuntimeError(f'Anthropic API key env var {api_key_env} is not set')

            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{'role': 'user', 'content': prompt}],
            )
            if not msg.content:
                raise RuntimeError('Anthropic returned empty content')
            return msg.content[0].text

        elif provider == 'openai':
            if not api_key:
                raise RuntimeError(f'OpenAI API key env var {api_key_env} is not set')

            import openai

            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=1024,
            )
            if not resp.choices:
                raise RuntimeError('OpenAI returned no choices')
            return resp.choices[0].message.content or ''

        elif provider == 'ollama':
            import json as _json
            import urllib.request

            ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
            payload = _json.dumps({'model': model, 'prompt': prompt, 'stream': False}).encode()
            req = urllib.request.Request(
                f'{ollama_host}/api/generate',
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=120) as response:
                data = _json.loads(response.read())
            return str(data.get('response', ''))

        else:
            raise RuntimeError(f'Unknown AI provider: {provider}')

    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f'{provider} LLM call failed: {exc}') from exc


# ============================================================================
# Transcript loading
# ============================================================================

def load_transcript(speaker: str, transcripts_dir: str) -> Optional[dict]:
    path = os.path.join(transcripts_dir, f'{speaker}.json')
    if not os.path.exists(path):
        print(f'  [WARN] No transcript for {speaker}: {path}', file=sys.stderr)
        return None
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


# ============================================================================
# Core suggestion finder for one concept × speaker
# ============================================================================

def find_suggestions_for_pair(
    concept_id: str,
    target_speaker: str,
    transcript: dict,
    ortho_forms: list[str],
    ipa_forms: list[str],
    top_n: int = 25,
    reference_source: str = "verified",
    expected_time_sec: Optional[float] = None,
) -> list[dict]:
    segments = transcript.get('segments', [])
    if not segments:
        return []

    source_wav: str = transcript.get('source_wav', '')

    norm_ortho_forms = [normalize_text_for_match(f) for f in ortho_forms]

    phonetic_patterns = []
    for ipa_str in ipa_forms:
        pattern = ipa_to_regex(ipa_str)
        if not pattern:
            continue
        try:
            phonetic_patterns.append((ipa_str, re.compile(rf'^{pattern}$')))
        except re.error:
            continue

    candidates: list[dict] = []

    for seg in segments:
        start_sec: float = float(seg.get('start', 0.0))
        end_sec: float = float(seg.get('end', start_sec + 3.0))
        text: str = seg.get('text', '')

        if not text.strip():
            continue

        tokens = tokenize(text)
        if not tokens:
            continue

        best_result: Optional[tuple[str, float, str]] = None

        for token in tokens:
            if not token:
                continue

            norm_token = normalize_text_for_match(token)

            result = match_exact(token, norm_token, ortho_forms, norm_ortho_forms)
            if result:
                _, score, _ = result
                if best_result is None or score > best_result[1]:
                    best_result = result
                break

            result = match_fuzzy(token, norm_token, ortho_forms, norm_ortho_forms)
            if result:
                _, score, _ = result
                if best_result is None or score > best_result[1]:
                    best_result = result
                continue

            if best_result is None or best_result[2] == 'romanized_phonetic_match':
                result = match_phonetic(token, norm_token, phonetic_patterns)
                if result:
                    _, score, _ = result
                    if best_result is None or score > best_result[1]:
                        best_result = result

        if best_result is None:
            continue

        matched_token, score, method = best_result

        if score < 0.20:
            continue

        label = confidence_label(score)

        suggestion: dict = {
            'source_wav': source_wav,
            'segment_start_sec': round(start_sec, 3),
            'segment_end_sec': round(end_sec, 3),
            'transcript_text': text,
            'matched_token': matched_token,
            'confidence': label,
            'confidence_score': round(score, 3),
            'method': method,
            'reference_form_source': reference_source,
        }

        if method == 'exact_ortho_match':
            suggestion['note'] = 'Timestamp is segment start — target word occurs somewhere within this ~3s window'
        elif method == 'romanized_phonetic_match':
            suggestion['note'] = f'Phonetic match against IPA reference forms: {", ".join(ipa_forms[:3])}'

        candidates.append(suggestion)

    if expected_time_sec is not None and math.isfinite(expected_time_sec):
        candidates.sort(
            key=lambda x: (
                -x['confidence_score'],
                abs(x['segment_start_sec'] - expected_time_sec),
                x['segment_start_sec'],
            )
        )
    else:
        candidates.sort(
            key=lambda x: (-x['confidence_score'], x['segment_start_sec'])
        )

    seen_starts: set[float] = set()
    deduped: list[dict] = []
    for c in candidates:
        k = c['segment_start_sec']
        if k not in seen_starts:
            seen_starts.add(k)
            deduped.append(c)

    if top_n < 1 or len(deduped) <= top_n:
        return deduped

    cutoff_score = deduped[top_n - 1]['confidence_score']
    rerank_floor = max(0.0, cutoff_score - _MAX_POSITIONAL_BOOST)

    selected: list[dict] = []
    for candidate in deduped:
        candidate_score = candidate['confidence_score']
        if len(selected) < top_n:
            selected.append(candidate)
            continue
        if candidate_score == cutoff_score or candidate_score >= rerank_floor:
            selected.append(candidate)
            continue
        break

    return selected


# ============================================================================
# Positional anchors
# ============================================================================

def load_anchors(anchors_file: Optional[str]) -> dict:
    if not anchors_file:
        return {}
    if not os.path.exists(anchors_file):
        print(f'[WARN] Anchors file not found: {anchors_file}', file=sys.stderr)
        return {}
    with open(anchors_file, 'r', encoding='utf-8') as fh:
        return json.load(fh)


# ============================================================================
# Main generation pipeline
# ============================================================================

def generate_all_suggestions(
    review_data: dict,
    transcripts_dir: str,
    anchors: dict,
    top_n: int = 25,
    ai_config: Optional[dict] = None,
) -> dict:
    concept_ids = get_all_concept_ids(review_data)
    all_speakers = get_all_speakers(review_data)

    print(f'[INFO] {len(concept_ids)} concepts × {len(all_speakers)} speakers', file=sys.stderr)

    if not llm_strategy_enabled(ai_config):
        print('[INFO] Strategy 4 (LLM-assisted) disabled or unavailable; using strategies 1-3 only', file=sys.stderr)

    transcripts: dict[str, dict] = {}
    for speaker in all_speakers:
        t = load_transcript(speaker, transcripts_dir)
        if t is not None:
            transcripts[speaker] = t

    print(f'[INFO] Loaded transcripts for {len(transcripts)}/{len(all_speakers)} speakers', file=sys.stderr)

    suggestions_out: dict[str, dict] = {}
    total_pairs = 0
    total_suggestions = 0

    for concept_id in concept_ids:
        concept_data = _get_concept_by_id(concept_id, review_data)
        if concept_data is None:
            continue

        concept_en = get_concept_en(concept_data)

        all_ortho_forms, all_ipa_forms = collect_reference_forms(
            concept_data, target_speaker='__none__', require_verified=True
        )
        global_used_verified = True

        if not all_ortho_forms and not all_ipa_forms:
            all_ortho_forms, all_ipa_forms = collect_reference_forms(
                concept_data, target_speaker='__none__', require_verified=False
            )
            global_used_verified = False
            if all_ortho_forms or all_ipa_forms:
                print(
                    f'  [WARN] Concept {concept_id} ({concept_en}): '
                    f'using UNVERIFIED reference forms (no verified speakers yet)',
                    file=sys.stderr,
                )

        if not all_ortho_forms and not all_ipa_forms:
            print(f'  [SKIP] Concept {concept_id} ({concept_en}): no reference forms', file=sys.stderr)
            continue

        concept_entry: dict = {
            'concept_en': concept_en,
            'reference_forms': sorted(set(all_ortho_forms) | set(all_ipa_forms)),
            'speakers': {},
        }

        for speaker in all_speakers:
            if not _speaker_is_missing(speaker, concept_data):
                continue

            if speaker not in transcripts:
                continue

            used_verified_for_speaker = True
            ortho_forms, ipa_forms = collect_reference_forms(
                concept_data, speaker, require_verified=True
            )

            if not ortho_forms and not ipa_forms:
                ortho_forms, ipa_forms = collect_reference_forms(
                    concept_data, speaker, require_verified=False
                )
                used_verified_for_speaker = False

            if not ortho_forms and not ipa_forms:
                ortho_forms = all_ortho_forms
                ipa_forms = all_ipa_forms
                used_verified_for_speaker = global_used_verified

            suggestions = find_suggestions_for_pair(
                concept_id=concept_id,
                target_speaker=speaker,
                transcript=transcripts[speaker],
                ortho_forms=ortho_forms,
                ipa_forms=ipa_forms,
                top_n=top_n,
                reference_source="verified" if used_verified_for_speaker else "unverified_fallback",
                expected_time_sec=_expected_anchor_time(
                    concept_id,
                    anchors,
                    exclude_speaker=speaker,
                ),
            )

            if suggestions:
                concept_entry['speakers'][speaker] = suggestions
                total_pairs += 1
                total_suggestions += len(suggestions)
                best = suggestions[0]
                print(
                    f'  [{concept_id}] {concept_en} × {speaker}: '
                    f'{len(suggestions)} candidates '
                    f'(best {best["confidence_score"]:.2f} via {best["method"]})',
                    file=sys.stderr,
                )

        if concept_entry['speakers']:
            suggestions_out[concept_id] = concept_entry

    print(
        f'\n[INFO] Done: {len(suggestions_out)} concepts with suggestions, '
        f'{total_pairs} speaker pairs, {total_suggestions} total candidates',
        file=sys.stderr,
    )

    return {
        'positional_anchors': anchors,
        'suggestions': suggestions_out,
    }


# ============================================================================
# CLI
# ============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Generate ai_suggestions.json with base confidence scores '
            '(no positional boost) for the Source Explorer review tool.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Confidence bands (base score, before client-side positional boost):\n'
            '  0.70–1.00  → exact orthographic match  (high)\n'
            '  0.40–0.69  → fuzzy orthographic match   (medium)\n'
            '  0.20–0.39  → romanized phonetic match   (low)\n'
            '  < 0.20     → not included\n'
            '\n'
            'Fuzzy distance thresholds:\n'
            '  token ≤4 chars → Levenshtein ≤1\n'
            '  token >4 chars → Levenshtein ≤2\n'
        ),
    )
    parser.add_argument(
        '--review-data',
        required=True,
        metavar='FILE',
        help='Path to review_data.json (source of reference ortho/IPA forms and missing flags)',
    )
    parser.add_argument(
        '--transcripts-dir',
        required=True,
        metavar='DIR',
        help='Directory containing coarse_transcripts/<Speaker>.json files',
    )
    parser.add_argument(
        '--anchors',
        default=None,
        metavar='FILE',
        help='Path to positional anchors JSON (speaker → concept → timestamp).',
    )
    parser.add_argument(
        '--project',
        default=None,
        metavar='FILE',
        help='Optional path to project.json for AI provider configuration.',
    )
    parser.add_argument(
        '--output',
        required=True,
        metavar='FILE',
        help='Output path for ai_suggestions.json',
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=25,
        metavar='N',
        help=(
            'Target suggestions per concept × speaker pair before client-side positional '
            're-ranking retention widens the pool when needed (default: 25)'
        ),
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if not os.path.exists(args.review_data):
        print(f'[ERROR] review_data file not found: {args.review_data}', file=sys.stderr)
        sys.exit(1)

    print(f'[INFO] Loading review data: {args.review_data}', file=sys.stderr)
    with open(args.review_data, 'r', encoding='utf-8') as fh:
        review_data = json.load(fh)

    print(f'[INFO] Loading anchors: {args.anchors or "(none)"}', file=sys.stderr)
    anchors = load_anchors(args.anchors)

    if args.project:
        print(f'[INFO] Loading project config: {args.project}', file=sys.stderr)
    ai_config = load_ai_config(args.project)

    if not os.path.isdir(args.transcripts_dir):
        print(f'[ERROR] transcripts-dir is not a directory: {args.transcripts_dir}', file=sys.stderr)
        sys.exit(1)
    if args.top_n < 1:
        print(f'[ERROR] --top-n must be >= 1 (got {args.top_n})', file=sys.stderr)
        sys.exit(1)

    output = generate_all_suggestions(
        review_data=review_data,
        transcripts_dir=args.transcripts_dir,
        anchors=anchors,
        top_n=args.top_n,
        ai_config=ai_config,
    )

    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)

    with open(args.output, 'w', encoding='utf-8') as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    concept_count = len(output.get('suggestions', {}))
    total_sug = sum(
        sum(len(v) for v in entry.get('speakers', {}).values())
        for entry in output.get('suggestions', {}).values()
    )
    print(f'[INFO] Wrote: {args.output} ({concept_count} concepts, {total_sug} suggestions total)', file=sys.stderr)


if __name__ == '__main__':
    main()
