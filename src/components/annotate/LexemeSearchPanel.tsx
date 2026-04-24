import { useMemo, useState } from "react";
import { useUIStore } from "../../stores/uiStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import { useConfigStore } from "../../stores/configStore";
import { Button } from "../shared/Button";
import { Input } from "../shared/Input";
import { searchLexeme, type LexemeCandidate } from "../../lib/lexemeSearch";

interface LexemeSearchPanelProps {
  onSeek?: (timeSec: number) => void;
}

/** Format seconds as "m:ss.sss" for compact time labels on candidates. */
function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}

/**
 * Search & Anchor Lexeme — PR A (UI scaffold + client-side scoring).
 *
 * The scaffold half of the Lexical Anchor Alignment System. Takes a
 * comma/whitespace-separated list of orthographic variants (the user knows
 * they're searching for e.g. "yek / yak / jek"), scans the already-loaded
 * tiers on the active speaker, and lists ranked candidate time ranges.
 * Clicking a candidate seeks the waveform there; the user drops into the
 * existing region/annotation flow to confirm.
 *
 * PR B replaces `searchLexeme()` with a backend call to
 * `GET /api/lexeme/search` that adds phonetic IPA similarity + cross-speaker
 * confirmed-anchor matching. The UI surface stays stable across the cut-over.
 */
export function LexemeSearchPanel({ onSeek }: LexemeSearchPanelProps) {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const activeConceptId = useUIStore((s) => s.activeConcept);
  const concepts = useConfigStore((s) => s.config?.concepts ?? []);
  const record = useAnnotationStore((s) =>
    activeSpeaker ? s.records[activeSpeaker] ?? null : null,
  );

  const activeConcept = useMemo(
    () => concepts.find((c) => c.id === activeConceptId) ?? null,
    [concepts, activeConceptId],
  );

  // Variants input: comma- or space-separated. Seeded with the concept's
  // English label as a hint (the user almost always overwrites it with
  // the Kurdish form they know), but kept editable.
  const [variantsRaw, setVariantsRaw] = useState("");
  const [results, setResults] = useState<LexemeCandidate[] | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");

  // Seed input whenever the active concept changes. Only overwrites when
  // the field is empty to avoid clobbering mid-typed user input.
  const seedHint = activeConcept?.label ?? "";

  const parseVariants = (raw: string): string[] =>
    raw
      .split(/[\s,;/]+/)
      .map((v) => v.trim())
      .filter(Boolean);

  const runSearch = () => {
    const variants = parseVariants(variantsRaw);
    if (variants.length === 0) {
      setResults([]);
      setStatus("Enter at least one variant.");
      return;
    }
    if (!record) {
      setResults([]);
      setStatus("No annotation record loaded for this speaker.");
      return;
    }
    const hits = searchLexeme(record, variants);
    setResults(hits);
    setSelectedKey(hits.length > 0 ? keyOf(hits[0]) : null);
    if (hits.length > 0) onSeek?.(hits[0].start);
    setStatus(
      hits.length === 0
        ? "No candidates above confidence threshold. Try adding variants or fuzzier spellings."
        : `${hits.length} candidate${hits.length === 1 ? "" : "s"}.`,
    );
  };

  const keyOf = (c: LexemeCandidate) => `${c.tier}|${c.start.toFixed(3)}|${c.end.toFixed(3)}`;

  const useSeed = () => {
    if (seedHint) setVariantsRaw(seedHint);
  };

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

      <div style={{ color: "#475569", fontSize: "0.75rem" }}>
        Scans <code>ortho_words</code>, <code>ortho</code>, <code>stt</code>, and <code>ipa</code> tiers
        for fuzzy matches. Separate multiple variants with spaces or commas
        (e.g. <code>yek, yak, jek</code>).
      </div>

      <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
        <div style={{ flex: 1 }}>
          <Input
            label="Variants"
            placeholder={seedHint ? `e.g. ${seedHint}` : "yek, yak, jek"}
            value={variantsRaw}
            onChange={(e) => setVariantsRaw(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                runSearch();
              }
            }}
          />
        </div>
        <Button variant="secondary" size="sm" onClick={useSeed} disabled={!seedHint}>
          Use label
        </Button>
        <Button variant="primary" size="sm" onClick={runSearch}>
          Search
        </Button>
      </div>

      {status && (
        <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{status}</div>
      )}

      {results !== null && results.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", marginTop: "0.25rem" }}>
          <div style={{ fontSize: "0.7rem", fontWeight: 600, color: "#1e3a8a", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Candidates
          </div>
          {results.map((c) => {
            const key = keyOf(c);
            const isSelected = selectedKey === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setSelectedKey(key);
                  onSeek?.(c.start);
                }}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto",
                  gap: "0.5rem",
                  alignItems: "center",
                  padding: "0.375rem 0.5rem",
                  borderRadius: "0.25rem",
                  border: `1px solid ${isSelected ? "#1d4ed8" : "#cbd5e1"}`,
                  background: isSelected ? "#dbeafe" : "#ffffff",
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                  textAlign: "left",
                  cursor: "pointer",
                }}
                title={`Matched "${c.matchedVariant}" against ${c.tier} — score ${c.score.toFixed(3)}`}
              >
                <span style={{ color: "#475569" }}>
                  {formatTime(c.start)}–{formatTime(c.end)}
                </span>
                <span style={{ color: "#0f172a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.matchedText}
                </span>
                <span
                  style={{
                    fontSize: "0.65rem",
                    padding: "0.125rem 0.375rem",
                    borderRadius: "999px",
                    background: tierChipBg(c.tier),
                    color: "#fff",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c.sourceLabel}
                </span>
              </button>
            );
          })}
        </div>
      )}

      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          borderTop: "1px solid #bfdbfe",
          paddingTop: "0.5rem",
          marginTop: "0.25rem",
        }}
      >
        <Button
          variant="secondary"
          size="sm"
          disabled={true}
          title="Coming in PR B (backend /api/lexeme/search + confirmed-anchor persistence). Confirm a candidate first, then bulk-align the rest of the concepts for this speaker."
        >
          Bulk align remaining (coming in PR B)
        </Button>
      </div>
    </div>
  );
}

function tierChipBg(tier: string): string {
  switch (tier) {
    case "ortho_words": return "#059669"; // emerald — highest confidence
    case "ortho":       return "#2563eb"; // blue
    case "stt":         return "#6366f1"; // indigo
    case "ipa":         return "#8b5cf6"; // violet
    default:            return "#64748b";
  }
}
