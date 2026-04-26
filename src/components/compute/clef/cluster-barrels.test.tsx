// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { ClefConfigModal as BarrelConfigModal } from "../ClefConfigModal";
import { ClefPopulateSummaryBanner as BarrelSummaryBanner } from "../ClefPopulateSummaryBanner";
import { ClefSourcesReportModal as BarrelSourcesModal } from "../ClefSourcesReportModal";

describe("CLEF modal cluster barrels", () => {
  it("keeps the public compute import surface pointed at extracted CLEF modules", async () => {
    const [configModule, sourcesModule, bannerModule] = await Promise.all([
      import("./ClefConfigModal"),
      import("./ClefSourcesReportModal"),
      import("./ClefPopulateSummaryBanner"),
    ]);

    expect(configModule.ClefConfigModal).toBe(BarrelConfigModal);
    expect(sourcesModule.ClefSourcesReportModal).toBe(BarrelSourcesModal);
    expect(bannerModule.ClefPopulateSummaryBanner).toBe(BarrelSummaryBanner);
  });

  it("exports extracted CLEF hooks and shared types", async () => {
    const [{ useClefConfig }, { useClefFetchJob }, typesModule, sharedModule] = await Promise.all([
      import("./useClefConfig"),
      import("./useClefFetchJob"),
      import("./types"),
      import("./shared"),
    ]);

    expect(typeof useClefConfig).toBe("function");
    expect(typeof useClefFetchJob).toBe("function");
    expect(typesModule).toHaveProperty("MAX_PRIMARY");
    expect(sharedModule).toHaveProperty("providerLabel");
  });
});
