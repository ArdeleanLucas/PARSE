// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
  warnings: [],
};

const clipboardWriteText = vi.fn(async () => {});

const warningSummaryBase: PopulateSummary = {
  state: "ok",
  totalFilled: 2,
  perLang: { eng: 1, spa: 1 },
  warning: null,
  warnings: [],
};

describe("ClefPopulateSummaryBanner", () => {
  beforeEach(() => {
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWriteText },
    });
  });

  afterEach(() => {
    cleanup();
    clipboardWriteText.mockClear();
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

  it("renders no warnings section when warnings are empty", () => {
    render(
      <ClefPopulateSummaryBanner
        summary={{ ...warningSummaryBase, warnings: [] }}
        onDismiss={() => {}}
        onRetryWithProviders={() => {}}
      />,
    );

    expect(screen.queryByTestId("clef-populate-warning")).toBeNull();
    expect(screen.queryByRole("button", { name: /provider warnings/i })).toBeNull();
  });

  it("renders all warnings expanded when there are up to 3", async () => {
    const warnings = [
      "pylexibank: optional pylexibank package is not installed.",
      "grokipedia: no xAI or OpenAI API key is configured.",
    ];

    render(
      <ClefPopulateSummaryBanner
        summary={{ ...warningSummaryBase, warnings }}
        onDismiss={() => {}}
        onRetryWithProviders={() => {}}
      />,
    );

    expect(screen.getAllByTestId("clef-populate-warning")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /copy warnings/i }));
    await waitFor(() => {
      expect(clipboardWriteText).toHaveBeenCalledWith(warnings.join("\n"));
    });
  });

  it("defaults warnings collapsed when there are more than 3 and toggles open", () => {
    render(
      <ClefPopulateSummaryBanner
        summary={{ ...warningSummaryBase, warnings: ["w1", "w2", "w3", "w4"] }}
        onDismiss={() => {}}
        onRetryWithProviders={() => {}}
      />,
    );

    expect(screen.queryAllByTestId("clef-populate-warning")).toHaveLength(0);
    const toggle = screen.getByRole("button", { name: /4 provider warnings/i });
    fireEvent.click(toggle);
    expect(screen.getAllByTestId("clef-populate-warning")).toHaveLength(4);
  });
});
