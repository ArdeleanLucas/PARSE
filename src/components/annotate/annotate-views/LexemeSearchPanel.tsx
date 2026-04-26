import { useMemo } from "react";

import { Button } from "../../shared/Button";
import { Input } from "../../shared/Input";
import { useAnnotateSelection } from "./useAnnotateSelection";
import { useLexemeSearchJob } from "./useLexemeSearchJob";
import { LexemeResults } from "./LexemeResults";
import type { LexemeSearchPanelProps } from "./types";
import { formatSearchTime } from "./shared";

export function LexemeSearchPanel({ onSeek }: LexemeSearchPanelProps) {
  const { activeConceptId, activeSpeaker, concepts, record } = useAnnotateSelection();

  const activeConcept = useMemo(
    () => concepts.find((concept) => concept.id === activeConceptId) ?? null,
    [concepts, activeConceptId],
  );

  const existingAnchor = useMemo(() => {
    if (!record || !activeConceptId) return null;
    return record.confirmed_anchors?.[String(activeConceptId)] ?? null;
  }, [record, activeConceptId]);

  const {
    busy,
    candidates,
    clearAnchor,
    confirmCandidate,
    keyOf,
    response,
    runSearch,
    seedHint,
    selectCandidate,
    selectedKey,
    setVariantsRaw,
    status,
    useSeed,
    variantsRaw,
  } = useLexemeSearchJob({
    activeConceptId,
    activeSpeaker,
    conceptLabel: activeConcept?.label ?? "",
  });

  return (
    <div
      style={{
        border: "1px solid #bfdbfe",
        borderRadius: "0.25rem",
        background: "#eff6ff",
        fontFamily: "monospace",
        fontSize: "0.8125rem",
        padding: "0.75rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <div style={{ fontWeight: 700, color: "#1e3a8a" }}>Search &amp; anchor lexeme</div>
        {activeConcept && (
          <div style={{ fontSize: "0.75rem", color: "#475569" }}>
            concept <span style={{ color: "#1e3a8a" }}>#{activeConcept.id}</span>
            <span style={{ color: "#64748b" }}> — {activeConcept.label}</span>
          </div>
        )}
      </div>

      {existingAnchor && (
        <div
          style={{
            padding: "0.375rem 0.5rem",
            borderRadius: "0.25rem",
            background: "#dcfce7",
            color: "#166534",
            fontSize: "0.75rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span>
            Confirmed anchor: <strong>{formatSearchTime(existingAnchor.start)}–{formatSearchTime(existingAnchor.end)}</strong>
            {existingAnchor.matched_text ? <> · {existingAnchor.matched_text}</> : null}
            {existingAnchor.source ? <span style={{ color: "#15803d", marginLeft: "0.5rem" }}>({existingAnchor.source})</span> : null}
          </span>
          <Button variant="secondary" size="sm" onClick={clearAnchor}>
            Clear
          </Button>
        </div>
      )}

      <div style={{ color: "#475569", fontSize: "0.75rem" }}>
        Two-signal ranking across <code>ortho_words</code>, <code>ortho</code>, <code>stt</code>, <code>ipa</code> +
        cross-speaker confirmed anchors. Separate variants with spaces or commas
        (e.g. <code>yek, yak, jek</code>).
      </div>

      <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
        <div style={{ flex: 1 }}>
          <Input
            label="Variants"
            placeholder={seedHint ? `e.g. ${seedHint}` : "yek, yak, jek"}
            value={variantsRaw}
            onChange={(e) => setVariantsRaw(e.target.value)}
            onKeyDown={async (e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const first = await runSearch();
                if (first) onSeek?.(first.start);
              }
            }}
          />
        </div>
        <Button variant="secondary" size="sm" onClick={useSeed} disabled={!seedHint}>
          Use label
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={async () => {
            const first = await runSearch();
            if (first) onSeek?.(first.start);
          }}
          disabled={busy}
        >
          {busy ? "Searching…" : "Search"}
        </Button>
      </div>

      {status && (
        <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{status}</div>
      )}

      {response?.signals_available.contact_variants.length ? (
        <div style={{ fontSize: "0.7rem", color: "#475569" }}>
          Auto-augmented with contact-language variants:{" "}
          <span style={{ color: "#1e3a8a" }}>{response.signals_available.contact_variants.join(", ")}</span>
        </div>
      ) : null}

      <LexemeResults
        candidates={candidates}
        onConfirm={confirmCandidate}
        onSeek={onSeek}
        response={response}
        selectedKey={selectedKey}
        setSelectedKey={selectCandidate}
        keyOf={keyOf}
      />
    </div>
  );
}
