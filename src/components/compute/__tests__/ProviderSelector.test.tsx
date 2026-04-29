// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProviderSelector, StatusBadge } from "../clef/ProviderSelector";

afterEach(() => {
  cleanup();
});

describe("StatusBadge", () => {
  it("renders the canonical tones for ready, needs_auth, and missing_file", () => {
    const { rerender } = render(<StatusBadge kind="ready" />);
    expect(screen.getByText("Ready").className).toContain("emerald");

    rerender(<StatusBadge kind="needs_auth" />);
    expect(screen.getByText(/Needs API key/i).className).toContain("amber");

    rerender(<StatusBadge kind="missing_file" />);
    expect(screen.getByText(/Local file missing/i).className).toContain("rose");
  });
});

describe("ProviderSelector", () => {
  const providers = [
    { id: "wiktionary", name: "Wiktionary" },
    { id: "literature", name: "Literature" },
    { id: "grok_llm", name: "Grok LLM" },
  ];

  it("keeps compact pill mode for legacy callers", () => {
    render(
      <ProviderSelector
        providers={providers}
        selectedProviders={new Set(["wiktionary"])}
        toggleProvider={() => {}}
        overwrite={false}
        setOverwrite={() => {}}
        saving={false}
      />,
    );

    expect(screen.getByRole("button", { name: "Wiktionary" })).toBeTruthy();
    expect(screen.queryByText(/Open lexical databases/i)).toBeNull();
  });

  it("renders grouped detailed mode with connect affordance for unauthed Grok LLM", () => {
    const onExpandAuth = vi.fn();
    render(
      <ProviderSelector
        mode="detailed"
        providers={providers}
        selectedProviders={new Set(["wiktionary", "grok_llm"])}
        toggleProvider={() => {}}
        overwrite={false}
        setOverwrite={() => {}}
        saving={false}
        providerStatuses={{
          wiktionary: "ready",
          literature: "missing_file",
          grok_llm: "needs_auth",
        }}
        onExpandAuth={onExpandAuth}
      />,
    );

    expect(screen.getByText(/Open lexical databases/i)).toBeTruthy();
    expect(screen.getByText(/Local sources/i)).toBeTruthy();
    expect(screen.getByText(/LLM-augmented search/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /connect/i }));
    expect(onExpandAuth).toHaveBeenCalledWith("grok_llm");
  });
});
