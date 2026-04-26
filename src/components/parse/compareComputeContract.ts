import type { ActionJobState } from '../../hooks/useActionJob';

export const COMPARE_COMPUTE_MODES = ['cognates', 'similarity', 'contact-lexemes'] as const;
export type CompareComputeMode = (typeof COMPARE_COMPUTE_MODES)[number];

const COMPARE_COMPUTE_MODE_SET = new Set<string>(COMPARE_COMPUTE_MODES);

export function isCompareComputeMode(value: string): value is CompareComputeMode {
  return COMPARE_COMPUTE_MODE_SET.has(value);
}

export type CompareComputeJobStatus = ActionJobState['status'];

export const OFFSET_PHASES = [
  'idle',
  'manual',
  'detecting',
  'detected',
  'applying',
  'applied',
  'error',
] as const;
export type OffsetPhase = (typeof OFFSET_PHASES)[number];

const OFFSET_PHASE_SET = new Set<string>(OFFSET_PHASES);

export function isOffsetPhase(value: string): value is OffsetPhase {
  return OFFSET_PHASE_SET.has(value);
}

export function isCompareRunDisabled(args: {
  computeMode: CompareComputeMode;
  selectedSpeakersCount: number;
  crossSpeakerJobStatus: CompareComputeJobStatus;
  computeJobStatus: CompareComputeJobStatus;
}): boolean {
  const { computeMode, selectedSpeakersCount, crossSpeakerJobStatus, computeJobStatus } = args;
  if (computeMode === 'contact-lexemes') {
    return crossSpeakerJobStatus === 'running';
  }
  return computeJobStatus === 'running' || selectedSpeakersCount === 0;
}
