import { describe, expect, it } from "vitest";
import type { CompareBundle } from "../../api/types";
import {
  activeCandidateFor,
  canonicalFor,
  enumerateVariants,
  findBundleForConcept,
  migrateCanonicalRealizationToSelection,
  normalizeBundles,
  resolveActiveBucketForSpeaker,
} from "../compareBundles";

const selectedAt = "2026-05-11T00:00:00Z";

function bigBundle(overrides: Partial<CompareBundle> = {}): CompareBundle {
  return {
    bundle_id: "bundle:big",
    label: "big",
    row_ids: ["53", "619", "150"],
    buckets: [
      {
        bucket_key: "klq\u00004.1",
        survey_id: "klq",
        source_item: "4.1",
        variants: [
          { csv_row_id: "53", variant_label: "A", label: "big (A)" },
          { csv_row_id: "619", variant_label: "B", label: "big (B)" },
        ],
      },
      {
        bucket_key: "jbil\u0000169",
        survey_id: "jbil",
        source_item: "169",
        variants: [
          { csv_row_id: "150", variant_label: "A", label: "big (A)" },
        ],
      },
    ],
    candidates: {
      Saha01: {
        "53": { csv_row_id: "53", speaker: "Saha01", ipa: "gawra", start_sec: 1.1, end_sec: 1.8, source_wav: "audio/saha.wav", realization_index: 0 },
        "619": null,
        "150": null,
      },
      Fail02: {
        "53": { csv_row_id: "53", speaker: "Fail02", start_sec: 2.1, end_sec: 2.7, source_wav: "audio/fail.wav", realization_index: 0 },
        "619": { csv_row_id: "619", speaker: "Fail02", start_sec: 2.8, end_sec: 3.4, source_wav: "audio/fail.wav", realization_index: 1 },
        "150": null,
      },
    },
    ...overrides,
  };
}

describe("normalizeBundles", () => {
  it("defensively normalizes single-row bundles and drops malformed entries", () => {
    const payload = normalizeBundles({
      bundles: [
        {
          bundle_id: "bundle:hair",
          label: "hair",
          buckets: [{ survey_id: "KLQ", source_item: "2.1", variants: [{ csv_row_id: "42", label: "hair" }] }],
          candidates: { Fail01: { "42": { start_sec: 0.1, end_sec: 0.6, source_wav: "audio/fail01.wav" } } },
        },
        { label: "bad", buckets: [] },
      ],
      warnings: ["beta", 7],
    });

    expect(payload.bundles).toHaveLength(1);
    expect(payload.bundles[0]).toMatchObject({
      bundle_id: "bundle:hair",
      row_ids: ["42"],
      buckets: [{ survey_id: "klq", source_item: "2.1" }],
      candidates: { Fail01: { "42": { csv_row_id: "42", start_sec: 0.1, end_sec: 0.6, source_wav: "audio/fail01.wav" } } },
    });
    expect(payload.warnings).toEqual(["beta"]);
  });

  it("normalizes the big A/B plus JBIL reference case", () => {
    const payload = normalizeBundles({ bundles: [bigBundle()] });

    expect(payload.bundles[0].row_ids).toEqual(["53", "619", "150"]);
    expect(enumerateVariants(payload.bundles[0]).map(({ variant }) => variant.csv_row_id)).toEqual(["53", "619", "150"]);
  });

  it("accepts MC-368-B emitted variant and candidate shapes without filtering variants", () => {
    const payload = normalizeBundles({ bundles: [bigBundle()] });
    const [bundle] = payload.bundles;

    expect(bundle.buckets).toHaveLength(2);
    expect(bundle.buckets[0].variants).toHaveLength(2);
    expect(bundle.buckets[1].variants).toHaveLength(1);
    expect(enumerateVariants(bundle).map(({ variant }) => variant.csv_row_id)).toEqual(["53", "619", "150"]);
    expect(bundle.candidates?.Saha01?.["53"]).toMatchObject({
      start_sec: 1.1,
      end_sec: 1.8,
      source_wav: "audio/saha.wav",
    });
  });
});

describe("findBundleForConcept", () => {
  it("matches singleton concepts by row id before considering labels", () => {
    const decoy = bigBundle({ bundle_id: "bundle:label-decoy", label: "not big", row_ids: ["999"] });

    expect(findBundleForConcept([decoy, bigBundle()], { key: "53", name: "not big" })?.bundle_id).toBe("bundle:big");
  });

  it("falls back from grouped source-item keys to normalized bundle labels", () => {
    expect(findBundleForConcept([bigBundle()], { key: "4.1", name: "big" })?.bundle_id).toBe("bundle:big");
  });

  it("uses case-insensitive trimmed label matching without a row match", () => {
    expect(findBundleForConcept([bigBundle({ label: "  BIG  " })], { key: "missing", name: " big " })?.bundle_id).toBe("bundle:big");
  });

  it("returns null when neither row ids nor labels match", () => {
    expect(findBundleForConcept([bigBundle()], { key: "999", name: "small" })).toBeNull();
  });
});

describe("canonical selectors", () => {
  it("uses manual canonical selections before defaults", () => {
    const bundle = bigBundle({
      canonical: {
        Fail02: { csv_row_id: "619", survey_id: "klq", source_item: "4.1", bucket_key: "klq\u00004.1", source: "manual", selected_at: selectedAt },
      },
    });

    expect(canonicalFor(bundle, "Fail02")?.csv_row_id).toBe("619");
    expect(activeCandidateFor(bundle, "Fail02")?.csv_row_id).toBe("619");
  });

  it("synthesizes a non-persisted default when exactly one candidate is available", () => {
    const selection = canonicalFor(bigBundle(), "Saha01");

    expect(selection).toMatchObject({
      csv_row_id: "53",
      source: "default:single-candidate",
      survey_id: "klq",
      source_item: "4.1",
    });
    expect(activeCandidateFor(bigBundle(), "Saha01")?.csv_row_id).toBe("53");
  });

  it("returns no canonical for multiple candidates or zero candidates", () => {
    expect(canonicalFor(bigBundle(), "Fail02")).toBeNull();
    expect(canonicalFor(bigBundle(), "Nope01")).toBeNull();
  });

  it("treats null candidate entries as unavailable and not default-selectable", () => {
    const bundle = bigBundle({ candidates: { Saha01: { "53": null, "619": null, "150": null } } });

    expect(enumerateVariants(bundle).map(({ variant }) => variant.csv_row_id)).toContain("150");
    expect(canonicalFor(bundle, "Saha01")).toBeNull();
  });
});

describe("resolveActiveBucketForSpeaker", () => {
  it("applies speaker row links before speaker choices, global links, then legacy csv order", () => {
    const bundle = bigBundle({
      speaker_concept_survey_links: { Saha01: { "53": { jbil: "169" } } },
      speaker_choices: { Saha01: { "bundle:big": "klq" }, Fail02: { "bundle:big": "jbil" } },
      concept_survey_links: { "53": { klq: "4.1" } },
    });

    expect(resolveActiveBucketForSpeaker(bundle, "Saha01")?.bucket_key).toBe("jbil\u0000169");
    expect(resolveActiveBucketForSpeaker(bundle, "Fail02")?.bucket_key).toBe("jbil\u0000169");
    expect(resolveActiveBucketForSpeaker(bundle, "Other01")?.bucket_key).toBe("klq\u00004.1");
  });
});

describe("migrateCanonicalRealizationToSelection", () => {
  it("maps unambiguous legacy idx to a migration selection", () => {
    const selection = migrateCanonicalRealizationToSelection(0, bigBundle(), "Saha01", selectedAt);

    expect(selection).toEqual({
      csv_row_id: "53",
      survey_id: "klq",
      source_item: "4.1",
      bucket_key: "klq\u00004.1",
      realization_index: 0,
      source: "migration:canonical_realizations",
      selected_at: selectedAt,
    });
  });

  it("returns null for invalid or ambiguous legacy idx mappings", () => {
    expect(migrateCanonicalRealizationToSelection(-1, bigBundle(), "Saha01")).toBeNull();
    expect(migrateCanonicalRealizationToSelection(99, bigBundle(), "Saha01")).toBeNull();
    expect(migrateCanonicalRealizationToSelection(1, bigBundle(), "Saha01")).toBeNull();
  });
});
