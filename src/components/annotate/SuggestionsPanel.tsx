import { useUIStore } from "../../stores/uiStore"
import { useSuggestions, type Suggestion } from "../../hooks/useSuggestions"

interface SuggestionsPanelProps {
  onSeek: (timeSec: number, createRegion?: boolean, durationSec?: number) => void
}

const confidenceColor = (score: number) => {
  if (score > 0.8) return "#15803d"
  if (score > 0.5) return "#b45309"
  return "#b91c1c"
}

const confidenceLabel = (score: number) => {
  if (score > 0.8) return "high"
  if (score > 0.5) return "medium"
  return "low"
}

export function SuggestionsPanel({ onSeek }: SuggestionsPanelProps) {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker)
  const activeConcept = useUIStore((s) => s.activeConcept)
  const {
    suggestions,
    loading,
    error,
    priorSpeakers,
    selectedPriors,
    setSelectedPriors,
    expectedTimeSec,
  } = useSuggestions({ speaker: activeSpeaker, conceptId: activeConcept })

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px", padding: "8px" }}>
      {priorSpeakers.length > 0 && (
        <div style={{ border: "1px solid #d1d5db", borderRadius: "6px", padding: "8px" }}>
          <div style={{ fontWeight: 600, marginBottom: "6px" }}>Positional priors</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {priorSpeakers.map((sp) => (
              <label key={sp} style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={selectedPriors.includes(sp)}
                  onChange={() => {
                    if (selectedPriors.includes(sp)) {
                      setSelectedPriors(selectedPriors.filter((p) => p !== sp))
                    } else {
                      setSelectedPriors([...selectedPriors, sp])
                    }
                  }}
                />
                {sp}
              </label>
            ))}
          </div>
          <div style={{ display: "flex", gap: "6px", marginTop: "8px" }}>
            <button
              onClick={() => setSelectedPriors([...priorSpeakers])}
              style={{ padding: "2px 8px", fontSize: "12px", cursor: "pointer" }}
            >
              Recommended
            </button>
            <button
              onClick={() => setSelectedPriors([])}
              style={{ padding: "2px 8px", fontSize: "12px", cursor: "pointer" }}
            >
              Clear
            </button>
          </div>
          {selectedPriors.length > 0 && expectedTimeSec !== null && (
            <div style={{ marginTop: "6px", fontSize: "13px", color: "#6b7280" }}>
              Expected: {expectedTimeSec.toFixed(1)}s
            </div>
          )}
        </div>
      )}

      {loading && (
        <div style={{ textAlign: "center", padding: "16px", color: "#6b7280" }}>
          <div data-testid="loading-spinner" style={{ display: "inline-block", width: "20px", height: "20px", border: "2px solid #d1d5db", borderTopColor: "#3b82f6", borderRadius: "50%", animation: "spin 0.6s linear infinite" }} />
          <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
        </div>
      )}

      {error && (
        <div style={{ color: "#b91c1c", padding: "8px", fontSize: "13px" }}>{error}</div>
      )}

      {!loading && !error && suggestions.length === 0 && (
        <div style={{ color: "#6b7280", padding: "8px", fontSize: "13px" }}>
          No suggestions for this concept/speaker
        </div>
      )}

      {!loading &&
        suggestions.map((s: Suggestion) => (
          <div
            key={`${s.rank}-${s.start_sec}`}
            data-testid="suggestion-card"
            onClick={() => onSeek(s.start_sec, true, s.end_sec - s.start_sec)}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: "6px",
              padding: "8px",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
              <span style={{ fontWeight: 600 }}>#{s.rank}</span>
              <span style={{ color: "#6b7280" }}>{s.start_sec.toFixed(3)}s</span>
              <span
                style={{
                  color: confidenceColor(s.confidence_score),
                  fontWeight: 600,
                }}
              >
                {confidenceLabel(s.confidence_score)}
              </span>
            </div>
            <div style={{ color: "#6b7280", fontSize: "12px" }}>{s.match_method}</div>
            {s.transcript_snippet && (
              <div style={{ marginTop: "4px", fontSize: "12px", color: "#374151" }}>
                {s.transcript_snippet.length > 80
                  ? s.transcript_snippet.slice(0, 80) + "..."
                  : s.transcript_snippet}
              </div>
            )}
            {s.source_wav && (
              <div style={{ marginTop: "2px", fontSize: "11px", color: "#9ca3af" }}>
                {s.source_wav.split("/").pop()}
              </div>
            )}
          </div>
        ))}
    </div>
  )
}
