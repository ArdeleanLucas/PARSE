import { useState, useEffect } from "react"
import { useConfigStore } from "../../stores/configStore"
import { useUIStore } from "../../stores/uiStore"

export interface OnboardingFlowProps {
  onComplete: () => void
}

export function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const config = useConfigStore((s) => s.config)
  const load = useConfigStore((s) => s.load)
  const [currentStep, setCurrentStep] = useState(0)
  useEffect(() => {
    load().catch(console.error)
  }, [load])

  const projectName = config?.project_name ?? "PARSE Project"
  const languageCode = config?.language_code ?? "unknown"

  // Step 3 (Done): auto-call onComplete after 1s
  useEffect(() => {
    if (currentStep !== 3) return
    const timer = setTimeout(() => {
      useUIStore.setState({
        onboardingComplete: true,
        activeSpeaker: null,
        annotatePanel: "chat",
      })
      onComplete()
    }, 1000)
    return () => clearTimeout(timer)
  }, [currentStep, onComplete])

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
            Ready to import speakers.
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
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>
            Step 3 of 4
          </div>
          <h2 style={titleStyle}>Import speaker data</h2>
          <p style={{ fontSize: 14, color: "#374151", marginBottom: 8 }}>
            Use the AI Assistant to import your first speaker dataset.
          </p>
          <p style={{ fontSize: 13, color: "#64748b", marginBottom: 20 }}>
            The assistant will guide you through selecting your audio files and CSV,
            one speaker at a time.
          </p>
          <button
            style={btnStyle}
            onClick={() => setCurrentStep(3)}
          >
            Open AI assistant
          </button>
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
        <h2 style={titleStyle}>Opening AI assistant…</h2>
      </div>
    </div>
  )
}
