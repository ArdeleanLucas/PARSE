// Regression coverage for compare-bundle normalization (MC-466-A).
//
// The Compare page renders one selectable variant card per recorded
// realization (A/B/…) via SpeakerFormsTable's buildVariantList, which reads
// `bundle.candidates[speaker][rowId].realizations`. The backend has emitted
// that array since PR #616; the table has consumed it since PR #617. But
// normalizeCandidate — which every live bundle passes through on its way from
// getCompareBundles() into component state — rebuilt candidates field-by-field
// and dropped `realizations` (and `warnings`). The result: no A/B+ variants on
// Compare, so the canonical picker only ever showed one option.

import { describe, expect, it } from "vitest";
import { normalizeBundles } from "./compareBundles";

function bundleWithCandidate(candidate: Record<string, unknown>) {
  return normalizeBundles({
    bundles: [
      {
        bundle_id: "bundle:c-hair",
        uid: "c-hair",
        label: "hair",
        row_ids: ["10"],
        buckets: [
          {
            bucket_key: "klq 1.1",
            survey_id: "klq",
            source_item: "1.1",
            variants: [{ csv_row_id: "10", variant_label: "A", label: "hair (A)" }],
          },
        ],
        candidates: { Fail01: { "10": candidate } },
      },
    ],
  }).bundles[0];
}

describe("normalizeCandidate — realizations passthrough", () => {
  it("preserves the per-row realizations array through normalization", () => {
    const bundle = bundleWithCandidate({
      csv_row_id: "10",
      ipa: "mɵ",
      realization_index: 0,
      realizations: [
        { csv_row_id: "10", ipa: "mɵ", realization_index: 0, source_wav: "a.wav", start_sec: 1, end_sec: 2 },
        { csv_row_id: "10", ipa: "mu", realization_index: 1, source_wav: "a.wav", start_sec: 3, end_sec: 4 },
      ],
    });

    const candidate = bundle?.candidates?.Fail01?.["10"];
    expect(candidate?.realizations).toHaveLength(2);
    expect(candidate?.realizations?.[0]).toMatchObject({ ipa: "mɵ", realization_index: 0 });
    expect(candidate?.realizations?.[1]).toMatchObject({ ipa: "mu", realization_index: 1 });
  });

  it("leaves realizations undefined when the backend omits it (single-realization rows)", () => {
    const bundle = bundleWithCandidate({ csv_row_id: "10", ipa: "mɵ", realization_index: 0 });
    expect(bundle?.candidates?.Fail01?.["10"]?.realizations).toBeUndefined();
  });

  it("drops a malformed realizations array down to its valid entries", () => {
    const bundle = bundleWithCandidate({
      csv_row_id: "10",
      realizations: [null, 42, { csv_row_id: "10", ipa: "mu", realization_index: 1 }],
    });
    const realizations = bundle?.candidates?.Fail01?.["10"]?.realizations;
    expect(realizations).toHaveLength(1);
    expect(realizations?.[0]).toMatchObject({ ipa: "mu", realization_index: 1 });
  });

  it("preserves candidate warnings", () => {
    const bundle = bundleWithCandidate({ csv_row_id: "10", ipa: "mɵ", warnings: ["overlapping intervals", 7] });
    expect(bundle?.candidates?.Fail01?.["10"]?.warnings).toEqual(["overlapping intervals"]);
  });
});
