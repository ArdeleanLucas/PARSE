import { describe, expect, it } from 'vitest';

import { assignVariantLetters } from '../conceptGrouping';
import fixture from '../../../tests/fixtures/variant-letters.json';

type VariantLetterCase = {
  name: string;
  input: { start: number }[];
  expected: string[];
};

describe('assignVariantLetters — fixture', () => {
  (fixture.cases as VariantLetterCase[]).forEach((testCase) => {
    it(testCase.name, () => {
      expect(assignVariantLetters(testCase.input)).toEqual(testCase.expected);
    });
  });
});

describe('assignVariantLetters — extra coverage', () => {
  it('assigns A through Z then AA for 27 intervals', () => {
    const input = Array.from({ length: 27 }, (_, i) => ({ start: i }));

    const out = assignVariantLetters(input);

    expect(out[0]).toBe('A');
    expect(out[25]).toBe('Z');
    expect(out[26]).toBe('AA');
  });

  it('preserves input order when every start time ties', () => {
    const input = [{ start: 1 }, { start: 1 }, { start: 1 }];

    expect(assignVariantLetters(input)).toEqual(['A', 'B', 'C']);
  });
});
