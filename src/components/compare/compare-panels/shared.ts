import type {
  BorrowingDecision,
  CognateGroup,
  ConceptEntry,
  GroupLetter,
  SpeakerDecision,
} from "./types";

export const EPS = 0.01;

export const GROUP_COLORS: Record<string, string> = {
  A: "#dcfce7",
  B: "#dbeafe",
  C: "#fef9c3",
  D: "#fce7f3",
  E: "#f3e8ff",
};

export const BAND_COLORS: Record<string, { bg: string; label: string }> = {
  unlikely: { bg: "#dcfce7", label: "unlikely" },
  possible: { bg: "#fef3c7", label: "possible" },
  likely: { bg: "#fee2e2", label: "likely" },
};

export const DECISION_OPTIONS: BorrowingDecision[] = ["native", "borrowed", "uncertain", "skip"];

export function normalizeConcept(raw: string): string {
  let s = raw.trim();
  if (s.startsWith("#")) s = s.slice(1);
  const colonIdx = s.indexOf(":");
  if (colonIdx >= 0) s = s.slice(0, colonIdx);
  return s.trim();
}

export function parseConcepts(concepts: unknown): { id: string; label: string }[] {
  if (!Array.isArray(concepts)) return [];
  return concepts.map((c) => {
    if (typeof c === "string") {
      const id = normalizeConcept(c);
      return { id, label: id };
    }
    if (c && typeof c === "object" && ("id" in c || "label" in c)) {
      const obj = c as { id?: string; label?: string };
      const id = normalizeConcept(obj.id ?? obj.label ?? "");
      const label = obj.label ?? obj.id ?? id;
      return { id, label };
    }
    return { id: String(c), label: String(c) };
  });
}

export function lookupEntry(
  records: Record<string, unknown>,
  speaker: string,
  conceptId: string,
): ConceptEntry {
  const empty: ConceptEntry = {
    conceptId,
    ipa: "",
    ortho: "",
    sourceWav: null,
    startSec: null,
    endSec: null,
  };
  const rec = records[speaker] as {
    tiers?: Record<string, { intervals?: { start: number; end: number; text: string }[] }>;
    source_wav?: string;
  } | undefined;
  if (!rec?.tiers?.concept?.intervals) return empty;
  const conceptInterval = rec.tiers.concept.intervals.find((iv) => normalizeConcept(iv.text) === conceptId);
  if (!conceptInterval) return empty;
  const { start, end } = conceptInterval;
  const findMatch = (tier: string): string => {
    const intervals = rec.tiers?.[tier]?.intervals;
    if (!intervals) return "";
    const match = intervals.find((iv) => Math.abs(iv.start - start) < EPS && Math.abs(iv.end - end) < EPS);
    return match?.text ?? "";
  };
  return {
    conceptId,
    ipa: findMatch("ipa"),
    ortho: findMatch("ortho"),
    sourceWav: rec.source_wav || null,
    startSec: start,
    endSec: end,
  };
}

export function lookupForm(records: Record<string, unknown>, speaker: string, conceptId: string) {
  const entry = lookupEntry(records, speaker, conceptId);
  if (!entry.ipa && !entry.ortho) return null;
  return { ipa: entry.ipa, ortho: entry.ortho };
}

export function getCognateGroup(
  enrichmentData: Record<string, unknown>,
  conceptId: string,
  speaker: string,
): CognateGroup | null {
  const overrides = enrichmentData?.manual_overrides as { cognate_sets?: Record<string, Record<string, string[]>> } | undefined;
  const base = enrichmentData?.cognate_sets as Record<string, Record<string, string[]>> | undefined;
  const sets = overrides?.cognate_sets?.[conceptId] ?? base?.[conceptId];
  if (!sets) return null;
  for (const [group, speakers] of Object.entries(sets)) {
    if (Array.isArray(speakers) && speakers.includes(speaker)) {
      return { group, color: GROUP_COLORS[group] ?? "#e5e7eb" };
    }
  }
  return null;
}

export function expandKey(speaker: string, conceptId: string): string {
  return `${speaker}::${conceptId}`;
}

export function speakerHasForm(records: Record<string, unknown>, speaker: string, conceptId: string): boolean {
  return Boolean(lookupEntry(records, speaker, conceptId).ipa.trim());
}

export function sanitizeGroups(groups: Record<string, string[]>, speakersWithForm: string[]): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  const assigned = new Set<string>();
  for (const letter of ["A", "B", "C", "D", "E"] as GroupLetter[]) {
    if (!groups[letter]) continue;
    const filtered = groups[letter].filter((sp) => speakersWithForm.includes(sp) && !assigned.has(sp));
    if (filtered.length > 0) {
      result[letter] = filtered;
      filtered.forEach((sp) => assigned.add(sp));
    }
  }
  const unassigned = speakersWithForm.filter((sp) => !assigned.has(sp));
  if (unassigned.length > 0) {
    result.A = [...(result.A ?? []), ...unassigned];
  }
  return result;
}

export function normalizeDecision(raw: unknown): BorrowingDecision {
  if (typeof raw === "string") {
    const v = raw.toLowerCase().trim();
    if (v === "yes" || v === "loan" || v === "loanword" || v === "borrowed") return "borrowed";
    if (v === "no" || v === "native" || v === "not_borrowing") return "native";
    if (v === "uncertain" || v === "unclear" || v === "possible") return "uncertain";
  }
  return "skip";
}

export function deriveAudioUrl(record: { source_audio?: string; source_wav?: string } | null | undefined): string {
  const raw = (record?.source_audio ?? record?.source_wav ?? "").trim();
  if (!raw) return "";
  const cleaned = raw.replace(/\\/g, "/").replace(/^\/+/, "");
  return "/" + cleaned;
}

export function formatSeconds(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const minutes = Math.floor(value / 60);
  const seconds = value - minutes * 60;
  return `${minutes}:${seconds.toFixed(3).padStart(6, "0")}`;
}

export function scoreBand(score: number): string {
  if (score < 0.3) return "unlikely";
  if (score < 0.6) return "possible";
  return "likely";
}

export function resolveSpeakerDecision(
  localDecisions: Record<string, SpeakerDecision>,
  activeConcept: string | null,
  enrichmentData: Record<string, unknown>,
  speaker: string,
): SpeakerDecision {
  if (localDecisions[speaker]) return localDecisions[speaker];
  if (!activeConcept) return { decision: "skip", sourceLang: null };
  const manualOverrides = enrichmentData?.manual_overrides as { borrowing_flags?: Record<string, Record<string, unknown>> } | undefined;
  const baseFlags = enrichmentData?.borrowing_flags as Record<string, Record<string, unknown>> | undefined;
  const manualEntry = manualOverrides?.borrowing_flags?.[activeConcept]?.[speaker];
  if (manualEntry) {
    if (typeof manualEntry === "object" && manualEntry !== null) {
      const e = manualEntry as { decision?: unknown; sourceLang?: string | null };
      return { decision: normalizeDecision(e.decision), sourceLang: e.sourceLang ?? null };
    }
    return { decision: normalizeDecision(manualEntry), sourceLang: null };
  }
  const baseEntry = baseFlags?.[activeConcept]?.[speaker];
  if (baseEntry) {
    if (typeof baseEntry === "object" && baseEntry !== null) {
      const e = baseEntry as { decision?: unknown; sourceLang?: string | null };
      return { decision: normalizeDecision(e.decision), sourceLang: e.sourceLang ?? null };
    }
    return { decision: normalizeDecision(baseEntry), sourceLang: null };
  }
  return { decision: "skip", sourceLang: null };
}
