// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { useWaveSurfer as BarrelUseWaveSurfer } from "../useWaveSurfer";
import { useBatchPipelineJob as BarrelUseBatchPipelineJob } from "../useBatchPipelineJob";

describe("hook cluster barrels", () => {
  it("re-exports split hook entry points through the existing top-level import surface", async () => {
    const [waveModule, batchModule] = await Promise.all([
      import("../wave-surfer/useWaveSurfer"),
      import("../batch-pipeline/useBatchPipelineJob"),
    ]);

    expect(waveModule.useWaveSurfer).toBe(BarrelUseWaveSurfer);
    expect(batchModule.useBatchPipelineJob).toBe(BarrelUseBatchPipelineJob);
  });

  it("exports extracted wave/batch helper modules", async () => {
    const [waveInstance, waveRegions, wavePlayback, wavePeaks, waveTypes, batchStart, batchPoll, batchResults, batchErrors, batchTypes] = await Promise.all([
      import("../wave-surfer/useWaveSurferInstance"),
      import("../wave-surfer/useWaveSurferRegions"),
      import("../wave-surfer/useWaveSurferPlayback"),
      import("../wave-surfer/useWaveSurferPeaks"),
      import("../wave-surfer/types"),
      import("../batch-pipeline/useBatchJobStart"),
      import("../batch-pipeline/useBatchJobPoll"),
      import("../batch-pipeline/useBatchJobResults"),
      import("../batch-pipeline/useBatchJobErrors"),
      import("../batch-pipeline/types"),
    ]);

    expect(waveInstance).toHaveProperty("useWaveSurferInstance");
    expect(waveRegions).toHaveProperty("useWaveSurferRegions");
    expect(wavePlayback).toHaveProperty("useWaveSurferPlayback");
    expect(wavePeaks).toHaveProperty("loadWaveSurferAudio");
    expect(waveTypes).toHaveProperty("WAVE_SURFER_REGION_COLOR");
    expect(batchStart).toHaveProperty("startBatchSpeakerJob");
    expect(batchPoll).toHaveProperty("pollBatchSpeakerJob");
    expect(batchResults).toHaveProperty("markPendingSpeakersCancelled");
    expect(batchErrors).toHaveProperty("normalizeProgress");
    expect(batchTypes).toHaveProperty("POLL_INTERVAL_MS");
  });
});
