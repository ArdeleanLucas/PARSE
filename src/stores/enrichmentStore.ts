// enrichmentStore — Track B (ParseBuilder impl).
import { create } from "zustand";
import { getEnrichments, saveEnrichments } from "../api/client";
import type { EnrichmentsPayload } from "../api/types";

interface EnrichmentStore {
  data: Record<string, unknown>;
  loading: boolean;
  load: () => Promise<void>;
  save: (patch: Record<string, unknown>) => Promise<void>;
}

export const useEnrichmentStore = create<EnrichmentStore>()((set, get) => ({
  data: {},
  loading: false,

  load: async () => {
    set({ loading: true });
    try {
      const payload = await getEnrichments();
      set({ data: payload as Record<string, unknown>, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  save: async (patch: Record<string, unknown>) => {
    const merged = { ...get().data, ...patch };
    set({ data: merged });
    await saveEnrichments(merged as EnrichmentsPayload);
  },
}));
