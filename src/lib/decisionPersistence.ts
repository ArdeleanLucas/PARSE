import type { CanonicalLexemeSelection, CompareBundle } from "../api/types";
import { migrateCanonicalRealizationToSelection } from "./compareBundles";

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

export type CanonicalLexemesByBundle = Record<string, Record<string, CanonicalLexemeSelection>>;

export interface CanonicalDecisionManualOverrides {
  cognate_decisions: CognateDecisionMap;
  cognate_sets: CognateSetMap;
  speaker_flags: SpeakerFlagMap;
  borrowing_flags: BorrowingFlagMap;
  canonical_lexemes?: CanonicalLexemesByBundle;
}

export interface CanonicalDecisionImportOptions {
  compareBundles?: CompareBundle[];
  selectedAt?: string;
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

function sanitizeCanonicalSelection(raw: unknown): CanonicalLexemeSelection | null {
  if (!isRecord(raw)) return null;
  const csvRowId = typeof raw.csv_row_id === 'string' ? raw.csv_row_id.trim() : '';
  const surveyId = typeof raw.survey_id === 'string' ? raw.survey_id.trim().toLowerCase() : '';
  const sourceItem = typeof raw.source_item === 'string' ? raw.source_item.trim() : '';
  const source = typeof raw.source === 'string' ? raw.source : '';
  if (!csvRowId || !surveyId || !sourceItem) return null;
  if (source !== 'manual' && source !== 'migration:canonical_realizations' && source !== 'default:single-candidate') return null;
  return {
    csv_row_id: csvRowId,
    survey_id: surveyId,
    source_item: sourceItem,
    bucket_key: typeof raw.bucket_key === 'string' && raw.bucket_key.trim() ? raw.bucket_key.trim() : undefined,
    realization_index: typeof raw.realization_index === 'number' && Number.isInteger(raw.realization_index) ? raw.realization_index : undefined,
    source,
    selected_at: typeof raw.selected_at === 'string' ? raw.selected_at : '',
  };
}

function sanitizeCanonicalLexemes(raw: unknown, options: { includeDefaults?: boolean } = {}): CanonicalLexemesByBundle | undefined {
  if (!isRecord(raw)) return undefined;
  const sanitized: CanonicalLexemesByBundle = {};
  for (const [bundleId, speakers] of Object.entries(raw)) {
    if (!isRecord(speakers)) continue;
    const speakerSelections: Record<string, CanonicalLexemeSelection> = {};
    for (const [speaker, value] of Object.entries(speakers)) {
      const selection = sanitizeCanonicalSelection(value);
      if (!selection) continue;
      if (!options.includeDefaults && selection.source === 'default:single-candidate') continue;
      speakerSelections[speaker] = selection;
    }
    if (Object.keys(speakerSelections).length > 0) sanitized[bundleId] = speakerSelections;
  }
  return Object.keys(sanitized).length > 0 ? sanitized : undefined;
}

function migrateLegacyCanonicalRealizations(raw: unknown, options: CanonicalDecisionImportOptions = {}): CanonicalLexemesByBundle | undefined {
  if (!isRecord(raw) || !options.compareBundles?.length) return undefined;
  const bundlesByLabel = new Map<string, CompareBundle>();
  for (const bundle of options.compareBundles) {
    bundlesByLabel.set(bundle.bundle_id, bundle);
    bundlesByLabel.set(bundle.label, bundle);
    for (const rowId of bundle.row_ids) bundlesByLabel.set(rowId, bundle);
  }

  const migrated: CanonicalLexemesByBundle = {};
  for (const [legacyKey, speakers] of Object.entries(raw)) {
    if (!isRecord(speakers)) continue;
    const bundle = bundlesByLabel.get(legacyKey);
    if (!bundle) continue;
    for (const [speaker, legacyIdx] of Object.entries(speakers)) {
      if (typeof legacyIdx !== 'number') continue;
      const selection = migrateCanonicalRealizationToSelection(legacyIdx, bundle, speaker, options.selectedAt ?? '');
      if (!selection) continue;
      migrated[bundle.bundle_id] = migrated[bundle.bundle_id] ?? {};
      migrated[bundle.bundle_id][speaker] = selection;
    }
  }
  return Object.keys(migrated).length > 0 ? migrated : undefined;
}

function mergeCanonicalLexemesOnImport(
  existing: CanonicalLexemesByBundle | undefined,
  incoming: CanonicalLexemesByBundle | undefined,
): CanonicalLexemesByBundle | undefined {
  const merged: CanonicalLexemesByBundle = existing ? Object.fromEntries(
    Object.entries(existing).map(([bundleId, speakers]) => [bundleId, { ...speakers }]),
  ) : {};
  for (const [bundleId, speakers] of Object.entries(incoming ?? {})) {
    merged[bundleId] = merged[bundleId] ?? {};
    for (const [speaker, incomingSelection] of Object.entries(speakers)) {
      const current = merged[bundleId][speaker];
      if (current?.source === 'manual' && incomingSelection.source !== 'manual') continue;
      merged[bundleId][speaker] = incomingSelection;
    }
  }
  return Object.keys(merged).length > 0 ? merged : undefined;
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
    canonical_lexemes: sanitizeCanonicalLexemes(manualOverrides.canonical_lexemes),
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
    Object.keys(overrides.borrowing_flags).length > 0 ||
    Object.keys(overrides.canonical_lexemes ?? {}).length > 0
  );
}

function normalizeImportedDecisions(raw: unknown, options: CanonicalDecisionImportOptions = {}): CanonicalDecisionPayload | null {
  if (!isRecord(raw)) return null;
  if (raw.format !== PARSE_DECISIONS_FORMAT) return null;
  if (raw.version !== PARSE_DECISIONS_VERSION) return null;
  if (!isRecord(raw.manual_overrides)) return null;

  const manualSource = raw.manual_overrides;
  const importedCanonicalLexemes = sanitizeCanonicalLexemes(manualSource.canonical_lexemes);
  /** @deprecated scheduled for removal once decision files predating 2026-05 stop appearing. */
  const legacyCanonicalLexemes = importedCanonicalLexemes
    ? undefined
    // Legacy canonical_realizations read path: scheduled for removal once decision files predating 2026-05 stop appearing.
    : migrateLegacyCanonicalRealizations(manualSource.canonical_realizations, options);
  const overrides: CanonicalDecisionManualOverrides = {
    cognate_decisions: sanitizeCognateDecisionMap(manualSource.cognate_decisions),
    cognate_sets: sanitizeCognateSetMap(manualSource.cognate_sets),
    speaker_flags: sanitizeSpeakerFlagMap(manualSource.speaker_flags),
    borrowing_flags: sanitizeBorrowingFlagMap(manualSource.borrowing_flags),
    canonical_lexemes: importedCanonicalLexemes ?? legacyCanonicalLexemes,
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
  options: CanonicalDecisionImportOptions = {},
): Record<string, unknown> | null {
  const imported = normalizeImportedDecisions(raw, options);
  if (!imported) return null;

  const { cognate_decisions: _legacyCognateDecisions, ...withoutLegacyRoot } = currentData;
  const existingManualOverrides = isRecord(withoutLegacyRoot.manual_overrides) ? withoutLegacyRoot.manual_overrides : {};
  const existingCanonicalLexemes = sanitizeCanonicalLexemes(existingManualOverrides.canonical_lexemes, { includeDefaults: true });
  const canonicalLexemes = mergeCanonicalLexemesOnImport(
    existingCanonicalLexemes,
    imported.manual_overrides.canonical_lexemes,
  );

  return {
    ...withoutLegacyRoot,
    manual_overrides: {
      ...existingManualOverrides,
      cognate_decisions: imported.manual_overrides.cognate_decisions,
      cognate_sets: imported.manual_overrides.cognate_sets,
      speaker_flags: imported.manual_overrides.speaker_flags,
      borrowing_flags: imported.manual_overrides.borrowing_flags,
      ...(canonicalLexemes ? { canonical_lexemes: canonicalLexemes } : {}),
    },
  };
}
