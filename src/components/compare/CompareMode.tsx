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
  const comparePanel = useUIStore((store) => store.comparePanel);
  const setComparePanel = useUIStore((store) => store.setComparePanel);
  const activeConcept = useUIStore((store) => store.activeConcept);

  const enrichmentData = useEnrichmentStore((store) => store.data);
  const loadEnrichments = useEnrichmentStore((store) => store.load);

  const hydrateTags = useTagStore((store) => store.hydrate);

  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    if (enrichmentData == null || Object.keys(enrichmentData).length === 0) {
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
          data-testid="open-speaker-import"
          onClick={() => setImportOpen(true)}
          style={{ padding: "0.25rem 0.75rem", cursor: "pointer", fontFamily: "monospace" }}
        >
          Import Speaker
        </button>
      </TopBar>

      <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ flex: 1, overflow: "auto" }}>
          <ConceptTable />
        </div>

        <section style={{ borderTop: "1px solid #e5e7eb", flexShrink: 0 }}>
          <div style={{ display: "flex", borderBottom: "1px solid #e5e7eb" }}>
            {TABS.map((tab) => (
              <button
                key={tab.id}
                data-testid={`tab-${tab.id}`}
                onClick={() => setComparePanel(tab.id)}
                style={{
                  padding: "0.5rem 1rem",
                  cursor: "pointer",
                  fontFamily: "monospace",
                  border: "none",
                  borderBottom:
                    comparePanel === tab.id ? "2px solid #3b82f6" : "2px solid transparent",
                  background: "transparent",
                  color: comparePanel === tab.id ? "#1f2937" : "#6b7280",
                  fontWeight: comparePanel === tab.id ? 600 : 400,
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div style={{ minHeight: 200 }}>
            {comparePanel === "cognate" && activeConcept === null && (
              <div style={{ padding: "1rem", color: "#9ca3af" }}>
                Select a concept to inspect cognate sets.
              </div>
            )}
            {comparePanel === "cognate" && activeConcept !== null && <CognateControls />}
            {comparePanel === "borrowing" && <BorrowingPanel />}
            {comparePanel === "enrichments" && (
              <EnrichmentsPanel activeConcept={activeConcept} />
            )}
            {comparePanel === "tags" && (
              <div style={{ padding: "1rem", color: "#6b7280" }}>
                Tag manager opened.
              </div>
            )}
          </div>
        </section>
      </main>

      <TagManager
        isOpen={comparePanel === "tags"}
        onClose={() => setComparePanel("cognate")}
      />

      <Modal open={importOpen} onClose={() => setImportOpen(false)} title="Import Speaker">
        <SpeakerImport onImportComplete={() => setImportOpen(false)} />
      </Modal>
    </div>
  );
}
