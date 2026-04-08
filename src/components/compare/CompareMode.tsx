// CompareMode — root component at /compare.
import { useState, useEffect } from "react";
import { TopBar } from "../shared/TopBar";
import { Modal } from "../shared/Modal";
import { ConceptTable } from "./ConceptTable";
import { CognateControls } from "./CognateControls";
import { BorrowingPanel } from "./BorrowingPanel";
import { EnrichmentsPanel } from "./EnrichmentsPanel";
import { TagManager } from "./TagManager";
import { SpeakerImport } from "./SpeakerImport";
import { useUIStore } from "../../stores/uiStore";
import { useEnrichmentStore } from "../../stores/enrichmentStore";
import { useTagStore } from "../../stores/tagStore";

const TABS = [
  { id: "cognate" as const, label: "Cognate" },
  { id: "borrowing" as const, label: "Borrowing" },
  { id: "enrichments" as const, label: "Enrichments" },
  { id: "tags" as const, label: "Tags" },
] as const;

export function CompareMode() {
  const comparePanel = useUIStore((s) => s.comparePanel);
  const setComparePanel = useUIStore((s) => s.setComparePanel);
  const activeConcept = useUIStore((s) => s.activeConcept);
  const enrichmentData = useEnrichmentStore((s) => s.data);
  const loadEnrichments = useEnrichmentStore((s) => s.load);
  const hydrateTags = useTagStore((s) => s.hydrate);

  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    if (Object.keys(enrichmentData).length === 0) {
      loadEnrichments().catch(() => {});
    }
    hydrateTags();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      data-testid="compare-mode"
      style={{ display: "flex", flexDirection: "column", height: "100vh", fontFamily: "monospace" }}
    >
      <TopBar>
        <button
          onClick={() => setImportOpen(true)}
          style={{ padding: "0.25rem 0.75rem", cursor: "pointer", fontFamily: "monospace" }}
        >
          Import Speaker
        </button>
      </TopBar>

      <div style={{ flex: 1, overflow: "auto" }}>
        <ConceptTable />
      </div>

      <div style={{ borderTop: "1px solid #374151" }}>
        {/* Sidebar tab bar */}
        <div style={{ display: "flex", borderBottom: "1px solid #374151" }}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              data-testid={`tab-${tab.id}`}
              onClick={() => setComparePanel(tab.id)}
              style={{
                padding: "0.5rem 1rem",
                cursor: "pointer",
                fontFamily: "monospace",
                background: comparePanel === tab.id ? "#1f2937" : "transparent",
                border: "none",
                borderBottom: comparePanel === tab.id ? "2px solid #60a5fa" : "2px solid transparent",
                color: comparePanel === tab.id ? "#f9fafb" : "#9ca3af",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Sidebar panel */}
        <div style={{ padding: "0.5rem", minHeight: "200px" }}>
          {comparePanel === "cognate" && !activeConcept && (
            <div style={{ padding: "1rem", color: "#9ca3af" }}>Select a concept to see cognates</div>
          )}
          {comparePanel === "cognate" && activeConcept && (
            <CognateControls />
          )}
          {comparePanel === "borrowing" && <BorrowingPanel />}
          {comparePanel === "enrichments" && <EnrichmentsPanel activeConcept={activeConcept} />}
          {comparePanel === "tags" && <TagManager isOpen={true} onClose={() => {}} />}
        </div>
      </div>

      <Modal open={importOpen} onClose={() => setImportOpen(false)} title="Import Speaker">
        <SpeakerImport onImportComplete={() => setImportOpen(false)} />
      </Modal>
    </div>
  );
}
