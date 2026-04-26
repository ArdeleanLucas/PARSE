import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectConfig } from "../api/types";

const { mockedGetConfig, mockedUpdateConfig } = vi.hoisted(() => ({
  mockedGetConfig: vi.fn(),
  mockedUpdateConfig: vi.fn(),
}));

vi.mock("../api/client", () => ({
  getConfig: mockedGetConfig,
  updateConfig: mockedUpdateConfig,
}));

import { useConfigStore } from "./configStore";

const baseConfig: ProjectConfig = {
  project_name: "TestProject",
  language_code: "ckb",
  speakers: ["Fail01"],
  concepts: [],
  audio_dir: "audio",
  annotations_dir: "annotations",
};

describe("configStore.update", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useConfigStore.setState({
      config: structuredClone(baseConfig),
      loading: false,
      error: null,
    });
    mockedUpdateConfig.mockResolvedValue(undefined);
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
});
