// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { CompareTabContent } from './right-panel/CompareTabContent';
import { AnnotateTabContent } from './right-panel/AnnotateTabContent';
import { SpeakersSection } from './right-panel/SpeakersSection';

describe('right-panel module barrels', () => {
  it('exports the extracted tab and shared section modules', () => {
    expect(CompareTabContent).toBeTypeOf('function');
    expect(AnnotateTabContent).toBeTypeOf('function');
    expect(SpeakersSection).toBeTypeOf('function');
  });
});
