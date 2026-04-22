import { describe, it, expect } from "vitest";

// Mirror of the surveyKey helper in ParseUI.tsx. Kept here so the ordering
// contract is testable without mounting the whole component tree.
function surveyKey(raw: string): (string | number)[] {
  const tokens: (string | number)[] = [];
  for (const match of raw.matchAll(/([A-Za-z]+)|(\d+)/g)) {
    if (match[1]) tokens.push(match[1].toLowerCase());
    else if (match[2]) tokens.push(parseInt(match[2], 10));
  }
  return tokens;
}

function compare(a: string, b: string): number {
  const ka = surveyKey(a);
  const kb = surveyKey(b);
  for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
    const xa = ka[i];
    const xb = kb[i];
    if (xa === undefined) return -1;
    if (xb === undefined) return 1;
    if (typeof xa === "number" && typeof xb === "number") {
      if (xa !== xb) return xa - xb;
    } else {
      const sa = String(xa);
      const sb = String(xb);
      if (sa !== sb) return sa < sb ? -1 : 1;
    }
  }
  return 0;
}

describe("survey-item natural sort", () => {
  it("orders JBIL numerically: 1, 2, 10, 11, 100 (not 1, 10, 100, 11, 2)", () => {
    const items = ["JBIL_10.A", "JBIL_100.A", "JBIL_11.A", "JBIL_1.A", "JBIL_2.A"];
    const sorted = [...items].sort(compare);
    expect(sorted).toEqual([
      "JBIL_1.A", "JBIL_2.A", "JBIL_10.A", "JBIL_11.A", "JBIL_100.A",
    ]);
  });

  it("treats KLQ section.item as two integers (not a decimal)", () => {
    // The pre-fix regex captured 1.10 as a float (1.1), so KLQ_1.10.A would
    // land *before* KLQ_1.2.A. Guard that explicitly.
    const items = [
      "KLQ_1.10.A", "KLQ_1.2.A", "KLQ_1.2.B", "KLQ_2.1.A", "KLQ_1.1.A",
    ];
    const sorted = [...items].sort(compare);
    expect(sorted).toEqual([
      "KLQ_1.1.A", "KLQ_1.2.A", "KLQ_1.2.B", "KLQ_1.10.A", "KLQ_2.1.A",
    ]);
  });

  it("groups by source prefix before number (JBIL before KLQ alphabetically)", () => {
    const items = ["KLQ_1.1.A", "JBIL_1.A", "KLQ_2.1.A", "JBIL_10.A"];
    const sorted = [...items].sort(compare);
    expect(sorted).toEqual([
      "JBIL_1.A", "JBIL_10.A", "KLQ_1.1.A", "KLQ_2.1.A",
    ]);
  });

  it("A/B variants on the same (section,item) stay adjacent in variant order", () => {
    const items = ["KLQ_1.2.B", "KLQ_1.1.A", "KLQ_1.2.A"];
    const sorted = [...items].sort(compare);
    expect(sorted).toEqual(["KLQ_1.1.A", "KLQ_1.2.A", "KLQ_1.2.B"]);
  });

  it("unprefixed numeric survey ids sort numerically too", () => {
    // Fallback for workspaces that store bare numeric ids.
    const items = ["10", "100", "11", "1", "2"];
    const sorted = [...items].sort(compare);
    expect(sorted).toEqual(["1", "2", "10", "11", "100"]);
  });
});
