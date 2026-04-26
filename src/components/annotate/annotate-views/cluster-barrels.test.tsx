// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { AnnotateView as BarrelAnnotateView } from "../AnnotateView";
import { AnnotateMode as BarrelAnnotateMode } from "../AnnotateMode";
import { AnnotationPanel as BarrelAnnotationPanel } from "../AnnotationPanel";
import { LexemeSearchPanel as BarrelLexemeSearchPanel } from "../LexemeSearchPanel";

describe("annotate workstation cluster barrels", () => {
  it("re-exports annotate cluster modules through the existing top-level import surface", async () => {
    const [viewModule, modeModule, panelModule, searchModule] = await Promise.all([
      import("./AnnotateView"),
      import("./AnnotateMode"),
      import("./AnnotationPanel"),
      import("./LexemeSearchPanel"),
    ]);

    expect(viewModule.AnnotateView).toBe(BarrelAnnotateView);
    expect(modeModule.AnnotateMode).toBe(BarrelAnnotateMode);
    expect(panelModule.AnnotationPanel).toBe(BarrelAnnotationPanel);
    expect(searchModule.LexemeSearchPanel).toBe(BarrelLexemeSearchPanel);
  });

  it("exports extracted annotate hooks/helpers", async () => {
    const [{ useAnnotateSelection }, { useAnnotateLifecycle }, { useLexemeSearchJob }, sharedModule, typesModule] = await Promise.all([
      import("./useAnnotateSelection"),
      import("./useAnnotateLifecycle"),
      import("./useLexemeSearchJob"),
      import("./shared"),
      import("./types"),
    ]);

    expect(typeof useAnnotateSelection).toBe("function");
    expect(typeof useAnnotateLifecycle).toBe("function");
    expect(typeof useLexemeSearchJob).toBe("function");
    expect(sharedModule).toHaveProperty("findAnnotationForConcept");
    expect(typesModule).toHaveProperty("PANEL_TABS");
  });
});
