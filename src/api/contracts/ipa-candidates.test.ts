// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { IpaCandidate, IpaReviewState } from "../types";
import { getIpaCandidates, putIpaReview } from "../client";

describe("IPA candidate/review API contract", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GET /api/annotations/<speaker>/ipa-candidates returns candidates and review maps", async () => {
    const candidate: IpaCandidate = {
      candidate_id: "cand-1",
      model: "wav2vec2-xlsr-53-espeak-cv-ft",
      model_version: "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
      raw_ipa: "eˈɾem",
      decoded_at: "2026-05-02T14:19:00Z",
      timing_basis: "audition_cue",
      confidence: null,
    };
    const review: IpaReviewState = {
      status: "needs_review",
      suggested_ipa: "",
      resolution_type: "",
      evidence_sources: [],
      notes: "",
    };
    const payload = { candidates: { "12::ipa::0": [candidate] }, review: { "12::ipa::0": review } };
    fetchMock.mockResolvedValue({ ok: true, status: 200, headers: new Headers(), json: async () => payload });

    await expect(getIpaCandidates("Fail 01")).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/annotations/Fail%2001/ipa-candidates",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it("PUT /api/annotations/<speaker>/ipa-review/<key> sends the review state and unwraps review", async () => {
    const state: IpaReviewState = {
      status: "accepted",
      suggested_ipa: "eɾɛm",
      resolution_type: "human_review_edited",
      evidence_sources: ["user_edit"],
      notes: "checked",
    };
    fetchMock.mockResolvedValue({ ok: true, status: 200, headers: new Headers(), json: async () => ({ review: state }) });

    await expect(putIpaReview("Fail01", "12::ipa::0", state)).resolves.toEqual(state);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/annotations/Fail01/ipa-review/12%3A%3Aipa%3A%3A0",
      expect.objectContaining({ method: "PUT", body: JSON.stringify(state) }),
    );
  });
});
