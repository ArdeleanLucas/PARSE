import { create } from "zustand";
import { getEnrichments, saveEnrichments } from "../api/client";
import type { EnrichmentsPayload } from "../api/types";

interface EnrichmentStore {
  data: Record<string, unknown>;
  loading: boolean;
  load: () => Promise<void>;
  save: (patch: Record<string, unknown>) => Promise<void>;
  replace: (nextData: Record<string, unknown>) => Promise<void>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function deepMerge(base: Record<string, unknown>, patch: Record<string, unknown>): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...base };

  for (const [key, value] of Object.entries(patch)) {
    const current = merged[key];
    if (isRecord(current) && isRecord(value)) {
      merged[key] = deepMerge(current, value);
    } else {
      merged[key] = value;
    }
  }

  return merged;
}

export const useEnrichmentStore = create<EnrichmentStore>()((set, get) => ({
  data: {},
  loading: false,

  load: async () => {
    set({ loading: true });
    try {
      const payload = await getEnrichments();
      set({ data: payload as Record<string, unknown> });
    } finally {
      set({ loading: false });
    }
  },

  save: async (patch: Record<string, unknown>) => {
    const current = get().data;
    const merged = deepMerge(current, patch);
    set({ data: merged });
    await saveEnrichments(merged as EnrichmentsPayload);
  },

  replace: async (nextData: Record<string, unknown>) => {
    set({ data: nextData });
    await saveEnrichments(nextData as EnrichmentsPayload);
  },
}));
