// Empirical bug-confirmation tests for Compare-mode display drift.
//
// Three independent bugs surfaced while reviewing concepts "big" (Saha01,
// Fail01) and "bird" / "yellow" in Compare mode on 2026-05-19. See
// docs/reports/2026-05-19-compare-display-bugs.md and the fix plan at
// docs/reports/2026-05-19-compare-display-bugs-fix-plan.md.
//
// Bug 3 (findBundleForConcept namespace collision) is fixed in this PR
// (MC-414-A). Bugs 1 and 2 ride issue #529 — their tests are currently
// skipped with TODO references and a one-line reproduction summary so
// they go green automatically once the data-model migration lands.

import { describe, expect, it } from 'vitest';
import type {
  AnnotationInterval,
  AnnotationRecord,
  CompareBundle,
} from '../../api/types';
import { findBundleForConcept } from '../compareBundles';
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
    const form = buildSpeakerForm(record, bigConcept, 'Saha01', {}, false, []);
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

    const form = buildSpeakerForm(record, bigConcept, 'Fail01', {}, false, []);
    expect(form.realizations[2]).toMatchObject({ ipa: 'ɡap' });
    expect(form.realizations[0]).toMatchObject({ ipa: '' });
    expect(form.ipa).toBe('ɡap');
    expect(form.selectedIdx).toBe(2);
  });
});

describe('Bug 3 — findBundleForConcept collides sourceItem with csv row id', () => {
  // Fixed in MC-414-A. The frontend's conceptGrouping uses sourceItem as
  // the grouped-concept key (e.g. "92" for "bird" rows that share JBIL
  // 92), while bundle.row_ids are csv row ids (e.g. "92" for the "yellow"
  // row). findBundleForConcept conflated the two namespaces.

  it('routes the bird concept to bundle:bird, not bundle:yellow', () => {
    // concepts.csv (anchored to /home/lucas/parse-workspace 2026-05-19):
    //   id=92  yellow      KLQ 5.5
    //   id=167 yellow (A)  JBIL 178
    //   id=311 bird (A)    JBIL 92
    //   id=651 bird (B)    JBIL 92
    const bundleYellow: CompareBundle = {
      bundle_id: 'bundle:yellow',
      label: 'yellow',
      row_ids: ['92', '167'],
      buckets: [
        {
          bucket_key: 'klq 5.5',
          survey_id: 'klq',
          source_item: '5.5',
          variants: [{ csv_row_id: '92', variant_label: '', label: 'yellow' }],
        },
        {
          bucket_key: 'jbil 178',
          survey_id: 'jbil',
          source_item: '178',
          variants: [{ csv_row_id: '167', variant_label: 'A', label: 'yellow (A)' }],
        },
      ],
    };
    const bundleBird: CompareBundle = {
      bundle_id: 'bundle:bird',
      label: 'bird',
      row_ids: ['311', '651'],
      buckets: [
        {
          bucket_key: 'jbil 92',
          survey_id: 'jbil',
          source_item: '92',
          variants: [
            { csv_row_id: '311', variant_label: 'A', label: 'bird (A)' },
            { csv_row_id: '651', variant_label: 'B', label: 'bird (B)' },
          ],
        },
      ],
    };

    // Grouped concept key is the sourceItem "92" (from JBIL 92). It must
    // not be interpreted as a csv row id when the same string appears as
    // a row id in an unrelated bundle.
    const birdConcept = {
      key: '92',
      name: 'bird',
      variants: [{ conceptKey: '311' }, { conceptKey: '651' }],
    };

    expect(findBundleForConcept([bundleYellow, bundleBird], birdConcept)?.bundle_id).toBe('bundle:bird');
  });

  it('routes a residual post-#529 clarifier-suffix grouped concept to its own bundle', () => {
    // Post-#529 simulation against /home/lucas/parse-workspace finds 14
    // grouped buckets where sourceItem is also a csv row id. Sample:
    //   bucket=(JBIL,123)  siblings=[(45,'ice'),(144,'snow')]
    //   sourceItem '123' is csv row id for an unrelated 'to jump' row.
    // Without the fix, findBundleForConcept routes the ice concept to
    // bundle:to-jump because "123" appears as a row id there.
    const bundleToJump: CompareBundle = {
      bundle_id: 'bundle:to-jump',
      label: 'to jump',
      row_ids: ['123'],
      buckets: [{
        bucket_key: 'klq 6.7',
        survey_id: 'klq',
        source_item: '6.7',
        variants: [{ csv_row_id: '123', variant_label: '', label: 'to jump' }],
      }],
    };
    const bundleIce: CompareBundle = {
      bundle_id: 'bundle:ice',
      label: 'ice',
      row_ids: ['45'],
      buckets: [{
        bucket_key: 'jbil 123',
        survey_id: 'jbil',
        source_item: '123',
        variants: [{ csv_row_id: '45', variant_label: '', label: 'ice' }],
      }],
    };
    const bundleSnow: CompareBundle = {
      bundle_id: 'bundle:snow',
      label: 'snow',
      row_ids: ['144'],
      buckets: [{
        bucket_key: 'jbil 123',
        survey_id: 'jbil',
        source_item: '123',
        variants: [{ csv_row_id: '144', variant_label: '', label: 'snow' }],
      }],
    };

    const iceGrouped = {
      key: '123',
      name: 'ice',
      variants: [{ conceptKey: '45' }, { conceptKey: '144' }],
    };
    expect(findBundleForConcept([bundleToJump, bundleIce, bundleSnow], iceGrouped)?.bundle_id).toBe('bundle:ice');
  });

  it('still matches a singleton concept by its csv row id (no variants, no mergedKeys)', () => {
    // Singleton concepts have concept.key = csv row id directly. The fix
    // must not break that path.
    const bundleHair: CompareBundle = {
      bundle_id: 'bundle:hair',
      label: 'hair',
      row_ids: ['1'],
      buckets: [{
        bucket_key: 'klq 1.1',
        survey_id: 'klq',
        source_item: '1.1',
        variants: [{ csv_row_id: '1', variant_label: '', label: 'hair' }],
      }],
    };
    const hairSingleton = { key: '1', name: 'hair' };
    expect(findBundleForConcept([bundleHair], hairSingleton)?.bundle_id).toBe('bundle:hair');
  });

  it('uses mergedKeys (user-merged concepts) before falling back to concept.key', () => {
    // User-merged concepts keep concept.key as the primary's csv row id
    // and expose every underlying csv row id via mergedKeys.
    const bundleA: CompareBundle = {
      bundle_id: 'bundle:alpha',
      label: 'alpha',
      row_ids: ['10'],
      buckets: [{ bucket_key: 'klq 1', survey_id: 'klq', source_item: '1', variants: [{ csv_row_id: '10', variant_label: '', label: 'alpha' }] }],
    };
    const bundleB: CompareBundle = {
      bundle_id: 'bundle:beta',
      label: 'beta',
      row_ids: ['20'],
      buckets: [{ bucket_key: 'klq 2', survey_id: 'klq', source_item: '2', variants: [{ csv_row_id: '20', variant_label: '', label: 'beta' }] }],
    };
    const merged = { key: '10', name: 'alpha', mergedKeys: ['10', '20'] };
    expect(findBundleForConcept([bundleA, bundleB], merged)?.bundle_id).toBe('bundle:alpha');
  });
});
