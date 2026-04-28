// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockSaveApiKey = vi.fn();
const mockGetAuthStatus = vi.fn();

vi.mock("../../../api/client", () => ({
  saveApiKey: (...args: unknown[]) => mockSaveApiKey(...args),
  getAuthStatus: (...args: unknown[]) => mockGetAuthStatus(...args),
}));

import { ProviderApiKeyForm } from "../clef/ProviderApiKeyForm";

describe("ProviderApiKeyForm", () => {
  beforeEach(() => {
    mockSaveApiKey.mockReset();
    mockGetAuthStatus.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("switches between xAI and OpenAI key modes", () => {
    render(
      <ProviderApiKeyForm
        onCancel={() => {}}
        onSaved={() => {}}
      />,
    );

    expect(screen.getByPlaceholderText("xai-...")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /openai/i }));
    expect(screen.getByPlaceholderText("sk-...")).toBeTruthy();
  });

  it("tests and saves the key, then refreshes auth status and notifies the parent", async () => {
    const onSaved = vi.fn();
    mockSaveApiKey.mockResolvedValue({ authenticated: true, provider: "xai", method: "api_key" });
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: "xai", method: "api_key" });

    render(
      <ProviderApiKeyForm
        onCancel={() => {}}
        onSaved={onSaved}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("xai-..."), {
      target: { value: "xai-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /test & save/i }));

    await waitFor(() => expect(mockSaveApiKey).toHaveBeenCalledWith("xai-secret", "xai"));
    await waitFor(() => expect(mockGetAuthStatus).toHaveBeenCalledTimes(1));
    expect(onSaved).toHaveBeenCalledWith({ authenticated: true, provider: "xai", method: "api_key" });
    expect(screen.getByText(/saved and connected/i)).toBeTruthy();
  });

  it("renders backend save errors inline", async () => {
    mockSaveApiKey.mockRejectedValue(new Error("bad key"));

    render(
      <ProviderApiKeyForm
        onCancel={() => {}}
        onSaved={() => {}}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("xai-..."), {
      target: { value: "xai-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /test & save/i }));

    expect(await screen.findByText("bad key")).toBeTruthy();
    expect(mockGetAuthStatus).not.toHaveBeenCalled();
  });
});
