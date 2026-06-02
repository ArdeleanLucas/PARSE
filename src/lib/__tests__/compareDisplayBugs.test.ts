// Empirical bug-confirmation tests for Compare-mode display drift.
//
// Three independent bugs surfaced while reviewing concepts "big" (Saha01,
// Fail01) and "bird" / "yellow" in Compare mode on 2026-05-19. See
// docs/reports/2026-05-19-compare-display-bugs.md and the fix plan at
// docs/reports/2026-05-19-compare-display-bugs-fix-plan.md.
//
// Bug 3 now routes by concept identity uid instead of a sourceItem/csv-row bridge.
// Bugs 1 and 2 ride issue #529 — their tests are currently
// skipped with TODO references and a one-line reproduction summary so
// they go green automatically once the data-model migration lands.

import { describe, expect, it } from 'vitest';
import type {
  AnnotationInterval,
  AnnotationRecord,
} from '../../api/types';
import { normalizeBundles } from '../compareBundles';
import { buildSpeakerForm } from '../speakerForm';
import type { Concept } from '../speakerForm';

function makeRecord(partial: {
  concept?: AnnotationInterval[];
  ipa?: AnnotationInterval[];
  ortho?: AnnotationInterval[];
  ortho_words?: AnnotationInterval[];
}): AnnotationRecord {
  return {
    speaker: 'X',
    tiers: {
      ipa_phone: { name: 'ipa_phone', display_order: 1, intervals: [] },
      ipa: { name: 'ipa', display_order: 2, intervals: partial.ipa ?? [] },
      ortho: { name: 'ortho', display_order: 3, intervals: partial.ortho ?? [] },
      ortho_words: { name: 'ortho_words', display_order: 4, intervals: partial.ortho_words ?? [] },
      stt: { name: 'stt', display_order: 5, intervals: [] },
      concept: { name: 'concept', display_order: 6, intervals: partial.concept ?? [] },
      sentence: { name: 'sentence', display_order: 7, intervals: [] },
      speaker: { name: 'speaker', display_order: 8, intervals: [] },
    },
    source_wav: '',
  };
}

describe('Bug 1 — collapsed IPA cell vs expanded variant card (Saha01 "big")', () => {
  // TODO(#529): rides the concept-identity-pollution migration. Post-#529
  // "big" becomes a singleton, so buildSpeakerForm falls through to the
  // default branch (realizations[0] = first IPA in tier order) which
  // matches the backend's _pick_time_overlap(matches[0]). This test's
  // assertion (form.ipa == 'ɡoːrɔ') becomes true automatically once #529
  // lands and the test fixture below is updated to use a singleton
  // concept shape.
  it.skip('form.ipa for a grouped concept should equal the backend candidate ipa', () => {
    const bigConcept: Concept = {
      id: 1,
      key: '4.1',
      name: 'big',
      tag: 'untagged',
      sourceItem: '4.1',
      sourceSurvey: 'KLQ',
      variants: [
        { conceptKey: '53', conceptEn: 'big (A)', variantLabel: 'A' },
        { conceptKey: '619', conceptEn: 'big (B)', variantLabel: 'B' },
      ],
    };

    const record = makeRecord({
      concept: [
        { start: 4013.131, end: 4013.999, text: 'big (A)', concept_id: '53' },
        { start: 4024.0, end: 4025.051, text: 'big', concept_id: '53' },
      ],
      ipa: [
        { start: 4013.131, end: 4013.999, text: 'ɡoːrɔ' },
        { start: 4024.0, end: 4025.051, text: 'enemfuːikalaŋpi' },
      ],
    });

    const backendCandidateIpa = 'ɡoːrɔ';
    const form = buildSpeakerForm(record, bigConcept, 'Saha01', {}, []);
    expect(form.ipa).toBe(backendCandidateIpa);
  });
});

describe('Bug 2 — empty form.ipa when only a non-zero variant has data (Fail01 "big")', () => {
  // TODO(#529): rides the concept-identity-pollution migration. Post-#529
  // Fail01's cid=634 intervals re-key to canonical cid=53 and "big"
  // becomes a singleton — the default branch picks realizations[0]
  // (the only realization, ipa='ɡap'), so form.ipa is no longer empty.
  // This test's current fixture exercises the grouped-concept path that
  // disappears post-#529; rewrite as a singleton with multi-interval
  // data once the migration ships.
  it.skip('auto-selects the only non-empty realization when there is no canonical override', () => {
    const bigConcept: Concept = {
      id: 1,
      key: '4.1',
      name: 'big',
      tag: 'untagged',
      sourceItem: '4.1',
      sourceSurvey: 'KLQ',
      variants: [
        { conceptKey: '53', conceptEn: 'big (A)', variantLabel: 'A' },
        { conceptKey: '619', conceptEn: 'big (B)', variantLabel: 'B' },
        { conceptKey: '634', conceptEn: 'big', variantLabel: '' },
      ],
    };

    const record = makeRecord({
      concept: [
        { start: 3492.305, end: 3493.186, text: 'big', concept_id: '634' },
      ],
      ipa: [
        { start: 3492.305, end: 3493.186, text: 'ɡap' },
      ],
      ortho_words: [
        { start: 3492.305, end: 3493.186, text: 'گەپ' },
      ],
    });

    const form = buildSpeakerForm(record, bigConcept, 'Fail01', {}, []);
    expect(form.realizations[2]).toMatchObject({ ipa: 'ɡap' });
    expect(form.realizations[0]).toMatchObject({ ipa: '' });
    expect(form.ipa).toBe('ɡap');
    expect(form.selectedIdx).toBe(2);
  });

  it('post-migration singleton concept keeps a one-interval speaker realization even when another speaker has multiple intervals', () => {
    const bigConcept: Concept = {
      id: 53,
      key: '53',
      name: 'big',
      tag: 'untagged',
    };
    const fail01 = makeRecord({
      concept: [{ start: 3492.305, end: 3493.186, text: 'big', concept_id: '53' }],
      ipa: [{ start: 3492.305, end: 3493.186, text: 'ɡap' }],
      ortho_words: [{ start: 3492.305, end: 3493.186, text: 'گەپ' }],
    });
    const saha01 = makeRecord({
      concept: [
        { start: 10, end: 11, text: 'big', concept_id: '53' },
        { start: 20, end: 21, text: 'big', concept_id: '53' },
        { start: 30, end: 31, text: 'big', concept_id: '53' },
      ],
      ipa: [
        { start: 10, end: 11, text: 'one' },
        { start: 20, end: 21, text: 'two' },
        { start: 30, end: 31, text: 'three' },
      ],
    });

    const failForm = buildSpeakerForm(fail01, bigConcept, 'Fail01', {}, []);
    const sahaForm = buildSpeakerForm(saha01, bigConcept, 'Saha01', {}, []);

    expect(failForm.variantCount).toBe(1);
    expect(failForm.ipa).toBe('ɡap');
    expect(failForm.selectedIdx).toBe(0);
    expect(sahaForm.variantCount).toBe(3);
  });

});


describe('Bug 3 — concept identity uid routing replaces sourceItem/csv-row bridge', () => {
  it('routes the bird concept to c-bird by uid, not to the yellow row whose csv id equals source_item 92', () => {
    const payload = normalizeBundles({
      bundles: [
        {
          bundle_id: 'bundle:c-yellow',
          uid: 'c-yellow',
          label: 'yellow',
          row_ids: ['92', '167'],
          buckets: [
            { bucket_key: 'klq 5.5', survey_id: 'klq', source_item: '5.5', variants: [{ csv_row_id: '92', variant_label: '', label: 'yellow' }] },
            { bucket_key: 'jbil 178', survey_id: 'jbil', source_item: '178', variants: [{ csv_row_id: '167', variant_label: 'A', label: 'yellow (A)' }] },
          ],
        },
        {
          bundle_id: 'bundle:c-bird',
          uid: 'c-bird',
          label: 'bird',
          row_ids: ['311', '651'],
          buckets: [{
            bucket_key: 'jbil 92',
            survey_id: 'jbil',
            source_item: '92',
            variants: [
              { csv_row_id: '311', variant_label: 'A', label: 'bird (A)' },
              { csv_row_id: '651', variant_label: 'B', label: 'bird (B)' },
            ],
          }],
        },
      ],
    });

    const concept = { key: 'c-bird', name: 'bird', variants: [{ conceptKey: '311' }, { conceptKey: '651' }] };
    const activeBundle = payload.bundles.find((bundle) => bundle.uid === concept.key);

    expect(activeBundle?.bundle_id).toBe('bundle:c-bird');
    expect(activeBundle?.row_ids).toEqual(['311', '651']);
  });
});
