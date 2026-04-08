// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { CompareMode } from "./CompareMode";

vi.mock("./ConceptTable", () => ({ ConceptTable: () => <div data-testid="concept-table" /> }));
vi.mock("./CognateControls", () => ({ CognateControls: () => <div data-testid="cognate-controls" /> }));
vi.mock("./BorrowingPanel", () => ({ BorrowingPanel: () => <div data-testid="borrowing-panel" /> }));
vi.mock("./EnrichmentsPanel", () => ({ EnrichmentsPanel: () => <div data-testid="enrichments-panel" /> }));
vi.mock("./TagManager", () => ({
  TagManager: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="tag-manager" /> : null,
}));
vi.mock("./SpeakerImport", () => ({
  SpeakerImport: ({ onImportComplete }: { onImportComplete?: () => void }) => (
    <button data-testid="speaker-import" onClick={onImportComplete}>Done</button>
  ),
}));

vi.mock("../shared/TopBar", () => ({
  TopBar: ({ children }: { children?: React.ReactNode }) => (
    <nav data-testid="top-bar">{children}</nav>
  ),
}));

vi.mock("../shared/Modal", () => ({
  Modal: ({ open, children, onClose }: { open: boolean; children: React.ReactNode; onClose: () => void }) =>
    open ? <div data-testid="modal"><button onClick={onClose}>Close</button>{children}</div> : null,
}));

const mockLoad = vi.fn().mockResolvedValue(undefined);
const mockHydrate = vi.fn();
const mockSetComparePanel = vi.fn();
let mockComparePanel: "cognate" | "borrowing" | "enrichments" | "tags" = "cognate";
let mockActiveConcept: string | null = null;

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (state: {
    comparePanel: "cognate" | "borrowing" | "enrichments" | "tags";
    setComparePanel: (panel: "cognate" | "borrowing" | "enrichments" | "tags") => void;
    activeConcept: string | null;
  }) => unknown) =>
    selector({
      comparePanel: mockComparePanel,
      setComparePanel: mockSetComparePanel,
      activeConcept: mockActiveConcept,
    }),
}));

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (state: {
    data: Record<string, unknown>;
    loading: boolean;
    load: () => Promise<void>;
  }) => unknown) =>
    selector({ data: {}, loading: false, load: mockLoad }),
}));

vi.mock("../../stores/tagStore", () => ({
  useTagStore: (selector: (state: { hydrate: () => void }) => unknown) =>
    selector({ hydrate: mockHydrate }),
}));

describe("CompareMode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockComparePanel = "cognate";
    mockActiveConcept = null;
  });

  afterEach(() => {
    cleanup();
  });

  it("renders ConceptTable on mount", () => {
    render(<CompareMode />);
    expect(screen.getByTestId("concept-table")).toBeDefined();
  });

  it("calls enrichmentStore.load() on mount when data is null", () => {
    render(<CompareMode />);
    expect(mockLoad).toHaveBeenCalledOnce();
  });

  it("calls tagStore.hydrate() on mount", () => {
    render(<CompareMode />);
    expect(mockHydrate).toHaveBeenCalledOnce();
  });

  it("sidebar switches to BorrowingPanel when Borrowing tab clicked", () => {
    render(<CompareMode />);
    fireEvent.click(screen.getByTestId("tab-borrowing"));
    expect(mockSetComparePanel).toHaveBeenCalledWith("borrowing");
  });

  it("CognateControls is not rendered when activeConcept is null", () => {
    render(<CompareMode />);
    expect(screen.queryByTestId("cognate-controls")).toBeNull();
  });

  it("CognateControls renders when activeConcept is set", () => {
    mockActiveConcept = "water";
    mockComparePanel = "cognate";

    render(<CompareMode />);
    expect(screen.getByTestId("cognate-controls")).toBeDefined();
  });
});
