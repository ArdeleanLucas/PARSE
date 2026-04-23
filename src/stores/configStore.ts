import { create } from "zustand";
import type { ProjectConfig } from "../api/types";
import { getConfig } from "../api/client";

interface ConfigStore {
  config: ProjectConfig | null;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  update: (patch: Partial<ProjectConfig>) => Promise<void>;
}

export const useConfigStore = create<ConfigStore>()((set, get) => ({
  config: null,
  loading: false,
  error: null,

  load: async () => {
    const { config, loading } = get();
    if (config !== null && !loading) return;
    if (loading) return; // don't double-fetch
    set({ loading: true, error: null });
    try {
      const data = await getConfig();
      set({ config: data, loading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ loading: false, error: message });
    }
  },

  update: async (_patch: Partial<ProjectConfig>) => {
    // TODO: implement PATCH /api/config when backend supports it
    console.warn("[configStore] update() is not yet implemented");
  },
}));
