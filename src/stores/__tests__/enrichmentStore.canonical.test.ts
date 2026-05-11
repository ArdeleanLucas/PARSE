// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CanonicalLexemeSelection } from "../../api/types";
import { useEnrichmentStore } from "../enrichmentStore";

vi.mock("../../api/client", () => ({
  getEnrichments: vi.fn().mockResolvedValue({}),
  saveEnrichments: vi.fn().mockResolvedValue(undefined),
}));

const selection: CanonicalLexemeSelection = {
  csv_row_id: "53",
  survey_id: "klq",
  source_item: "4.1",
  bucket_key: "klq\u00004.1",
  realization_index: 0,
  source: "manual",
  selected_at: "2026-05-11T00:00:00Z",
};

describe("useEnrichmentStore.patchCanonicalLexeme", () => {
  beforeEach(() => {
    useEnrichmentStore.setState(useEnrichmentStore.getInitialState(), true);
  });

  afterEach(() => {
    useEnrichmentStore.setState(useEnrichmentStore.getInitialState(), true);
  });

  it("optimistically patches canonical lexemes without persisting", () => {
    useEnrichmentStore.setState({
      data: {
        manual_overrides: {
          speaker_flags: { "bundle:big": { Saha01: true } },
          canonical_lexemes: { "bundle:big": { Fail02: { ...selection, csv_row_id: "619" } } },
        },
      },
    });

    useEnrichmentStore.getState().patchCanonicalLexeme("bundle:big", "Saha01", selection);

    expect(useEnrichmentStore.getState().data).toMatchObject({
      manual_overrides: {
        speaker_flags: { "bundle:big": { Saha01: true } },
        canonical_lexemes: {
          "bundle:big": {
            Fail02: expect.objectContaining({ csv_row_id: "619" }),
            Saha01: selection,
          },
        },
      },
    });
  });

  it("clears one speaker selection without removing sibling speakers", () => {
    useEnrichmentStore.setState({
      data: { manual_overrides: { canonical_lexemes: { "bundle:big": { Saha01: selection, Fail02: { ...selection, csv_row_id: "619" } } } } },
    });

    useEnrichmentStore.getState().patchCanonicalLexeme("bundle:big", "Saha01", null);

    expect(useEnrichmentStore.getState().data).toMatchObject({
      manual_overrides: {
        canonical_lexemes: { "bundle:big": { Fail02: expect.objectContaining({ csv_row_id: "619" }) } },
      },
    });
    expect(((useEnrichmentStore.getState().data.manual_overrides as Record<string, unknown>).canonical_lexemes as Record<string, Record<string, unknown>>)["bundle:big"].Saha01).toBeUndefined();
  });
});
