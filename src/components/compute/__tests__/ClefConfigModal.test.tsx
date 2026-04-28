// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockGetClefConfig = vi.fn();
const mockGetClefCatalog = vi.fn();
const mockGetClefProviders = vi.fn();
const mockSaveClefConfig = vi.fn();
const mockStartContactLexemeFetch = vi.fn();
const mockGetAuthStatus = vi.fn();

vi.mock("../../../api/client", () => ({
  getClefConfig: (...args: unknown[]) => mockGetClefConfig(...args),
  getClefCatalog: (...args: unknown[]) => mockGetClefCatalog(...args),
  getClefProviders: (...args: unknown[]) => mockGetClefProviders(...args),
  saveClefConfig: (...args: unknown[]) => mockSaveClefConfig(...args),
  startContactLexemeFetch: (...args: unknown[]) => mockStartContactLexemeFetch(...args),
  getAuthStatus: (...args: unknown[]) => mockGetAuthStatus(...args),
  saveApiKey: vi.fn(),
}));

import { ClefConfigModal } from "../ClefConfigModal";

function setupBaseMocks() {
  mockGetClefConfig.mockResolvedValue({
    configured: true,
    primary_contact_languages: ["ar"],
    languages: [{ code: "ar", name: "Arabic" }],
    config_path: "config/sil_contact_languages.json",
    concepts_csv_exists: true,
    meta: {},
  });
  mockGetClefCatalog.mockResolvedValue({
    languages: [{ code: "ar", name: "Arabic" }],
  });
  mockGetClefProviders.mockResolvedValue({
    providers: [
      { id: "wiktionary", name: "Wiktionary" },
      { id: "wikidata", name: "Wikidata" },
      { id: "asjp", name: "ASJP" },
      { id: "cldf", name: "CLDF" },
      { id: "pycldf", name: "pycldf" },
      { id: "pylexibank", name: "pylexibank" },
      { id: "lingpy_wordlist", name: "LingPy wordlist" },
      { id: "csv_override", name: "CSV override" },
      { id: "literature", name: "Literature" },
      { id: "grokipedia", name: "Grokipedia" },
    ],
  });
}

describe("ClefConfigModal", () => {
  beforeEach(() => {
    mockGetClefConfig.mockReset();
    mockGetClefCatalog.mockReset();
    mockGetClefProviders.mockReset();
    mockSaveClefConfig.mockReset();
    mockStartContactLexemeFetch.mockReset();
    mockGetAuthStatus.mockReset();
    setupBaseMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("defaults all ten providers to checked in the sources section", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: false, flow_active: false });
    render(<ClefConfigModal open onClose={() => {}} />);

    expect(screen.queryByLabelText(/Grokipedia/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /2\. sources/i }));

    await waitFor(() => screen.getByText(/9 of 10 sources will run/i));
    expect(screen.getByText(/9 of 10 sources will run/i)).toBeTruthy();
    expect(screen.getByLabelText(/Grokipedia/i)).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: /search contact languages/i })).toBeNull();
  });

  it("blocks Start when Grokipedia is selected without an API key", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: false, flow_active: false });
    render(<ClefConfigModal open onClose={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /2\. sources/i }));
    await waitFor(() => screen.getByText(/9 of 10 sources will run/i));
    fireEvent.click(screen.getByRole("button", { name: /start search/i }));

    expect(await screen.findByText(/Grokipedia is selected but no API key is configured/i)).toBeTruthy();
    expect(mockSaveClefConfig).not.toHaveBeenCalled();
    expect(mockStartContactLexemeFetch).not.toHaveBeenCalled();
  });

  it("switching tabs hides the previous tab content", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: false, flow_active: false });
    render(<ClefConfigModal open onClose={() => {}} />);

    await waitFor(() => expect(screen.getByLabelText(/search contact languages/i)).toBeTruthy());
    expect(screen.queryByLabelText(/Wiktionary/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /2\. sources/i }));

    await waitFor(() => expect(screen.getByLabelText(/Wiktionary/i)).toBeTruthy());
    expect(screen.queryByLabelText(/search contact languages/i)).toBeNull();
  });

  it("switches back to the Languages tab when Start is clicked without a primary language", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: "xai", flow_active: false });
    mockGetClefConfig.mockResolvedValue({
      configured: true,
      primary_contact_languages: [],
      languages: [{ code: "ar", name: "Arabic" }],
      config_path: "config/sil_contact_languages.json",
      concepts_csv_exists: true,
      meta: {},
    });
    render(<ClefConfigModal open initialTab="populate" onClose={() => {}} />);

    await waitFor(() => expect(screen.getByLabelText(/Wiktionary/i)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /start search/i }));

    expect(await screen.findByText(/Pick at least one primary contact language\./i)).toBeTruthy();
    expect(screen.getByLabelText(/search contact languages/i)).toBeTruthy();
    expect(screen.queryByLabelText(/Wiktionary/i)).toBeNull();
    expect(mockSaveClefConfig).not.toHaveBeenCalled();
  });
});
