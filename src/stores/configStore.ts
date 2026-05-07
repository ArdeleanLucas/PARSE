import { create } from "zustand";
import type { ProjectConfig, SurveyOverlapPatch, SurveyOverlapState } from "../api/types";
import { getConfig, updateConfig, updateSurveyOverlap as persistSurveyOverlap } from "../api/client";

interface ConfigStore {
  config: ProjectConfig | null;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  update: (patch: Partial<ProjectConfig>) => Promise<void>;
  updateSurveyOverlap: (patch: SurveyOverlapPatch) => Promise<void>;
}

function mergeSurveyOverlapProjection(config: ProjectConfig, state: SurveyOverlapState): ProjectConfig {
  const conceptLinks = state.concept_survey_links ?? {};
  return {
    ...config,
    concepts: config.concepts.map((concept) => ({
      ...concept,
      surveys: conceptLinks[concept.id] ?? concept.surveys,
    })),
    survey_settings: state.surveys,
    survey_color_coding_enabled: state.color_coding_enabled,
    speaker_survey_choices: state.speaker_choices,
  };
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

  update: async (patch: Partial<ProjectConfig>) => {
    const current = get().config;
    if (!current) {
      set({ error: "Cannot update config before it has loaded" });
      return;
    }
    set({ error: null });
    try {
      await updateConfig(patch);
      set({ config: { ...current, ...patch } });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message });
    }
  },

  updateSurveyOverlap: async (patch: SurveyOverlapPatch) => {
    const current = get().config;
    if (!current) {
      set({ error: "Cannot update survey overlap before config has loaded" });
      return;
    }
    set({ error: null });
    try {
      const state = await persistSurveyOverlap(patch);
      set({ config: mergeSurveyOverlapProjection(current, state) });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message });
    }
  },
}));
