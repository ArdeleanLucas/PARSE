import { describe, expect, it } from 'vitest';
import {
  COMPARE_COMPUTE_MODES,
  isCompareComputeMode,
  isCompareRunDisabled,
  isOffsetPhase,
  type CompareComputeMode,
} from './compareComputeContract';

describe('compareComputeContract', () => {
  it('defines the active compare compute modes explicitly', () => {
    const modes: CompareComputeMode[] = [...COMPARE_COMPUTE_MODES];
    expect(modes).toEqual(['cognates', 'similarity', 'contact-lexemes']);
  });

  it('accepts only supported compare compute modes', () => {
    expect(isCompareComputeMode('cognates')).toBe(true);
    expect(isCompareComputeMode('similarity')).toBe(true);
    expect(isCompareComputeMode('contact-lexemes')).toBe(true);
    expect(isCompareComputeMode('ipa')).toBe(false);
  });

  it('tracks the full offset-phase surface used by ParseUI', () => {
    expect(isOffsetPhase('idle')).toBe(true);
    expect(isOffsetPhase('manual')).toBe(true);
    expect(isOffsetPhase('detecting')).toBe(true);
    expect(isOffsetPhase('detected')).toBe(true);
    expect(isOffsetPhase('applying')).toBe(true);
    expect(isOffsetPhase('applied')).toBe(true);
    expect(isOffsetPhase('error')).toBe(true);
    expect(isOffsetPhase('ready')).toBe(false);
  });

  it('keeps contact-lexeme Run independent from selected compare speakers', () => {
    expect(
      isCompareRunDisabled({
        computeMode: 'contact-lexemes',
        selectedSpeakersCount: 0,
        crossSpeakerJobStatus: 'idle',
        computeJobStatus: 'running',
      }),
    ).toBe(false);
    expect(
      isCompareRunDisabled({
        computeMode: 'similarity',
        selectedSpeakersCount: 0,
        crossSpeakerJobStatus: 'idle',
        computeJobStatus: 'idle',
      }),
    ).toBe(true);
  });
});
