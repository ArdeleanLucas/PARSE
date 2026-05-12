import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectConfig, SurveyOverlapState } from "../api/types";

const { mockedGetConfig, mockedGetSurveyOverlap, mockedUpdateConfig, mockedUpdateSurveyOverlap } = vi.hoisted(() => ({
  mockedGetConfig: vi.fn(),
  mockedGetSurveyOverlap: vi.fn(),
  mockedUpdateConfig: vi.fn(),
  mockedUpdateSurveyOverlap: vi.fn(),
}));

vi.mock("../api/client", () => ({
  getConfig: mockedGetConfig,
  getSurveyOverlap: mockedGetSurveyOverlap,
  updateConfig: mockedUpdateConfig,
  updateSurveyOverlap: mockedUpdateSurveyOverlap,
}));

import { useConfigStore } from "./configStore";

const baseConfig: ProjectConfig = {
  project_name: "TestProject",
  language_code: "ckb",
  speakers: ["Fail01", "Saha01"],
  concepts: [{ id: "1", label: "hair", surveys: { klq: "1.1" } }],
  audio_dir: "audio",
  annotations_dir: "annotations",
};


const overlapState: SurveyOverlapState = {
  version: 1,
  color_coding_enabled: true,
  surveys: {
    klq: { display_label: "KLQ", display_color: "slate" },
    jbil: { display_label: "JBIL", display_color: "amber" },
  },
  concept_survey_links: {
    "1": { klq: "1.1", jbil: "32" },
  },
  speaker_choices: {},
  speaker_concept_survey_links: {
    Saha01: {
      "1": { jbil: "32" },
    },
  },
};

describe("configStore.load survey-overlap hydration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useConfigStore.setState({ config: null, loading: false, error: null });
    mockedGetConfig.mockResolvedValue(structuredClone(baseConfig));
    mockedGetSurveyOverlap.mockResolvedValue(structuredClone(overlapState));
  });

  it("hydrates speaker-scoped and global survey links from /api/survey-overlap during load", async () => {
    await useConfigStore.getState().load();

    const config = useConfigStore.getState().config;
    expect(mockedGetConfig).toHaveBeenCalledTimes(1);
    expect(mockedGetSurveyOverlap).toHaveBeenCalledTimes(1);
    expect(config?.speaker_concept_survey_links?.Saha01?.["1"]?.jbil).toBe("32");
    expect(config?.concept_survey_links).toEqual(overlapState.concept_survey_links);
    expect(config?.concepts[0]?.surveys).toEqual({ klq: "1.1", jbil: "32" });
  });

  it("continues loading /api/config when /api/survey-overlap rejects", async () => {
    mockedGetSurveyOverlap.mockRejectedValueOnce(new Error("sidecar unavailable"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    try {
      await useConfigStore.getState().load();
    } finally {
      warn.mockRestore();
    }

    expect(useConfigStore.getState().config?.project_name).toBe("TestProject");
    expect(useConfigStore.getState().config?.speaker_concept_survey_links).toBeUndefined();
    expect(useConfigStore.getState().error).toBeNull();
  });

  it("applies a survey-link POST response without fetching /api/config again", () => {
    useConfigStore.setState({ config: structuredClone(baseConfig), loading: false, error: null });

    useConfigStore.getState().applySurveyOverlap(structuredClone(overlapState));

    expect(mockedGetConfig).not.toHaveBeenCalled();
    expect(useConfigStore.getState().config?.speaker_concept_survey_links?.Saha01?.["1"]?.jbil).toBe("32");
  });
});

describe("configStore.update", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useConfigStore.setState({
      config: structuredClone(baseConfig),
      loading: false,
      error: null,
    });
    mockedUpdateConfig.mockResolvedValue(undefined);
    mockedUpdateSurveyOverlap.mockResolvedValue({
      version: 1,
      color_coding_enabled: false,
      surveys: {},
      concept_survey_links: {},
      speaker_choices: {},
    });
  });

  it("persists the patch through the typed client and merges it into local state", async () => {
    await useConfigStore.getState().update({ project_name: "Renamed Project" });

    expect(mockedUpdateConfig).toHaveBeenCalledWith({ project_name: "Renamed Project" });
    expect(useConfigStore.getState().config?.project_name).toBe("Renamed Project");
    expect(useConfigStore.getState().config?.language_code).toBe("ckb");
  });

  it("records an error and preserves the previous config when the typed client update fails", async () => {
    mockedUpdateConfig.mockRejectedValueOnce(new Error("config write failed"));

    await useConfigStore.getState().update({ project_name: "Broken Rename" });

    expect(useConfigStore.getState().error).toBe("config write failed");
    expect(useConfigStore.getState().config?.project_name).toBe("TestProject");
  });

  it("persists survey-overlap patches and merges the normalized sidecar projection into config", async () => {
    mockedUpdateSurveyOverlap.mockResolvedValueOnce({
      version: 1,
      color_coding_enabled: true,
      surveys: { klq: { display_label: "Kurdish List", display_color: "teal" } },
      concept_survey_links: { rain: { klq: "KLQ_1.10", jbil: "JBIL_100" } },
      speaker_choices: { Saha01: { rain: "jbil" } },
    });

    await useConfigStore.getState().updateSurveyOverlap({
      surveys: { klq: { display_label: "Kurdish List", display_color: "teal" } },
      speaker_choices: { Saha01: { rain: "jbil" } },
    });

    expect(mockedUpdateSurveyOverlap).toHaveBeenCalledWith({
      surveys: { klq: { display_label: "Kurdish List", display_color: "teal" } },
      speaker_choices: { Saha01: { rain: "jbil" } },
    });
    expect(useConfigStore.getState().config).toMatchObject({
      survey_color_coding_enabled: true,
      survey_settings: { klq: { display_label: "Kurdish List", display_color: "teal" } },
      speaker_survey_choices: { Saha01: { rain: "jbil" } },
    });
  });

  it("preserves the previous survey projection when the sidecar update fails", async () => {
    useConfigStore.setState({
      config: {
        ...structuredClone(baseConfig),
        survey_color_coding_enabled: false,
        survey_settings: { klq: { display_label: "KLQ", display_color: "slate" } },
        speaker_survey_choices: {},
      },
      loading: false,
      error: null,
    });
    mockedUpdateSurveyOverlap.mockRejectedValueOnce(new Error("sidecar write failed"));

    await useConfigStore.getState().updateSurveyOverlap({ speaker_choices: { Saha01: { rain: "jbil" } } });

    expect(useConfigStore.getState().error).toBe("sidecar write failed");
    expect(useConfigStore.getState().config).toMatchObject({
      survey_color_coding_enabled: false,
      survey_settings: { klq: { display_label: "KLQ", display_color: "slate" } },
      speaker_survey_choices: {},
    });
  });
});

describe("configStore.reload", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useConfigStore.setState({
      config: structuredClone(baseConfig),
      loading: false,
      error: null,
    });
  });

  it("force-refreshes from /api/config even when config is already loaded", async () => {
    const updated: ProjectConfig = {
      ...structuredClone(baseConfig),
      project_name: "After Reload",
      concepts: [{ id: "1", label: "leaf (A)" }, { id: "618", label: "leaf (B)" }],
    };
    mockedGetConfig.mockResolvedValueOnce(updated);

    await useConfigStore.getState().reload();

    expect(mockedGetConfig).toHaveBeenCalledTimes(1);
    expect(useConfigStore.getState().config?.project_name).toBe("After Reload");
    expect(useConfigStore.getState().config?.concepts).toHaveLength(2);
    expect(useConfigStore.getState().loading).toBe(false);
  });

  it("records the error message and clears the loading flag when getConfig fails", async () => {
    mockedGetConfig.mockRejectedValueOnce(new Error("config fetch failed"));

    await useConfigStore.getState().reload();

    expect(useConfigStore.getState().error).toBe("config fetch failed");
    expect(useConfigStore.getState().loading).toBe(false);
  });

  it("does not double-fetch when a load is already in flight", async () => {
    useConfigStore.setState({ loading: true });
    await useConfigStore.getState().reload();
    expect(mockedGetConfig).not.toHaveBeenCalled();
  });
});
