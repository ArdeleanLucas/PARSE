import { describe, expect, it } from 'vitest';
import type { ConceptEntry } from '../api/types';
import { groupConceptEntries } from './conceptGrouping';

/**
 * INVARIANT GUARD — concept-key namespace integrity.
 *
 * Decision state (speaker_flags, cognate_sets, concept tags, borrowing_flags,
 * canonical selections) is persisted in dicts keyed by `Concept.key`, so
 * `Concept.key` MUST be globally unique and live in a single namespace.
 *
 * The bug (fixed): grouped concepts keyed by `source_item`, a survey-local
 * coordinate sharing the csv-`id` string namespace. JBIL `source_item`s are
 * bare integers, so a grouped key could equal an unrelated concept's id and the
 * two shared one storage slot (e.g. `ice`/`snow` group on "123" == `to jump`).
 *
 * The fix keys every concept by a real csv id (singletons: own id; groups:
 * canonical `min(memberIds)`, matching backend #529). This file is the
 * regression guard. See docs/reports/2026-06-02-concept-key-namespace-collision.md.
 */

// Faithful slice of the live concepts.csv covering the reported concepts plus
// controls. Ids and source_items are the real values.
const FIXTURE: ConceptEntry[] = [
  { id: '322', label: 'leaf', source_item: '102', source_survey: 'JBIL' },     // singleton
  { id: '385', label: 'green', source_item: '177', source_survey: 'JBIL' },    // singleton
  { id: '1', label: 'hair', source_item: '1.1', source_survey: 'KLQ' },        // KLQ group ...
  { id: '599', label: 'hair (collective)', source_item: '1.1', source_survey: 'KLQ' },
  { id: '45', label: 'ice', source_item: '123', source_survey: 'JBIL' },       // JBIL group ice+snow
  { id: '144', label: 'snow', source_item: '123', source_survey: 'JBIL' },
  { id: '123', label: 'to jump', source_item: '7.13', source_survey: 'KLQ' },  // was the collision victim
  { id: '517', label: 'I', source_item: '319', source_survey: 'JBIL' },        // JBIL group I + sentences
  { id: '558', label: 'i am teaching', source_item: '319', source_survey: 'JBIL' },
  { id: '592', label: 'i saw you', source_item: '319', source_survey: 'JBIL' },
  { id: '593', label: 'i see you', source_item: '319', source_survey: 'JBIL' },
  { id: '601', label: 'Im a teacher', source_item: '319', source_survey: 'JBIL' },
  { id: '319', label: 'wood (substance)', source_item: '99', source_survey: 'JBIL' }, // was the collision victim
];

function concepts() {
  return groupConceptEntries(FIXTURE, () => 'untagged');
}

describe('concept-key namespace integrity', () => {
  it('every Concept.key is globally unique (no two concepts share a storage slot)', () => {
    const keys = concepts().map((c) => c.key);
    const dupes = keys.filter((k, i) => keys.indexOf(k) !== i);
    expect(dupes, `duplicate keys: ${JSON.stringify(dupes)}`).toHaveLength(0);
  });

  it('no Concept.key is a survey-local source_item (keys live only in the csv-id namespace)', () => {
    const ids = new Set(FIXTURE.map((e) => e.id));
    // Every key must be a real csv id; a bare source_item would not be in `ids`.
    const keysOutsideIdNamespace = concepts().map((c) => c.key).filter((key) => !ids.has(key));
    expect(keysOutsideIdNamespace).toEqual([]);
  });

  it('grouped concepts key by canonical member id, never the colliding source_item', () => {
    const byName = Object.fromEntries(concepts().map((c) => [c.name, c.key]));
    expect(byName['ice']).toBe('45');   // min(45,144) — not "123" (to jump's id)
    expect(byName['I']).toBe('517');    // min(517,558,592,593,601) — not "319" (wood's id)
    expect(byName['hair']).toBe('1');   // min(1,599)
    // The former collision victims keep their own ids, undisturbed.
    expect(byName['to jump']).toBe('123');
    expect(byName['wood (substance)']).toBe('319');
  });
});
