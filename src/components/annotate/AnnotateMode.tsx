import { useEffect, useRef, useCallback } from "react";
import { TopBar } from "../shared/TopBar";
import { Button } from "../shared/Button";
import { Select } from "../shared/Select";
import { OnboardingFlow } from "./OnboardingFlow";
import { RegionManager } from "./RegionManager";
import { AnnotationPanel } from "./AnnotationPanel";
import { TranscriptPanel } from "./TranscriptPanel";
import { SuggestionsPanel } from "./SuggestionsPanel";
import { ChatPanel } from "./ChatPanel";
import { useConfigStore } from "../../stores/configStore";
import { useUIStore } from "../../stores/uiStore";
import { usePlaybackStore } from "../../stores/playbackStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import { useWaveSurfer } from "../../hooks/useWaveSurfer";
import { useAnnotationSync } from "../../hooks/useAnnotationSync";

const PANEL_TABS = ["annotation", "transcript", "suggestions", "chat"] as const;

const RATE_OPTIONS = [
  { value: "0.5", label: "0.5x" },
  { value: "0.75", label: "0.75x" },
  { value: "1", label: "1.0x" },
  { value: "1.25", label: "1.25x" },
];

export function AnnotateMode() {
  const containerRef = useRef<HTMLDivElement>(null);

  // Stores
  const load = useConfigStore((s) => s.load);
  const speakers = useConfigStore((s) => s.config?.speakers ?? []);
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const activeConcept = useUIStore((s) => s.activeConcept);
  const annotatePanel = useUIStore((s) => s.annotatePanel);
  const onboardingComplete = useUIStore((s) => s.onboardingComplete);
  const setActiveSpeaker = useUIStore((s) => s.setActiveSpeaker);
  const setAnnotatePanel = useUIStore((s) => s.setAnnotatePanel);
  const setOnboardingComplete = useUIStore((s) => s.setOnboardingComplete);
  const setPlaybackSpeaker = usePlaybackStore((s) => s.setActiveSpeaker);
  const zoom = usePlaybackStore((s) => s.zoom);
  const setZoom = usePlaybackStore((s) => s.setZoom);
  const loopEnabled = usePlaybackStore((s) => s.loopEnabled);
  const toggleLoop = usePlaybackStore((s) => s.toggleLoop);
  const playbackRate = usePlaybackStore((s) => s.playbackRate);
  const setPlaybackRate = usePlaybackStore((s) => s.setPlaybackRate);
  // Subscribe to the playhead for the numeric readout in the controls bar.
  // The waveform has no built-in time display; annotators need to anchor
  // exact timestamps and eyeballing the scrub bar isn't precise enough.
  const currentTime = usePlaybackStore((s) => s.currentTime);
  const playbackDuration = usePlaybackStore((s) => s.duration);
  const dirty = useAnnotationStore((s) => s.dirty);
  const record = useAnnotationStore((s) =>
    activeSpeaker ? s.records[activeSpeaker] ?? null : null,
  );

  // Annotation sync
  useAnnotationSync();

  // Waveform URL comes from the loaded annotation's source_audio
  // (e.g. "audio/working/Fail02/foo.wav"), not a speaker-name stub.
  const sourceAudio = (record?.source_audio ?? record?.source_wav ?? "").replace(/\\/g, "/").replace(/^\/+/, "");
  const audioUrl = activeSpeaker && sourceAudio ? "/" + sourceAudio : "";
  const {
    playPause,
    seek,
    skip,
    addRegion,
    setZoom: wsSetZoom,
    setRate,
  } = useWaveSurfer({
    containerRef,
    audioUrl,
    peaksUrl: activeSpeaker ? `/peaks/${activeSpeaker}.json` : undefined,
    onTimeUpdate: (t) => usePlaybackStore.setState({ currentTime: t }),
    onReady: (d) => usePlaybackStore.setState({ duration: d }),
    onPlayStateChange: (p) => usePlaybackStore.setState({ isPlaying: p }),
    onRegionUpdate: (start, end) =>
      usePlaybackStore.setState({ selectedRegion: { start, end } }),
  });

  // Load config on mount
  useEffect(() => {
    load().catch(console.error);
  }, [load]);

  // Handlers
  const handleSpeakerClick = useCallback(
    (speaker: string) => {
      setActiveSpeaker(speaker);
      setPlaybackSpeaker(speaker);
    },
    [setActiveSpeaker, setPlaybackSpeaker],
  );

  const handleOnboardingComplete = useCallback(() => {
    setOnboardingComplete(true);
  }, [setOnboardingComplete]);

  const handleZoomChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = Number(e.target.value);
      setZoom(val);
      wsSetZoom(val);
    },
    [setZoom, wsSetZoom],
  );

  const handleRateChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const rate = Number(e.target.value);
      setPlaybackRate(rate);
      setRate(rate);
    },
    [setPlaybackRate, setRate],
  );

  const handleSeekWithRegion = useCallback(
    (t: number, create?: boolean, dur?: number) => {
      seek(t);
      if (create) addRegion(t, t + (dur ?? 3));
    },
    [seek, addRegion],
  );

  // Onboarding gate
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
        {/* Left — Speaker list */}
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
          {speakers.map((sp) => (
            <button
              key={sp}
              onClick={() => handleSpeakerClick(sp)}
              data-testid={`speaker-${sp}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                width: "100%",
                padding: "0.375rem 0.5rem",
                border: "none",
                borderRadius: "0.25rem",
                background: sp === activeSpeaker ? "#dbeafe" : "transparent",
                fontWeight: sp === activeSpeaker ? 600 : 400,
                fontFamily: "monospace",
                fontSize: "0.8rem",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              {sp}
              {dirty[sp] && (
                <span
                  data-testid={`dirty-${sp}`}
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

        {/* Center — Waveform + controls */}
        <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div
            ref={containerRef}
            data-testid="waveform-container"
            style={{ height: 80, width: "100%", flexShrink: 0 }}
          />

          {/* Region manager */}
          <RegionManager
            onSeek={handleSeekWithRegion}
            onAssigned={(sp, cid, s, e) =>
              console.info("Assigned", sp, cid, s, e)
            }
          />

          {/* Playback controls */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.5rem",
              flexShrink: 0,
            }}
          >
            <Button size="sm" onClick={() => skip(-5)}>
              -5s
            </Button>
            <Button variant="primary" size="sm" onClick={() => playPause()}>
              Play/Pause
            </Button>
            <Button size="sm" onClick={() => skip(5)}>
              +5s
            </Button>
            {/* Numeric playhead readout — m:ss.sss / m:ss.sss. */}
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
            <Button
              size="sm"
              variant={loopEnabled ? "primary" : "secondary"}
              onClick={toggleLoop}
            >
              Loop
            </Button>
            <Select
              options={RATE_OPTIONS}
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

        {/* Right — Panel tabs */}
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
            {annotatePanel === "transcript" && <TranscriptPanel onSeek={seek} />}
            {annotatePanel === "suggestions" && (
              <SuggestionsPanel onSeek={handleSeekWithRegion} />
            )}
            {annotatePanel === "chat" && (
              <ChatPanel speaker={activeSpeaker} conceptId={activeConcept} />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

/** Format seconds as "m:ss.sss" for the playhead readout. Handles NaN /
 * negative values (which can briefly appear before the waveform reports
 * its duration) by collapsing to "0:00.000". */
function formatPlayhead(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00.000";
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}
