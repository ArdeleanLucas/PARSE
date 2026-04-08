// enrichmentStore.ts — Oda (Track B) implements the body.
// ParseBuilder defines the interface only.
import { create } from "zustand";

interface EnrichmentStore {
  data: Record<string, unknown>;
  loading: boolean;
  load: () => Promise<void>;
  save: (patch: Record<string, unknown>) => Promise<void>;
}

export const useEnrichmentStore = create<EnrichmentStore>()(() => ({
  data: {},
  loading: false,

  // TODO Track B (Oda): implement
  load: async () => {
    throw new Error("Not implemented — Track B");
  },
  save: async (_patch: Record<string, unknown>) => {
    throw new Error("Not implemented — Track B");
  },
}));
