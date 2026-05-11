import { describe, expect, it } from "vitest";
import type { CanonicalLexemeSelection, CompareBundle } from "../api/types";
import {
  applyCanonicalDecisionImport,
  buildCanonicalDecisionPayload,
  getCanonicalManualOverrides,
} from "./decisionPersistence";

const selectedAt = "2026-05-11T00:00:00Z";

function selection(overrides: Partial<CanonicalLexemeSelection> = {}): CanonicalLexemeSelection {
  return {
    csv_row_id: "619",
    survey_id: "klq",
    source_item: "4.1",
    bucket_key: "klq\u00004.1",
    realization_index: 1,
    source: "manual",
    selected_at: selectedAt,
    ...overrides,
  };
}

function compareBundle(): CompareBundle {
  return {
    bundle_id: "bundle:big",
    label: "big",
    row_ids: ["53", "619"],
    buckets: [
      {
        bucket_key: "klq\u00004.1",
        survey_id: "klq",
        source_item: "4.1",
        variants: [
          { csv_row_id: "53", survey_id: "klq", source_item: "4.1", bucket_key: "klq\u00004.1" },
          { csv_row_id: "619", survey_id: "klq", source_item: "4.1", bucket_key: "klq\u00004.1" },
        ],
      },
    ],
    candidates: {
      Fail02: {
        "53": { csv_row_id: "53", speaker: "Fail02", form: "mez", realization_index: 0 },
        "619": { csv_row_id: "619", speaker: "Fail02", form: "gewre", realization_index: 1 },
      },
    },
  };
}

describe("canonical decision persistence", () => {
  it("round-trips persisted canonical_lexemes through export and import", () => {
    const current = {
      manual_overrides: {
        canonical_lexemes: {
          "bundle:big": {
            Fail02: selection(),
          },
        },
      },
    };

    const payload = buildCanonicalDecisionPayload(current);
    expect(payload.manual_overrides.canonical_lexemes).toEqual(current.manual_overrides.canonical_lexemes);

    const imported = applyCanonicalDecisionImport({}, payload);
    expect(imported?.manual_overrides).toMatchObject({
      canonical_lexemes: current.manual_overrides.canonical_lexemes,
    });
  });

  it("omits recomputable default canonical picks from exported decisions", () => {
    const payload = buildCanonicalDecisionPayload({
      manual_overrides: {
        canonical_lexemes: {
          "bundle:big": {
            Saha01: selection({
              csv_row_id: "53",
              realization_index: 0,
              source: "default:single-candidate",
              selected_at: "",
            }),
            Fail02: selection(),
          },
        },
      },
    });

    expect(payload.manual_overrides.canonical_lexemes).toEqual({
      "bundle:big": { Fail02: selection() },
    });
  });

  it("preserves workspace canonical selections when importing old decision files without canonical_lexemes", () => {
    const current = {
      manual_overrides: {
        canonical_lexemes: { "bundle:big": { Fail02: selection() } },
        speaker_flags: { big: { Fail02: true } },
      },
    };

    const imported = applyCanonicalDecisionImport(current, {
      format: "parse-decisions/v1",
      version: 1,
      manual_overrides: {
        cognate_decisions: { big: { decision: "accepted", ts: 7 } },
        cognate_sets: {},
        speaker_flags: {},
        borrowing_flags: {},
      },
    });

    expect(imported?.manual_overrides).toMatchObject({
      canonical_lexemes: current.manual_overrides.canonical_lexemes,
      cognate_decisions: { big: { decision: "accepted", ts: 7 } },
    });
  });

  it("protects manual workspace selections from imported non-manual selections", () => {
    const currentManual = selection({ csv_row_id: "619", source: "manual" });
    const incomingMigration = selection({ csv_row_id: "53", realization_index: 0, source: "migration:canonical_realizations" });

    const imported = applyCanonicalDecisionImport(
      { manual_overrides: { canonical_lexemes: { "bundle:big": { Fail02: currentManual } } } },
      {
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: {},
          cognate_sets: {},
          speaker_flags: {},
          borrowing_flags: {},
          canonical_lexemes: { "bundle:big": { Fail02: incomingMigration } },
        },
      },
    );

    expect(imported?.manual_overrides).toMatchObject({
      canonical_lexemes: { "bundle:big": { Fail02: currentManual } },
    });
  });

  it("lets imported manual selections replace manual workspace selections", () => {
    const workspaceManual = selection({ csv_row_id: "619", source: "manual" });
    const incomingManual = selection({ csv_row_id: "53", realization_index: 0, source: "manual" });

    const imported = applyCanonicalDecisionImport(
      { manual_overrides: { canonical_lexemes: { "bundle:big": { Fail02: workspaceManual } } } },
      {
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: {},
          cognate_sets: {},
          speaker_flags: {},
          borrowing_flags: {},
          canonical_lexemes: { "bundle:big": { Fail02: incomingManual } },
        },
      },
    );

    expect(imported?.manual_overrides).toMatchObject({
      canonical_lexemes: { "bundle:big": { Fail02: incomingManual } },
    });
  });

  it("migrates unambiguous legacy canonical_realizations to canonical_lexemes when bundles are supplied", () => {
    const imported = applyCanonicalDecisionImport(
      {},
      {
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: {},
          cognate_sets: {},
          speaker_flags: {},
          borrowing_flags: {},
          canonical_realizations: { big: { Fail02: 1 } },
        },
      },
      { compareBundles: [compareBundle()], selectedAt },
    );

    expect(imported?.manual_overrides).toMatchObject({
      canonical_lexemes: {
        "bundle:big": {
          Fail02: {
            csv_row_id: "619",
            source: "migration:canonical_realizations",
            selected_at: selectedAt,
          },
        },
      },
    });
  });

  it("exposes sanitized canonical_lexemes through getCanonicalManualOverrides", () => {
    expect(
      getCanonicalManualOverrides({
        manual_overrides: {
          canonical_lexemes: {
            "bundle:big": {
              Fail02: selection(),
              Saha01: { csv_row_id: "53", source: "manual" },
            },
          },
        },
      }).canonical_lexemes,
    ).toEqual({ "bundle:big": { Fail02: selection() } });
  });
});
