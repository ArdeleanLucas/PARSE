import { useState, useEffect } from "react"
import { useConfigStore } from "../../stores/configStore"
import { useUIStore } from "../../stores/uiStore"

export interface OnboardingFlowProps {
  onComplete: () => void
}

export function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const config = useConfigStore((s) => s.config)
  const load = useConfigStore((s) => s.load)
  const loading = useConfigStore((s) => s.loading)
  const [currentStep, setCurrentStep] = useState(0)
  const [selectedSpeaker, setSelectedSpeaker] = useState("")

  useEffect(() => {
    load().catch(console.error)
  }, [load])

  const projectName = config?.project_name ?? "PARSE Project"
  const languageCode = config?.language_code ?? "unknown"
  const speakers = config?.speakers ?? []

  // Step 3 (Done): auto-call onComplete after 1s
  useEffect(() => {
    if (currentStep !== 3) return
    const timer = setTimeout(() => {
      useUIStore.setState({
        onboardingComplete: true,
        activeSpeaker: selectedSpeaker,
      })
      onComplete()
    }, 1000)
    return () => clearTimeout(timer)
  }, [currentStep, selectedSpeaker, onComplete])

  const containerStyle: React.CSSProperties = {
    position: "fixed",
    inset: 0,
    zIndex: 10000,
    background: "rgba(15, 23, 42, 0.6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "system-ui, -apple-system, sans-serif",
  }

  const cardStyle: React.CSSProperties = {
    background: "#fff",
    borderRadius: 12,
    padding: 32,
    width: 480,
    maxHeight: "85vh",
    overflowY: "auto",
    boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
    color: "#0f172a",
  }

  const titleStyle: React.CSSProperties = {
    fontSize: "1.25rem",
    fontWeight: 700,
    margin: "0 0 20px 0",
  }

  const btnStyle: React.CSSProperties = {
    padding: "8px 18px",
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 500,
    cursor: "pointer",
    border: "1px solid #6366f1",
    background: "#6366f1",
    color: "#fff",
  }

  const disabledBtnStyle: React.CSSProperties = {
    ...btnStyle,
    opacity: 0.5,
    cursor: "not-allowed",
  }

  const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: 13,
    fontWeight: 500,
    color: "#374151",
    marginBottom: 4,
  }

  const selectStyle: React.CSSProperties = {
    width: "100%",
    padding: "8px 10px",
    border: "1px solid #cbd5e1",
    borderRadius: 8,
    fontSize: 14,
    boxSizing: "border-box",
  }

  if (currentStep === 0) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>
            Step 1 of 4
          </div>
          <h2 style={titleStyle}>Welcome</h2>
          <p style={{ fontSize: 14, color: "#374151", marginBottom: 8 }}>
            PARSE — Phonetic Analysis and Review Source Explorer
          </p>
          <p style={{ fontSize: 14, color: "#374151", marginBottom: 20 }}>
            Project: {projectName}
          </p>
          <button
            style={btnStyle}
            onClick={() => setCurrentStep(1)}
          >
            Next
          </button>
        </div>
      </div>
    )
  }

  if (currentStep === 1) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>
            Step 2 of 4
          </div>
          <h2 style={titleStyle}>Config check</h2>
          <p style={{ fontSize: 14, color: "#374151", marginBottom: 8 }}>
            Language code: {languageCode}
          </p>
          <p style={{ fontSize: 14, color: "#374151", marginBottom: 20 }}>
            Speakers: {speakers.length}
          </p>
          <button
            style={btnStyle}
            onClick={() => setCurrentStep(2)}
          >
            Next
          </button>
        </div>
      </div>
    )
  }

  if (currentStep === 2) {
    const canStart = selectedSpeaker !== ""
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>
            Step 3 of 4
          </div>
          <h2 style={titleStyle}>Speaker selection</h2>
          {loading && (
            <p style={{ fontSize: 13, color: "#64748b", marginBottom: 8 }}>
              Loading speakers...
            </p>
          )}
          {!loading && speakers.length === 0 && (
            <p style={{ fontSize: 13, color: "#ef4444", marginBottom: 8 }}>
              No speakers found. Check that source_index.json exists and contains speakers.
            </p>
          )}
          <label style={labelStyle}>Select a speaker</label>
          <select
            style={selectStyle}
            value={selectedSpeaker}
            onChange={(e) => setSelectedSpeaker(e.target.value)}
          >
            <option value="">-- Select speaker --</option>
            {speakers.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <div style={{ marginTop: 20 }}>
            <button
              style={canStart ? btnStyle : disabledBtnStyle}
              disabled={!canStart}
              onClick={() => setCurrentStep(3)}
            >
              Start annotating
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Step 3 — Done
  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>
          Step 4 of 4
        </div>
        <h2 style={titleStyle}>Ready.</h2>
      </div>
    </div>
  )
}
