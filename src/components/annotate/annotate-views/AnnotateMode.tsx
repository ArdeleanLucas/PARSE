import { useState, useRef } from "react";

import { TopBar } from "../../shared/TopBar";
import { Select } from "../../shared/Select";
import { Toast } from "../../shared/Toast";
import { AnnotationPanel } from "../AnnotationPanel";
import { ChatPanel } from "../ChatPanel";
import { OnboardingFlow } from "../OnboardingFlow";
import { RegionManager } from "../RegionManager";
import { SuggestionsPanel } from "../SuggestionsPanel";
import { TranscriptPanel } from "../TranscriptPanel";

import { formatPlayhead } from "./shared";
import { PANEL_TABS, RATE_OPTIONS } from "./types";
import { useAnnotateLifecycle } from "./useAnnotateLifecycle";

export function AnnotateMode() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [toast, setToast] = useState<string | null>(null);

  const {
    activeConcept,
    activeSpeaker,
    annotatePanel,
    canRedo,
    canUndo,
    currentTime,
    dirty,
    handleOnboardingComplete,
    handleRateChange,
    handleRedo,
    handleSeekWithRegion,
    handleSpeakerClick,
    handleUndo,
    handleZoomChange,
    loopEnabled,
    nextRedoLabel,
    nextUndoLabel,
    onboardingComplete,
    playbackDuration,
    playbackRate,
    setAnnotatePanel,
    speakers,
    toggleLoop,
    waveform,
    waveformContainerTestId,
    zoom,
  } = useAnnotateLifecycle(containerRef);

  if (!onboardingComplete) {
    return (
      <>
        <TopBar />
        <OnboardingFlow onComplete={handleOnboardingComplete} />
      </>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopBar />
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <aside
          style={{
            width: 180,
            borderRight: "1px solid #e5e7eb",
            overflowY: "auto",
            padding: "0.5rem",
          }}
        >
          <div
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "#6b7280",
              marginBottom: "0.5rem",
              fontFamily: "monospace",
            }}
          >
            Speakers
          </div>
          {speakers.map((speaker) => (
            <button
              key={speaker}
              onClick={() => handleSpeakerClick(speaker)}
              data-testid={`speaker-${speaker}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                width: "100%",
                padding: "0.375rem 0.5rem",
                border: "none",
                borderRadius: "0.25rem",
                background: speaker === activeSpeaker ? "#dbeafe" : "transparent",
                fontWeight: speaker === activeSpeaker ? 600 : 400,
                fontFamily: "monospace",
                fontSize: "0.8rem",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              {speaker}
              {dirty[speaker] && (
                <span
                  data-testid={`dirty-${speaker}`}
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "#f59e0b",
                    flexShrink: 0,
                  }}
                />
              )}
            </button>
          ))}
        </aside>

        <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div
            ref={containerRef}
            data-testid={waveformContainerTestId}
            style={{ height: 80, width: "100%", flexShrink: 0 }}
          />

          <RegionManager
            onSeek={handleSeekWithRegion}
            onAssigned={(speaker, conceptId, start, end) =>
              console.info("Assigned", speaker, conceptId, start, end)
            }
          />

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.5rem",
              flexShrink: 0,
            }}
          >
            <button onClick={() => waveform.skip(-5)}> -5s </button>
            <button onClick={() => waveform.playPause()}>Play/Pause</button>
            <button onClick={() => waveform.skip(5)}> +5s </button>
            <span
              aria-label="Playhead time"
              title="Current playhead / total duration"
              style={{
                fontFamily: "monospace",
                fontSize: "0.75rem",
                padding: "0.25rem 0.5rem",
                border: "1px solid #e2e8f0",
                borderRadius: "0.25rem",
                background: "#f8fafc",
                color: "#0f172a",
                whiteSpace: "nowrap",
                minWidth: 130,
                textAlign: "center",
              }}
            >
              <span style={{ fontWeight: 600 }}>{formatPlayhead(currentTime)}</span>
              <span style={{ color: "#94a3b8" }}> / {formatPlayhead(playbackDuration)}</span>
            </span>
            <button onClick={toggleLoop}>{loopEnabled ? "Looping" : "Loop"}</button>
            <button
              onClick={() => {
                const label = handleUndo();
                if (label) setToast(`Undid ${label}`);
              }}
              disabled={!canUndo}
              title={canUndo ? `Undo ${nextUndoLabel} (⌘Z)` : "Nothing to undo"}
              data-testid="undo-btn"
            >
              Undo
            </button>
            <button
              onClick={() => {
                const label = handleRedo();
                if (label) setToast(`Redid ${label}`);
              }}
              disabled={!canRedo}
              title={canRedo ? `Redo ${nextRedoLabel} (⇧⌘Z)` : "Nothing to redo"}
              data-testid="redo-btn"
            >
              Redo
            </button>
            <Select
              options={RATE_OPTIONS.map((option) => ({ ...option }))}
              value={String(playbackRate)}
              onChange={handleRateChange}
              style={{ width: 80 }}
            />
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.25rem",
                fontSize: "0.75rem",
                fontFamily: "monospace",
              }}
            >
              Zoom
              <input
                type="range"
                min={10}
                max={500}
                value={zoom}
                onChange={handleZoomChange}
              />
            </label>
          </div>
        </main>

        <aside
          style={{
            width: 340,
            borderLeft: "1px solid #e5e7eb",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              borderBottom: "1px solid #e5e7eb",
              flexShrink: 0,
            }}
          >
            {PANEL_TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setAnnotatePanel(tab)}
                data-testid={`tab-${tab}`}
                style={{
                  flex: 1,
                  padding: "0.375rem 0",
                  border: "none",
                  borderBottom:
                    annotatePanel === tab ? "2px solid #3b82f6" : "2px solid transparent",
                  background: "transparent",
                  fontFamily: "monospace",
                  fontSize: "0.7rem",
                  fontWeight: annotatePanel === tab ? 600 : 400,
                  cursor: "pointer",
                  textTransform: "capitalize",
                }}
              >
                {tab}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {annotatePanel === "annotation" && <AnnotationPanel onSeek={handleSeekWithRegion} />}
            {annotatePanel === "transcript" && <TranscriptPanel onSeek={waveform.seek} />}
            {annotatePanel === "suggestions" && (
              <SuggestionsPanel onSeek={handleSeekWithRegion} />
            )}
            {annotatePanel === "chat" && (
              <ChatPanel speaker={activeSpeaker} conceptId={activeConcept} />
            )}
          </div>
        </aside>
      </div>
      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}
