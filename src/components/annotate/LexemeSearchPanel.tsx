import { useEffect, useMemo, useState } from "react";
import { useUIStore } from "../../stores/uiStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import { useConfigStore } from "../../stores/configStore";
import { Button } from "../shared/Button";
import { Input } from "../shared/Input";
import {
  searchLexeme,
  type LexemeSearchCandidate,
  type LexemeSearchResponse,
} from "../../api/client";

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
 * Search & Anchor Lexeme — PR B (backend-powered, two-signal scoring).
 *
 * The user-facing entry point to the Lexical Anchor Alignment System.
 * Calls `GET /api/lexeme/search`, which combines:
 *   - within-speaker phonetic similarity (orthographic + IPA Levenshtein),
 *   - cross-speaker confirmed-anchor matching for the same concept,
 *   - ortho_words confidence weighting from PR #178.
 *
 * "Confirm & Use" persists the chosen candidate's time range to
 * `AnnotationRecord.confirmed_anchors[concept_id]` (sidecar — survives
 * Praat/TextGrid round-trips). Subsequent searches against other speakers
 * for the same concept will pick up this anchor as a cross-speaker
 * reference and rank candidates near it more confidently — that's how
 * the "later speakers get faster" curve compounds.
 */
export function LexemeSearchPanel({ onSeek }: LexemeSearchPanelProps) {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const activeConceptId = useUIStore((s) => s.activeConcept);
  const concepts = useConfigStore((s) => s.config?.concepts ?? []);
  const record = useAnnotationStore((s) =>
    activeSpeaker ? s.records[activeSpeaker] ?? null : null,
  );
  const setConfirmedAnchor = useAnnotationStore((s) => s.setConfirmedAnchor);

  const activeConcept = useMemo(
    () => concepts.find((c) => c.id === activeConceptId) ?? null,
    [concepts, activeConceptId],
  );

  const [variantsRaw, setVariantsRaw] = useState("");
  const [response, setResponse] = useState<LexemeSearchResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);

  // Reset transient UI when the user switches speaker or concept.
  useEffect(() => {
    setResponse(null);
    setSelectedKey(null);
    setStatus("");
  }, [activeSpeaker, activeConceptId]);

  const seedHint = activeConcept?.label ?? "";

  const existingAnchor = useMemo(() => {
    if (!record || !activeConceptId) return null;
    return record.confirmed_anchors?.[String(activeConceptId)] ?? null;
  }, [record, activeConceptId]);

  const parseVariants = (raw: string): string[] =>
    raw
      .split(/[\s,;/]+/)
      .map((v) => v.trim())
      .filter(Boolean);

  const runSearch = async () => {
    const variants = parseVariants(variantsRaw);
    if (variants.length === 0) {
      setResponse(null);
      setStatus("Enter at least one variant.");
      return;
    }
    if (!activeSpeaker) {
      setResponse(null);
      setStatus("No speaker selected.");
      return;
    }
    setBusy(true);
    setStatus("Searching…");
    try {
      const resp = await searchLexeme(activeSpeaker, variants, {
        conceptId: activeConceptId ? String(activeConceptId) : undefined,
      });
      setResponse(resp);
      const first = resp.candidates[0];
      setSelectedKey(first ? keyOf(first) : null);
      if (first) onSeek?.(first.start);
      setStatus(buildStatusLine(resp));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setResponse({
        speaker: activeSpeaker,
        concept_id: activeConceptId ? String(activeConceptId) : null,
        variants,
        language: "ku",
        candidates: [],
        signals_available: { phonemizer: false, cross_speaker_anchors: 0, contact_variants: [] },
      });
      setStatus(`Search failed: ${message}`);
    } finally {
      setBusy(false);
    }
  };

  const keyOf = (c: LexemeSearchCandidate) =>
    `${c.tier}|${c.start.toFixed(3)}|${c.end.toFixed(3)}`;

  const useSeed = () => {
    if (seedHint) setVariantsRaw(seedHint);
  };

  const confirmCandidate = (c: LexemeSearchCandidate) => {
    if (!activeSpeaker || !activeConceptId) return;
    setConfirmedAnchor(activeSpeaker, String(activeConceptId), {
      start: c.start,
      end: c.end,
      source: `user+${c.tier}`,
      confirmed_at: new Date().toISOString(),
      matched_text: c.matched_text,
      matched_variant: c.matched_variant,
      variants_used: response?.variants ?? parseVariants(variantsRaw),
    });
    setStatus(
      `Anchor confirmed at ${formatTime(c.start)}–${formatTime(c.end)} (${c.matched_text}).`,
    );
  };

  const clearAnchor = () => {
    if (!activeSpeaker || !activeConceptId) return;
    setConfirmedAnchor(activeSpeaker, String(activeConceptId), null);
    setStatus("Anchor cleared.");
  };

  const candidates = response?.candidates ?? [];
  const signals = response?.signals_available;

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
            Confirmed anchor: <strong>{formatTime(existingAnchor.start)}–{formatTime(existingAnchor.end)}</strong>
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
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void runSearch();
              }
            }}
          />
        </div>
        <Button variant="secondary" size="sm" onClick={useSeed} disabled={!seedHint}>
          Use label
        </Button>
        <Button variant="primary" size="sm" onClick={() => void runSearch()} disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </Button>
      </div>

      {status && (
        <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{status}</div>
      )}

      {signals && signals.contact_variants.length > 0 && (
        <div style={{ fontSize: "0.7rem", color: "#475569" }}>
          Auto-augmented with contact-language variants:{" "}
          <span style={{ color: "#1e3a8a" }}>{signals.contact_variants.join(", ")}</span>
        </div>
      )}

      {candidates.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", marginTop: "0.25rem" }}>
          <div style={{ fontSize: "0.7rem", fontWeight: 600, color: "#1e3a8a", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Candidates
          </div>
          {candidates.map((c) => {
            const key = keyOf(c);
            const isSelected = selectedKey === key;
            return (
              <div
                key={key}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto auto",
                  gap: "0.5rem",
                  alignItems: "center",
                  padding: "0.375rem 0.5rem",
                  borderRadius: "0.25rem",
                  border: `1px solid ${isSelected ? "#1d4ed8" : "#cbd5e1"}`,
                  background: isSelected ? "#dbeafe" : "#ffffff",
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setSelectedKey(key);
                    onSeek?.(c.start);
                  }}
                  style={{
                    background: "transparent",
                    border: 0,
                    padding: 0,
                    color: "#475569",
                    cursor: "pointer",
                    fontFamily: "monospace",
                    fontSize: "0.75rem",
                  }}
                  title="Click to seek the waveform here"
                >
                  {formatTime(c.start)}–{formatTime(c.end)}
                </button>
                <span
                  style={{
                    color: "#0f172a",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={`Phonetic ${c.phonetic_score.toFixed(3)}, cross-speaker bonus ${c.cross_speaker_score.toFixed(3)}, confidence ${c.confidence_weight.toFixed(2)}`}
                >
                  {c.matched_text}
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
                  {c.source_label}
                </span>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => confirmCandidate(c)}
                  title="Save this time range as the confirmed anchor for this concept on this speaker."
                >
                  Confirm
                </Button>
              </div>
            );
          })}
        </div>
      )}

      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          alignItems: "center",
          borderTop: "1px solid #bfdbfe",
          paddingTop: "0.5rem",
          marginTop: "0.25rem",
        }}
      >
        <Button
          variant="secondary"
          size="sm"
          disabled={true}
          title="Coming in PR C — confirm a few anchors first, then bulk-align the remaining concepts for this speaker using the confirmed anchors as scaffolding."
        >
          Bulk align remaining (coming in PR C)
        </Button>
        {signals && (
          <span style={{ fontSize: "0.7rem", color: "#64748b", marginLeft: "auto" }}>
            phonemizer {signals.phonemizer ? "✓" : "—"} · cross-speaker anchors {signals.cross_speaker_anchors}
          </span>
        )}
      </div>
    </div>
  );
}

function buildStatusLine(resp: LexemeSearchResponse): string {
  const n = resp.candidates.length;
  if (n === 0) {
    return "No candidates above confidence threshold. Try adding variants or fuzzier spellings.";
  }
  const bits: string[] = [`${n} candidate${n === 1 ? "" : "s"}.`];
  if (!resp.signals_available.phonemizer) {
    bits.push("Phonemizer unavailable — scoring on orthographic similarity only.");
  }
  if (resp.signals_available.cross_speaker_anchors > 0) {
    bits.push(`${resp.signals_available.cross_speaker_anchors} cross-speaker anchor(s) in scoring.`);
  }
  return bits.join(" ");
}

function tierChipBg(tier: string): string {
  switch (tier) {
    case "ortho_words": return "#059669";
    case "ortho":       return "#2563eb";
    case "stt":         return "#6366f1";
    case "ipa":         return "#8b5cf6";
    default:            return "#64748b";
  }
}
