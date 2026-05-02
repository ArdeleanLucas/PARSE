// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnnotationRecord, IpaCandidate, IpaReviewState } from "../../api/types";

const mocks = vi.hoisted(() => ({
  records: {} as Record<string, AnnotationRecord>,
  setIpaReview: vi.fn(),
  putIpaReview: vi.fn(),
}));

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (state: unknown) => unknown) =>
    selector({
      records: mocks.records,
      setIpaReview: mocks.setIpaReview,
    }),
}));

vi.mock("../../api/client", () => ({
  putIpaReview: mocks.putIpaReview,
}));

import { IpaCandidatePanel } from "./IpaCandidatePanel";

const key = "12::ipa::0";
const nextKey = "13::ipa::0";

function candidate(overrides: Partial<IpaCandidate> = {}): IpaCandidate {
  return {
    candidate_id: "cand-1",
    model: "wav2vec2-xlsr-53-espeak-cv-ft",
    model_version: "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
    raw_ipa: "eˈɾem",
    decoded_at: "2026-05-02T14:19:00Z",
    timing_basis: "audition_cue",
    confidence: null,
    ...overrides,
  };
}

function record(candidates: IpaCandidate[] | undefined, review?: IpaReviewState): AnnotationRecord {
  return {
    speaker: "Fail01",
    tiers: {},
    ipa_candidates: candidates === undefined ? {} : { [key]: candidates },
    ipa_review: review ? { [key]: review } : {},
  };
}

function recordByKey(candidateMap: Record<string, IpaCandidate[]>, reviewMap: Record<string, IpaReviewState> = {}): AnnotationRecord {
  return {
    speaker: "Fail01",
    tiers: {},
    ipa_candidates: candidateMap,
    ipa_review: reviewMap,
  };
}

function renderPanel(intervalKey = key) {
  return render(<IpaCandidatePanel speaker="Fail01" intervalKey={intervalKey} />);
}

beforeEach(() => {
  mocks.records = {};
  mocks.setIpaReview.mockClear();
  mocks.putIpaReview.mockReset();
  mocks.putIpaReview.mockResolvedValue({ status: "accepted", suggested_ipa: "", resolution_type: "", evidence_sources: [], notes: "" });
});

afterEach(cleanup);

describe("IpaCandidatePanel", () => {
  it("renders empty state and disables actions when no candidates exist", () => {
    mocks.records = { Fail01: record([]) };

    renderPanel();

    expect(screen.getByText("No IPA candidate for this interval. Run IPA in the run modal to generate one.")).toBeTruthy();
    for (const name of ["Accept", "Edit & Accept", "Reject", "Needs human review"]) {
      expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it("renders one candidate row with model, raw IPA, timing basis, and decoded time", () => {
    mocks.records = { Fail01: record([candidate()]) };

    renderPanel();

    expect(screen.getByText("wav2vec2-xlsr-53-espeak-cv-ft")).toBeTruthy();
    expect(screen.getByText("raw: eˈɾem")).toBeTruthy();
    expect(screen.getByText("timing: audition_cue")).toBeTruthy();
    expect(screen.getByText("decoded: 2026-05-02T14:19:00Z")).toBeTruthy();
  });

  it("renders two candidates without an agreement badge", () => {
    mocks.records = { Fail01: record([candidate({ candidate_id: "old", raw_ipa: "old-ipa" }), candidate({ candidate_id: "new", raw_ipa: "new-ipa" })]) };

    renderPanel();

    expect(screen.getByText("raw: old-ipa")).toBeTruthy();
    expect(screen.getByText("raw: new-ipa")).toBeTruthy();
    expect(screen.queryByText(/agreement/i)).toBeNull();
  });

  it("Accept writes accepted review using the most recent candidate", async () => {
    mocks.records = { Fail01: record([candidate({ candidate_id: "old", raw_ipa: "old" }), candidate({ candidate_id: "latest", raw_ipa: "latest" })]) };

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(mocks.putIpaReview).toHaveBeenCalled());
    expect(mocks.putIpaReview).toHaveBeenCalledWith("Fail01", key, {
      status: "accepted",
      suggested_ipa: "latest",
      resolution_type: "human_review",
      evidence_sources: ["user"],
    });
  });

  it("Edit & Accept writes the typed IPA with edited resolution type", async () => {
    mocks.records = { Fail01: record([candidate()]) };

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Edit & Accept" }));
    fireEvent.change(screen.getByLabelText("Edited IPA"), { target: { value: "eɾɛm" } });
    fireEvent.click(screen.getByRole("button", { name: "Save edited IPA" }));

    await waitFor(() => expect(mocks.putIpaReview).toHaveBeenCalled());
    expect(mocks.putIpaReview).toHaveBeenCalledWith("Fail01", key, {
      status: "accepted",
      suggested_ipa: "eɾɛm",
      resolution_type: "human_review_edited",
      evidence_sources: ["user_edit"],
    });
  });

  it("switching intervalKey resets edit state", () => {
    mocks.records = {
      Fail01: recordByKey({
        [key]: [candidate({ candidate_id: "cand-a", raw_ipa: "ipa-a" })],
        [nextKey]: [candidate({ candidate_id: "cand-b", raw_ipa: "ipa-b" })],
      }),
    };

    const { rerender } = renderPanel(key);
    fireEvent.click(screen.getByRole("button", { name: "Edit & Accept" }));
    fireEvent.change(screen.getByLabelText("Edited IPA"), { target: { value: "stale-typed-ipa" } });

    rerender(<IpaCandidatePanel speaker="Fail01" intervalKey={nextKey} />);

    expect(screen.queryByLabelText("Edited IPA")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit & Accept" }));
    expect((screen.getByLabelText("Edited IPA") as HTMLInputElement).value).toBe("ipa-b");
  });

  it("Cancel discards edit and closes input", () => {
    mocks.records = { Fail01: record([candidate()]) };

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Edit & Accept" }));
    fireEvent.change(screen.getByLabelText("Edited IPA"), { target: { value: "junk" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Edited IPA")).toBeNull();
    expect(screen.queryByText("Could not save IPA review. Restored previous state.")).toBeNull();
    expect(mocks.putIpaReview).not.toHaveBeenCalled();
  });

  it("Reject writes a human_rejected review", async () => {
    mocks.records = { Fail01: record([candidate()]) };

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    await waitFor(() => expect(mocks.putIpaReview).toHaveBeenCalled());
    expect(mocks.putIpaReview).toHaveBeenCalledWith("Fail01", key, {
      status: "rejected",
      resolution_type: "human_rejected",
      evidence_sources: ["user"],
    });
  });

  it("Needs human review writes needs_review", async () => {
    mocks.records = { Fail01: record([candidate()]) };

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Needs human review" }));

    await waitFor(() => expect(mocks.putIpaReview).toHaveBeenCalled());
    expect(mocks.putIpaReview).toHaveBeenCalledWith("Fail01", key, { status: "needs_review" });
  });

  it("rolls back optimistic review and shows an error when PUT fails", async () => {
    const previous: IpaReviewState = { status: "needs_review", suggested_ipa: "", resolution_type: "", evidence_sources: [], notes: "" };
    mocks.records = { Fail01: record([candidate()], previous) };
    mocks.putIpaReview.mockRejectedValue(new Error("API PUT failed 500"));

    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    await screen.findByText("Could not save IPA review. Restored previous state.");
    expect(mocks.setIpaReview).toHaveBeenLastCalledWith("Fail01", key, previous);
  });
});
