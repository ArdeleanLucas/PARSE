import { create } from "zustand";
import type { ProjectConfig, SurveyOverlapPatch, SurveyOverlapState } from "../api/types";
import { getConfig, getSurveyOverlap, updateConfig, updateSurveyOverlap as persistSurveyOverlap } from "../api/client";

interface ConfigStore {
  config: ProjectConfig | null;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  reload: () => Promise<void>;
  update: (patch: Partial<ProjectConfig>) => Promise<void>;
  updateSurveyOverlap: (patch: SurveyOverlapPatch) => Promise<void>;
  applySurveyOverlap: (state: SurveyOverlapState) => void;
}

function mergeSurveyOverlapProjection(config: ProjectConfig, state: SurveyOverlapState): ProjectConfig {
  const conceptLinks = state.concept_survey_links ?? {};
  return {
    ...config,
    concepts: config.concepts.map((concept) => ({
      ...concept,
      surveys: conceptLinks[concept.id] ? { ...(concept.surveys ?? {}), ...conceptLinks[concept.id] } : concept.surveys,
    })),
    survey_settings: state.surveys,
    survey_color_coding_enabled: state.color_coding_enabled,
    speaker_survey_choices: state.speaker_choices,
    concept_survey_links: state.concept_survey_links,
    speaker_concept_survey_links: state.speaker_concept_survey_links,
  };
}

async function fetchSurveyOverlapOrNull(): Promise<SurveyOverlapState | null> {
  try {
    return await getSurveyOverlap();
  } catch (err) {
    console.warn('[configStore] survey-overlap fetch failed; continuing without override sidecar', err);
    return null;
  }
}

function mergeConfigWithSurveyOverlap(config: ProjectConfig, state: SurveyOverlapState | null): ProjectConfig {
  return state ? mergeSurveyOverlapProjection(config, state) : config;
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
      const [data, overlap] = await Promise.all([getConfig(), fetchSurveyOverlapOrNull()]);
      set({ config: mergeConfigWithSurveyOverlap(data, overlap), loading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ loading: false, error: message });
    }
  },

  reload: async () => {
    // Force-refresh from /api/config, bypassing the load() short-circuit.
    // Used after server-mutating actions (e.g. concept duplicate) where the
    // canonical concepts.csv has changed and the FE needs the new state.
    if (get().loading) return;
    set({ loading: true, error: null });
    try {
      const [data, overlap] = await Promise.all([getConfig(), fetchSurveyOverlapOrNull()]);
      set({ config: mergeConfigWithSurveyOverlap(data, overlap), loading: false });
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

  applySurveyOverlap: (state: SurveyOverlapState) => {
    const current = get().config;
    if (!current) {
      set({ error: "Cannot update survey overlap before config has loaded" });
      return;
    }
    set({ config: mergeSurveyOverlapProjection(current, state), error: null });
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
      get().applySurveyOverlap(state);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message });
    }
  },
}));
