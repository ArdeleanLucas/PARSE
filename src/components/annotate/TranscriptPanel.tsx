import { useState, useRef, useMemo, useEffect, useCallback } from "react";
import { useUIStore } from "../../stores/uiStore";
import { usePlaybackStore } from "../../stores/playbackStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import type { AnnotationInterval } from "../../api/types";

interface TranscriptPanelProps {
  onSeek: (timeSec: number) => void;
}

const ROW_HEIGHT = 52;
const OVERSCAN = 4;
const MANUAL_SCROLL_GRACE_MS = 2500;

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

export function TranscriptPanel({ onSeek }: TranscriptPanelProps) {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const currentTime = usePlaybackStore((s) => s.currentTime);
  const record = useAnnotationStore((s) =>
    activeSpeaker ? (s.records[activeSpeaker] ?? null) : null,
  );

  const [query, setQuery] = useState("");
  const scrolledManuallyRef = useRef(false);
  const manualScrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(400);
  const viewportRef = useRef<HTMLDivElement>(null);

  const segments: AnnotationInterval[] = useMemo(
    () => record?.tiers?.ipa?.intervals ?? [],
    [record],
  );

  const normalizedQuery = useMemo(
    () => query.toLowerCase().trim().replace(/\s+/g, " "),
    [query],
  );

  const filteredSegments = useMemo(() => {
    if (!normalizedQuery) return segments;
    return segments.filter((seg) =>
      seg.text.toLowerCase().includes(normalizedQuery),
    );
  }, [segments, normalizedQuery]);

  // Active index: binary search for latest segment.start <= currentTime
  const activeIndex = useMemo(() => {
    if (segments.length === 0) return -1;
    let lo = 0;
    let hi = segments.length - 1;
    let result = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >>> 1;
      if (segments[mid].start <= currentTime) {
        result = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return result;
  }, [segments, currentTime]);

  // Auto-scroll to active segment
  useEffect(() => {
    if (activeIndex < 0 || scrolledManuallyRef.current) return;
    const vp = viewportRef.current;
    if (!vp) return;
    const targetTop = activeIndex * ROW_HEIGHT - vp.clientHeight / 2;
    vp.scrollTop = Math.max(0, targetTop);
  }, [activeIndex]);

  // Track viewport height on mount
  useEffect(() => {
    const vp = viewportRef.current;
    if (vp) setViewportHeight(vp.clientHeight);
  }, []);

  const handleScroll = useCallback(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    setScrollTop(vp.scrollTop);
    setViewportHeight(vp.clientHeight);

    scrolledManuallyRef.current = true;
    if (manualScrollTimerRef.current) clearTimeout(manualScrollTimerRef.current);
    manualScrollTimerRef.current = setTimeout(() => {
      scrolledManuallyRef.current = false;
    }, MANUAL_SCROLL_GRACE_MS);
  }, []);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (manualScrollTimerRef.current) clearTimeout(manualScrollTimerRef.current);
    };
  }, []);

  const displaySegments = filteredSegments;
  const totalHeight = displaySegments.length * ROW_HEIGHT;

  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const endIdx = Math.min(
    displaySegments.length - 1,
    Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + OVERSCAN,
  );

  // Build a set of original indices for filtered segments to check active state
  const filteredOriginalIndices = useMemo(() => {
    if (!normalizedQuery) return null;
    const map = new Map<AnnotationInterval, number>();
    segments.forEach((seg, i) => map.set(seg, i));
    return displaySegments.map((seg) => map.get(seg) ?? -1);
  }, [segments, displaySegments, normalizedQuery]);

  function highlightMatch(text: string): React.ReactNode {
    if (!normalizedQuery) return text;
    const lower = text.toLowerCase();
    const idx = lower.indexOf(normalizedQuery);
    if (idx === -1) return text;
    return (
      <>
        {text.slice(0, idx)}
        <strong>{text.slice(idx, idx + normalizedQuery.length)}</strong>
        {text.slice(idx + normalizedQuery.length)}
      </>
    );
  }

  const rows: React.ReactNode[] = [];
  for (let i = startIdx; i <= endIdx && i < displaySegments.length; i++) {
    const seg = displaySegments[i];
    const originalIdx = filteredOriginalIndices ? filteredOriginalIndices[i] : i;
    const isActive = originalIdx === activeIndex;

    rows.push(
      <div
        key={`${seg.start}-${i}`}
        data-testid="transcript-row"
        onClick={() => onSeek(seg.start)}
        style={{
          position: "absolute",
          top: i * ROW_HEIGHT,
          left: 0,
          right: 0,
          height: ROW_HEIGHT,
          display: "flex",
          alignItems: "center",
          padding: "0 12px",
          cursor: "pointer",
          fontFamily: "monospace",
          fontSize: 14,
          borderLeft: isActive ? "3px solid #3b82f6" : "3px solid transparent",
          backgroundColor: isActive ? "#f0f7ff" : "transparent",
          boxSizing: "border-box",
        }}
      >
        <span style={{ color: "#6b7280", marginRight: 12, flexShrink: 0 }}>
          {formatTime(seg.start)}
        </span>
        <span
          style={{
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {highlightMatch(seg.text)}
        </span>
      </div>,
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        fontFamily: "monospace",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <span style={{ fontWeight: 600 }}>Transcript</span>
        {activeSpeaker && (
          <span style={{ color: "#6b7280" }}>{activeSpeaker}</span>
        )}
        <span style={{ color: "#9ca3af", marginLeft: "auto" }}>
          {segments.length} segments
        </span>
      </div>

      {/* Search */}
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          gap: 8,
        }}
      >
        <input
          type="text"
          placeholder="Search segments..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search segments"
          style={{
            flex: 1,
            padding: "4px 8px",
            border: "1px solid #d1d5db",
            borderRadius: 4,
            fontFamily: "monospace",
            fontSize: 13,
          }}
        />
        {query && (
          <button
            onClick={() => setQuery("")}
            style={{
              padding: "4px 8px",
              border: "1px solid #d1d5db",
              borderRadius: 4,
              background: "#fff",
              cursor: "pointer",
              fontFamily: "monospace",
              fontSize: 13,
            }}
          >
            Clear
          </button>
        )}
      </div>

      {/* Virtualized list */}
      <div
        ref={viewportRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflow: "auto",
          position: "relative",
        }}
      >
        {displaySegments.length === 0 ? (
          <div
            style={{
              padding: 24,
              textAlign: "center",
              color: "#9ca3af",
            }}
          >
            No transcript segments
          </div>
        ) : (
          <div style={{ height: totalHeight, position: "relative" }}>{rows}</div>
        )}
      </div>
    </div>
  );
}
