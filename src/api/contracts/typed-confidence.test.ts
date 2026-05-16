// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import type { AnnotationInterval, ConfidenceSource, LexemeRerunOrthoResponse } from "../types";

describe("typed confidence API contracts", () => {
  it("models the backward-compatible confidence triplet on ORTH rerun responses", () => {
    const payload = {
      ortho: "ریشەم",
      interval: { start: 1, end: 2 },
      source: "rerun",
      confidence: 0.42,
      confidence_source: "constant_fallback",
      confidence_n_tokens: 0,
    } satisfies LexemeRerunOrthoResponse;

    expect(payload.confidence_source).toBe("constant_fallback");
  });

  it("models confidence provenance fields on annotation intervals", () => {
    const source: ConfidenceSource = "avg_logprob";
    const interval = {
      start: 1,
      end: 2,
      text: "segment",
      confidence: 0.87,
      confidence_source: source,
      confidence_n_tokens: 4,
    } satisfies AnnotationInterval;

    expect(interval.confidence_n_tokens).toBe(4);
  });
});
