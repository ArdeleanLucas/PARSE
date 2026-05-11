// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { BorrowingPanel as BarrelBorrowingPanel } from "../BorrowingPanel";
import { ConceptTable as BarrelConceptTable } from "../ConceptTable";
import { LexemeDetail as BarrelLexemeDetail } from "../LexemeDetail";
import { CognateControls as BarrelCognateControls } from "../CognateControls";

describe("compare workstation cluster barrels", () => {
  it("re-exports compare panels through the existing top-level import surface", async () => {
    const [borrowingModule, conceptModule, detailModule, controlsModule] = await Promise.all([
      import("./BorrowingPanel"),
      import("./ConceptTable"),
      import("./LexemeDetail"),
      import("./CognateControls"),
    ]);

    expect(borrowingModule.BorrowingPanel).toBe(BarrelBorrowingPanel);
    expect(conceptModule.ConceptTable).toBe(BarrelConceptTable);
    expect(detailModule.LexemeDetail).toBe(BarrelLexemeDetail);
    expect(controlsModule.CognateControls).toBe(BarrelCognateControls);
  });

  it("exports extracted compare hooks/helpers", async () => {
    const [{ useCompareSelection }, { useCognateDecisions }, { useEnrichmentsBinding }, sharedModule, typesModule] = await Promise.all([
      import("./useCompareSelection"),
      import("./useCognateDecisions"),
      import("./useEnrichmentsBinding"),
      import("./shared"),
      import("./types"),
    ]);

    expect(typeof useCompareSelection).toBe("function");
    expect(typeof useCognateDecisions).toBe("function");
    expect(typeof useEnrichmentsBinding).toBe("function");
    expect(sharedModule).toHaveProperty("normalizeConcept");
    expect(typesModule).toHaveProperty("GROUP_LETTERS");
  });

  it("looks up legacy compare rows by concept_id rather than display text", async () => {
    const { lookupEntry } = await import("./shared");
    const records = {
      Fail02: {
        tiers: {
          concept: {
            intervals: [
              { start: 0, end: 1, text: "dog", concept_id: "298" },
              { start: 1, end: 2, text: "298", concept_id: "322" },
            ],
          },
          ipa: { intervals: [{ start: 1, end: 2, text: "wrong-row" }] },
          ortho: { intervals: [{ start: 0, end: 1, text: "right-row" }] },
        },
      },
    };

    expect(lookupEntry(records, "Fail02", "298")).toMatchObject({
      startSec: 0,
      endSec: 1,
      ortho: "right-row",
    });
  });
});
