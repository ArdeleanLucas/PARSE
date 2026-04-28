// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ClefPopulateSummaryBanner,
  type PopulateSummary,
} from "../ClefPopulateSummaryBanner";

vi.mock("../../../api/client", () => ({
  getAuthStatus: vi.fn(async () => ({ authenticated: false, flow_active: false })),
  getClefConfig: vi.fn(async () => ({
    configured: true,
    primary_contact_languages: ["eng", "spa"],
    languages: [
      { code: "eng", name: "English" },
      { code: "spa", name: "Spanish" },
    ],
    config_path: "",
    concepts_csv_exists: true,
    meta: {},
  })),
  getClefCatalog: vi.fn(async () => ({
    languages: [
      { code: "eng", name: "English" },
      { code: "spa", name: "Spanish" },
    ],
  })),
  getClefProviders: vi.fn(async () => ({
    providers: [
      { id: "ids", name: "IDS" },
      { id: "wiktionary", name: "Wiktionary" },
    ],
  })),
  saveClefConfig: vi.fn(),
  saveApiKey: vi.fn(),
  startContactLexemeFetch: vi.fn(),
}));

import { ClefConfigModal } from "../ClefConfigModal";

const emptySummary: PopulateSummary = {
  state: "empty",
  totalFilled: 0,
  perLang: { eng: 0, spa: 0 },
  warning: "Providers returned 0 forms.",
};

const okSummary: PopulateSummary = {
  state: "ok",
  totalFilled: 42,
  perLang: { eng: 22, spa: 20 },
  warning: null,
};

describe("ClefPopulateSummaryBanner", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows retry button only on non-ok banner and fires onRetryWithProviders on click", () => {
    const onRetry = vi.fn();
    render(
      <ClefPopulateSummaryBanner
        summary={emptySummary}
        onDismiss={() => {}}
        onRetryWithProviders={onRetry}
      />,
    );
    const retry = screen.getByTestId("clef-populate-retry");
    expect(retry.textContent ?? "").toMatch(/retry with different providers/i);
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not render retry button on the success banner", () => {
    render(
      <ClefPopulateSummaryBanner
        summary={okSummary}
        onDismiss={() => {}}
        onRetryWithProviders={() => {}}
      />,
    );
    expect(screen.queryByTestId("clef-populate-retry")).toBeNull();
  });

  it("clicking retry opens ClefConfigModal on the populate tab", async () => {
    // Minimal parent that wires the banner -> modal exactly like ParseUI:
    // the retry handler flips the initialTab state and opens the modal.
    function Harness() {
      const [open, setOpen] = useState(false);
      const [tab, setTab] = useState<"languages" | "populate">("languages");
      return (
        <>
          <ClefPopulateSummaryBanner
            summary={emptySummary}
            onDismiss={() => {}}
            onRetryWithProviders={() => {
              setTab("populate");
              setOpen(true);
            }}
          />
          <ClefConfigModal
            open={open}
            initialTab={tab}
            onClose={() => {
              setOpen(false);
              setTab("languages");
            }}
          />
        </>
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByTestId("clef-populate-retry"));
    // Sources section nav becomes the visible active tab.
    const populateTab = await waitFor(() =>
      screen.getByRole("button", { name: /2\. sources/i }),
    );
    expect(populateTab.className).toMatch(/text-slate-900/);
    expect(populateTab.className).toMatch(/border-b-white/);
    // And the languages tab is not active.
    const langTab = screen.getByRole("button", { name: /1\. languages/i });
    expect(langTab.className).not.toMatch(/border-b-white/);
  });
});
