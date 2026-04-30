// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { AnnotationInterval, AnnotationRecord, Tag as StoreTag } from '../api/types';
import {
  conceptMatchesIntervalText,
  deriveAudioUrl,
  getConceptStatus,
  isInteractiveHotkeyTarget,
  isRecord,
  overlaps,
  readTextBlob,
  resolveAssetUrl,
} from './parseUIUtils';

function makeRecord(overrides: Partial<AnnotationRecord> = {}): AnnotationRecord {
  return {
    speaker: 'Fail02',
    tiers: {
      ipa_phone: { name: 'ipa_phone', display_order: 1, intervals: [] },
      ipa: { name: 'ipa', display_order: 2, intervals: [] },
      ortho: { name: 'ortho', display_order: 3, intervals: [] },
      ortho_words: { name: 'ortho_words', display_order: 4, intervals: [] },
      stt: { name: 'stt', display_order: 5, intervals: [] },
      concept: { name: 'concept', display_order: 6, intervals: [] },
      sentence: { name: 'sentence', display_order: 7, intervals: [] },
      speaker: { name: 'speaker', display_order: 8, intervals: [] },
    },
    source_wav: '',
    ...overrides,
  };
}

describe('parseUIUtils', () => {
  it('detects interactive form controls and contenteditable nodes for global hotkey suppression', () => {
    const input = document.createElement('input');
    const editable = document.createElement('div');
    Object.defineProperty(editable, 'isContentEditable', { value: true, configurable: true });
    const plain = document.createElement('div');

    expect(isInteractiveHotkeyTarget(input)).toBe(true);
    expect(isInteractiveHotkeyTarget(editable)).toBe(true);
    expect(isInteractiveHotkeyTarget(plain)).toBe(false);
    expect(isInteractiveHotkeyTarget(null)).toBe(false);
  });

  it('treats touching intervals as overlapping', () => {
    const left: AnnotationInterval = { start: 1, end: 2, text: 'a' };
    const right: AnnotationInterval = { start: 2, end: 3, text: 'b' };
    const far: AnnotationInterval = { start: 3.1, end: 4, text: 'c' };

    expect(overlaps(left, right)).toBe(true);
    expect(overlaps(left, far)).toBe(false);
  });

  it('normalizes source audio paths into workspace-rooted URLs', () => {
    expect(deriveAudioUrl(makeRecord({ source_audio: 'audio/working/Fail02/foo.wav' }), { dev: false })).toBe('/audio/working/Fail02/foo.wav');
    expect(deriveAudioUrl(makeRecord({ source_wav: '///audio\\legacy\\Fail02.wav' }), { dev: false })).toBe('/audio/legacy/Fail02.wav');
    expect(deriveAudioUrl(makeRecord(), { dev: false })).toBe('');
    expect(deriveAudioUrl(null, { dev: false })).toBe('');
  });

  it('routes heavy media assets directly to the backend target during dev', () => {
    expect(resolveAssetUrl('/peaks/Fail01.json', { dev: true, apiTarget: 'http://127.0.0.1:8866' })).toBe('http://127.0.0.1:8866/peaks/Fail01.json');
    expect(deriveAudioUrl(makeRecord({ source_audio: 'audio/working/Fail02/foo.wav' }), { dev: true, apiTarget: 'http://127.0.0.1:8866/' })).toBe('http://127.0.0.1:8866/audio/working/Fail02/foo.wav');
  });

  it('matches concept intervals by stringified concept_id equality', () => {
    expect(conceptMatchesIntervalText({ id: 226 }, '226')).toBe(true);
  });

  it('matches when the concept id is provided as a string', () => {
    expect(conceptMatchesIntervalText({ id: '226' }, '226')).toBe(true);
  });

  it('returns false when interval concept_id belongs to another concept', () => {
    expect(conceptMatchesIntervalText({ id: 226 }, '227')).toBe(false);
  });

  it('returns false when interval concept_id is missing', () => {
    expect(conceptMatchesIntervalText({ id: 226 }, null)).toBe(false);
  });

  it('returns false when interval concept_id is empty', () => {
    expect(conceptMatchesIntervalText({ id: 226 }, '')).toBe(false);
  });

  it('has no text parameter in the public matcher contract', () => {
    expect(conceptMatchesIntervalText.length).toBe(2);
  });

  it('prioritizes problematic then confirmed then review tags when deriving concept status', () => {
    const tag = (id: string): StoreTag => ({ id, label: id, color: '#000000', concepts: [] });

    expect(getConceptStatus([tag('review')])).toBe('review');
    expect(getConceptStatus([tag('confirmed'), tag('review')])).toBe('confirmed');
    expect(getConceptStatus([tag('problematic'), tag('confirmed')])).toBe('problematic');
    expect(getConceptStatus([])).toBe('untagged');
  });

  it('recognizes plain objects and rejects arrays/null', () => {
    expect(isRecord({ a: 1 })).toBe(true);
    expect(isRecord(['a'])).toBe(false);
    expect(isRecord(null)).toBe(false);
    expect(isRecord('x')).toBe(false);
  });

  it('reads text blobs through FileReader', async () => {
    await expect(readTextBlob(new Blob(['slaw']))).resolves.toBe('slaw');
  });
});
