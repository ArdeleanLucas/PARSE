import { useCallback } from "react";
import { getLingPyExport, getNEXUSExport } from "../api/client";
import { useEnrichmentStore } from "../stores/enrichmentStore";

const WORDLIST_HEADERS = ["ID", "CONCEPT", "DOCULECT", "IPA", "COGID", "TOKENS", "BORROWING"] as const;

type BorrowingDecision = "native" | "borrowed" | "uncertain" | "skip";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function normalizeDataRoot(data: Record<string, unknown>): Record<string, unknown> {
  if (isRecord(data.enrichments)) {
    return data.enrichments;
  }
  return data;
}

function normalizeBorrowing(raw: unknown): number {
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return raw === 0 ? 0 : 1;
  }
  if (typeof raw === "boolean") {
    return raw ? 1 : 0;
  }
  if (typeof raw === "string") {
    const value = raw.trim().toLowerCase();
    if (!value || value === "native" || value === "no" || value === "0") {
      return 0;
    }
    return 1;
  }
  if (isRecord(raw)) {
    return normalizeBorrowing((raw as { decision?: BorrowingDecision }).decision);
  }
  return 0;
}

function speakerCognateId(
  conceptId: string,
  speaker: string,
  root: Record<string, unknown>
): number {
  const sets = isRecord(root.cognate_sets) ? (root.cognate_sets as Record<string, unknown>)[conceptId] : null;
  if (!isRecord(sets)) {
    return 0;
  }

  const letters = Object.keys(sets).sort();
  for (let index = 0; index < letters.length; index += 1) {
    const letter = letters[index];
    const members = sets[letter];
    if (Array.isArray(members) && members.includes(speaker)) {
      return index + 1;
    }
  }

  return 0;
}

function tokenizeIPA(ipa: string): string {
  return Array.from(ipa.trim()).filter((char) => !/\s/.test(char)).join(" ");
}

function speakerBorrowing(
  conceptId: string,
  speaker: string,
  root: Record<string, unknown>
): number {
  const manualOverrides = isRecord(root.manual_overrides) ? root.manual_overrides : null;
  const manualFlags = manualOverrides && isRecord(manualOverrides.borrowing_flags)
    ? manualOverrides.borrowing_flags
    : null;
  const baseFlags = isRecord(root.borrowing_flags) ? root.borrowing_flags : null;

  const manualValue = manualFlags && isRecord((manualFlags as Record<string, unknown>)[conceptId])
    ? ((manualFlags as Record<string, Record<string, unknown>>)[conceptId][speaker])
    : undefined;
  if (manualValue !== undefined) {
    return normalizeBorrowing(manualValue);
  }

  const baseValue = baseFlags && isRecord((baseFlags as Record<string, unknown>)[conceptId])
    ? ((baseFlags as Record<string, Record<string, unknown>>)[conceptId][speaker])
    : undefined;

  return normalizeBorrowing(baseValue);
}

export function useExport() {
  const data = useEnrichmentStore((state) => state.data);

  const exportLingPyTSV = useCallback(async (): Promise<void> => {
    const blob = await getLingPyExport();
    triggerDownload(blob, "parse-wordlist.tsv");
  }, []);

  const exportNEXUS = useCallback(async (): Promise<void> => {
    const blob = await getNEXUSExport();
    triggerDownload(blob, "parse-wordlist.nex");
  }, []);

  const exportCSV = useCallback((): void => {
    const root = normalizeDataRoot(data);
    const rows: string[] = [WORDLIST_HEADERS.join("	")];
    let rowId = 1;

    for (const [conceptId, entry] of Object.entries(root)) {
      if (!isRecord(entry)) {
        continue;
      }

      const ipaBySpeaker = isRecord(entry.ipa_computed)
        ? (entry.ipa_computed as Record<string, unknown>)
        : null;
      if (!ipaBySpeaker) {
        continue;
      }

      for (const [speaker, ipaRaw] of Object.entries(ipaBySpeaker)) {
        if (typeof ipaRaw !== "string" || !ipaRaw.trim()) {
          continue;
        }

        const ipa = ipaRaw.trim();
        const tokens = tokenizeIPA(ipa);
        const cogid = speakerCognateId(conceptId, speaker, root);
        const borrowing = speakerBorrowing(conceptId, speaker, root);

        rows.push([
          String(rowId),
          conceptId,
          speaker,
          ipa,
          String(cogid),
          tokens,
          String(borrowing),
        ].join("	"));

        rowId += 1;
      }
    }

    const blob = new Blob([rows.join("\n")], {
      type: "text/tab-separated-values;charset=utf-8",
    });
    triggerDownload(blob, "parse-wordlist-local.tsv");
  }, [data]);

  return { exportLingPyTSV, exportNEXUS, exportCSV };
}
