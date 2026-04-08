// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetCoverage = vi.fn().mockResolvedValue({
  languages: {
    ar: { name: "Arabic", total: 82, filled: 41, empty: 41, concepts: { water: ["ma:P"] } },
    fa: { name: "Persian", total: 82, filled: 82, empty: 0, concepts: {} },
  },
});

const mockStartFetch = vi.fn().mockResolvedValue({ job_id: "test-job" });
const mockPollCompute = vi.fn().mockResolvedValue({ status: "done", progress: 100 });

vi.mock("../../api/client", () => ({
  getContactLexemeCoverage: (...args: unknown[]) => mockGetCoverage(...args),
  startContactLexemeFetch: (...args: unknown[]) => mockStartFetch(...args),
  pollCompute: (...args: unknown[]) => mockPollCompute(...args),
}));

import { ContactLexemePanel } from "./ContactLexemePanel";

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCoverage.mockResolvedValue({
    languages: {
      ar: { name: "Arabic", total: 82, filled: 41, empty: 41, concepts: { water: ["ma:P"] } },
      fa: { name: "Persian", total: 82, filled: 82, empty: 0, concepts: {} },
    },
  });
  mockStartFetch.mockResolvedValue({ job_id: "test-job" });
  mockPollCompute.mockResolvedValue({ status: "done", progress: 100 });
});

describe("ContactLexemePanel", () => {
  it("renders heading", async () => {
    render(<ContactLexemePanel />);
    expect(screen.getByText("Contact Language Lexemes")).toBeDefined();
  });

  it("shows coverage bars with filled/total after data loads", async () => {
    render(<ContactLexemePanel />);
    await waitFor(() => {
      expect(screen.getAllByText("41/82 concepts").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("82/82 concepts").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("Fetch Missing button is visible and enabled", async () => {
    render(<ContactLexemePanel />);
    await waitFor(() => {
      const btns = screen.getAllByText("Fetch Missing");
      expect(btns.length).toBeGreaterThanOrEqual(1);
      expect((btns[0] as HTMLButtonElement).disabled).toBe(false);
    });
  });

  it("shows Fetching... and disables button while job runs", async () => {
    mockPollCompute.mockResolvedValue({ status: "running", progress: 50, message: "Working..." });
    render(<ContactLexemePanel />);

    await waitFor(() => expect(screen.getAllByText("Fetch Missing").length).toBeGreaterThanOrEqual(1));

    fireEvent.click(screen.getAllByText("Fetch Missing")[0]);

    await waitFor(() => {
      const btns = screen.getAllByText("Fetching...");
      expect(btns.length).toBeGreaterThanOrEqual(1);
      expect((btns[0] as HTMLButtonElement).disabled).toBe(true);
    });
  });
});
