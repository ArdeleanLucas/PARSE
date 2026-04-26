export const PARSE_DECISIONS_FORMAT = 'parse-decisions/v1' as const;
export const PARSE_DECISIONS_VERSION = 1 as const;
export const PARSE_DECISIONS_FILE_NAME = 'parse-decisions.json';
export const LEGACY_ANNOTATE_REGION_STORAGE_KEY = 'parse-annotate-region-decisions-v1';

export type CognateDecisionValue = 'accepted' | 'split' | 'merge';

export interface CognateDecisionEntry {
  decision: CognateDecisionValue;
  ts: number;
}

export type CognateDecisionMap = Record<string, CognateDecisionEntry>;
export type CognateSetMap = Record<string, Record<string, string[]>>;
export type SpeakerFlagMap = Record<string, Record<string, boolean>>;
export type BorrowingFlagMap = Record<string, Record<string, unknown>>;

export interface CanonicalDecisionManualOverrides {
  cognate_decisions: CognateDecisionMap;
  cognate_sets: CognateSetMap;
  speaker_flags: SpeakerFlagMap;
  borrowing_flags: BorrowingFlagMap;
}

export interface CanonicalDecisionPayload {
  format: typeof PARSE_DECISIONS_FORMAT;
  version: typeof PARSE_DECISIONS_VERSION;
  manual_overrides: CanonicalDecisionManualOverrides;
}

const COGNATE_DECISION_VALUES = new Set<CognateDecisionValue>(['accepted', 'split', 'merge']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function sanitizeCognateDecisionMap(raw: unknown): CognateDecisionMap {
  if (!isRecord(raw)) return {};

  const sanitized: CognateDecisionMap = {};
  for (const [conceptKey, value] of Object.entries(raw)) {
    if (!isRecord(value)) continue;
    if (!COGNATE_DECISION_VALUES.has(value.decision as CognateDecisionValue)) continue;
    sanitized[conceptKey] = {
      decision: value.decision as CognateDecisionValue,
      ts: typeof value.ts === 'number' && Number.isFinite(value.ts) ? value.ts : 0,
    };
  }
  return sanitized;
}

function sanitizeCognateSetMap(raw: unknown): CognateSetMap {
  if (!isRecord(raw)) return {};

  const sanitized: CognateSetMap = {};
  for (const [conceptKey, groups] of Object.entries(raw)) {
    if (!isRecord(groups)) continue;
    const conceptGroups: Record<string, string[]> = {};
    for (const [groupKey, speakers] of Object.entries(groups)) {
      if (!Array.isArray(speakers)) continue;
      conceptGroups[groupKey] = speakers.filter((speaker): speaker is string => typeof speaker === 'string');
    }
    sanitized[conceptKey] = conceptGroups;
  }
  return sanitized;
}

function sanitizeSpeakerFlagMap(raw: unknown): SpeakerFlagMap {
  if (!isRecord(raw)) return {};

  const sanitized: SpeakerFlagMap = {};
  for (const [conceptKey, speakers] of Object.entries(raw)) {
    if (!isRecord(speakers)) continue;
    const conceptFlags: Record<string, boolean> = {};
    for (const [speaker, flagged] of Object.entries(speakers)) {
      if (typeof flagged !== 'boolean') continue;
      conceptFlags[speaker] = flagged;
    }
    sanitized[conceptKey] = conceptFlags;
  }
  return sanitized;
}

function sanitizeBorrowingFlagMap(raw: unknown): BorrowingFlagMap {
  if (!isRecord(raw)) return {};

  const sanitized: BorrowingFlagMap = {};
  for (const [conceptKey, speakers] of Object.entries(raw)) {
    if (!isRecord(speakers)) continue;
    sanitized[conceptKey] = { ...speakers };
  }
  return sanitized;
}

export function getCanonicalManualOverrides(enrichmentData: Record<string, unknown>): CanonicalDecisionManualOverrides {
  const manualOverrides = isRecord(enrichmentData.manual_overrides) ? enrichmentData.manual_overrides : {};
  const manualCognateDecisions = sanitizeCognateDecisionMap(manualOverrides.cognate_decisions);

  return {
    cognate_decisions:
      Object.keys(manualCognateDecisions).length > 0
        ? manualCognateDecisions
        : sanitizeCognateDecisionMap(enrichmentData.cognate_decisions),
    cognate_sets: sanitizeCognateSetMap(manualOverrides.cognate_sets),
    speaker_flags: sanitizeSpeakerFlagMap(manualOverrides.speaker_flags),
    borrowing_flags: sanitizeBorrowingFlagMap(manualOverrides.borrowing_flags),
  };
}

export function getStoredCognateDecision(
  enrichmentData: Record<string, unknown>,
  conceptKey: string,
): CognateDecisionEntry | null {
  return getCanonicalManualOverrides(enrichmentData).cognate_decisions[conceptKey] ?? null;
}

export function buildCognateDecisionPatch(
  conceptKey: string,
  decision: CognateDecisionValue,
  timestamp: number,
): Record<string, unknown> {
  return {
    manual_overrides: {
      cognate_decisions: {
        [conceptKey]: { decision, ts: timestamp },
      },
    },
  };
}

export function buildCanonicalDecisionPayload(
  enrichmentData: Record<string, unknown>,
): CanonicalDecisionPayload {
  return {
    format: PARSE_DECISIONS_FORMAT,
    version: PARSE_DECISIONS_VERSION,
    manual_overrides: getCanonicalManualOverrides(enrichmentData),
  };
}

function hasImportedDecisionContent(overrides: CanonicalDecisionManualOverrides): boolean {
  return (
    Object.keys(overrides.cognate_decisions).length > 0 ||
    Object.keys(overrides.cognate_sets).length > 0 ||
    Object.keys(overrides.speaker_flags).length > 0 ||
    Object.keys(overrides.borrowing_flags).length > 0
  );
}

function normalizeImportedDecisions(raw: unknown): CanonicalDecisionPayload | null {
  if (!isRecord(raw)) return null;
  if (raw.format !== PARSE_DECISIONS_FORMAT) return null;
  if (raw.version !== PARSE_DECISIONS_VERSION) return null;
  if (!isRecord(raw.manual_overrides)) return null;

  const manualSource = raw.manual_overrides;
  const overrides: CanonicalDecisionManualOverrides = {
    cognate_decisions: sanitizeCognateDecisionMap(manualSource.cognate_decisions),
    cognate_sets: sanitizeCognateSetMap(manualSource.cognate_sets),
    speaker_flags: sanitizeSpeakerFlagMap(manualSource.speaker_flags),
    borrowing_flags: sanitizeBorrowingFlagMap(manualSource.borrowing_flags),
  };

  if (!hasImportedDecisionContent(overrides)) return null;

  return {
    format: PARSE_DECISIONS_FORMAT,
    version: PARSE_DECISIONS_VERSION,
    manual_overrides: overrides,
  };
}

export function applyCanonicalDecisionImport(
  currentData: Record<string, unknown>,
  raw: unknown,
): Record<string, unknown> | null {
  const imported = normalizeImportedDecisions(raw);
  if (!imported) return null;

  const { cognate_decisions: _legacyCognateDecisions, ...withoutLegacyRoot } = currentData;
  const existingManualOverrides = isRecord(withoutLegacyRoot.manual_overrides) ? withoutLegacyRoot.manual_overrides : {};

  return {
    ...withoutLegacyRoot,
    manual_overrides: {
      ...existingManualOverrides,
      cognate_decisions: imported.manual_overrides.cognate_decisions,
      cognate_sets: imported.manual_overrides.cognate_sets,
      speaker_flags: imported.manual_overrides.speaker_flags,
      borrowing_flags: imported.manual_overrides.borrowing_flags,
    },
  };
}
