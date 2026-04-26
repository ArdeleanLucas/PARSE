import type { AnnotationRecord } from "../api/types";

export const CANONICAL_TIER_ORDER: Record<string, number> = {
  ipa_phone: 1,
  ipa: 2,
  ortho: 3,
  ortho_words: 4,
  stt: 5,
  concept: 6,
  sentence: 7,
  speaker: 8,
};

export const TIER_LABEL: Record<string, string> = {
  ipa_phone: "Phones",
  ipa: "IPA",
  ortho: "ORTH",
  ortho_words: "ORTH words",
  stt: "STT",
  concept: "Concept",
  sentence: "Sentence",
  speaker: "Speaker",
};

export function nowIsoUtc(): string {
  return new Date().toISOString();
}

export function deepClone<T>(val: T): T {
  return JSON.parse(JSON.stringify(val));
}

export function tierLabel(tier: string): string {
  return TIER_LABEL[tier] ?? tier;
}

export function blankRecord(speaker: string): AnnotationRecord {
  return {
    speaker,
    tiers: {
      ipa_phone: { name: "ipa_phone", display_order: 1, intervals: [] },
      ipa: { name: "ipa", display_order: 2, intervals: [] },
      ortho: { name: "ortho", display_order: 3, intervals: [] },
      ortho_words: { name: "ortho_words", display_order: 4, intervals: [] },
      stt: { name: "stt", display_order: 5, intervals: [] },
      concept: { name: "concept", display_order: 6, intervals: [] },
      sentence: { name: "sentence", display_order: 7, intervals: [] },
      speaker: { name: "speaker", display_order: 8, intervals: [] },
    },
    created_at: nowIsoUtc(),
    modified_at: nowIsoUtc(),
    source_wav: "",
  };
}

export function ensureCanonicalTiers(record: AnnotationRecord): AnnotationRecord {
  const tiers = { ...record.tiers };
  let changed = false;
  for (const [name, order] of Object.entries(CANONICAL_TIER_ORDER)) {
    if (!tiers[name]) {
      tiers[name] = { name, display_order: order, intervals: [] };
      changed = true;
    }
  }
  return changed ? { ...record, tiers } : record;
}
