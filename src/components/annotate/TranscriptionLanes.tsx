import { useEffect, useRef, useState } from "react";
import type WaveSurfer from "wavesurfer.js";
import { useAnnotationStore } from "../../stores/annotationStore";
import {
  useTranscriptionLanesStore,
  type LaneKind,
} from "../../stores/transcriptionLanesStore";
import type { AnnotationInterval, SttSegment } from "../../api/types";

interface TranscriptionLanesProps {
  speaker: string;
  wsRef: React.RefObject<WaveSurfer | null>;
  audioReady: boolean;
}

interface LaneStrip {
  kind: LaneKind;
  label: string;
  intervals: Array<{ start: number; end: number; text: string }>;
}

const LANE_LABELS: Record<LaneKind, string> = {
  stt: "STT",
  ipa: "IPA",
  ortho: "ORTHO",
};

/**
 * Stacked transcription lanes rendered directly below the WaveSurfer waveform.
 *
 * Each visible lane scrolls horizontally in lock-step with the waveform so
 * labelled intervals stay aligned with their corresponding audio. Per user
 * request: native interval grain, no re-bucketing — imported Praat/ELAN
 * boundaries round-trip losslessly.
 */
export function TranscriptionLanes({ speaker, wsRef, audioReady }: TranscriptionLanesProps) {
  const lanes = useTranscriptionLanesStore((s) => s.lanes);
  const sttByspeaker = useTranscriptionLanesStore((s) => s.sttByspeaker);
  const loadStt = useTranscriptionLanesStore((s) => s.loadStt);
  const record = useAnnotationStore((s) => (speaker ? s.records[speaker] ?? null : null));

  const [pxPerSec, setPxPerSec] = useState(0);
  const [duration, setDuration] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(0);
  const laneScrollRefs = useRef<Record<LaneKind, HTMLDivElement | null>>({
    stt: null,
    ipa: null,
    ortho: null,
  });

  useEffect(() => {
    if (speaker) void loadStt(speaker);
  }, [speaker, loadStt]);

  useEffect(() => {
    if (!audioReady) return;
    const ws = wsRef.current;
    if (!ws) return;

    const readState = () => {
      const opts = (ws as unknown as { options: { minPxPerSec?: number } }).options;
      setPxPerSec(opts?.minPxPerSec ?? 0);
      setDuration(ws.getDuration() ?? 0);
      try {
        const wrapper = ws.getWrapper();
        setScrollLeft(wrapper.scrollLeft ?? 0);
        setViewportWidth(wrapper.clientWidth ?? 0);
      } catch {
        /* wrapper not ready */
      }
    };

    readState();

    const onScroll = () => {
      try {
        const wrapper = ws.getWrapper();
        setScrollLeft(wrapper.scrollLeft ?? 0);
      } catch {
        /* ignore */
      }
    };
    const onZoom = () => readState();
    const onReady = () => readState();

    ws.on("scroll", onScroll);
    ws.on("zoom", onZoom);
    ws.on("ready", onReady);

    let wrapper: HTMLElement | null = null;
    try {
      wrapper = ws.getWrapper();
      wrapper?.addEventListener("scroll", onScroll, { passive: true });
    } catch {
      /* ignore */
    }

    const resizeObs = new ResizeObserver(() => readState());
    if (wrapper) resizeObs.observe(wrapper);

    return () => {
      ws.un("scroll", onScroll);
      ws.un("zoom", onZoom);
      ws.un("ready", onReady);
      wrapper?.removeEventListener("scroll", onScroll);
      resizeObs.disconnect();
    };
  }, [audioReady, wsRef, speaker]);

  // Keep each lane's horizontal scroll position synced with the waveform.
  useEffect(() => {
    for (const kind of Object.keys(laneScrollRefs.current) as LaneKind[]) {
      const el = laneScrollRefs.current[kind];
      if (el && Math.abs(el.scrollLeft - scrollLeft) > 0.5) {
        el.scrollLeft = scrollLeft;
      }
    }
  }, [scrollLeft]);

  const strips: LaneStrip[] = [];
  if (lanes.stt.visible) {
    const segs: SttSegment[] = sttByspeaker[speaker] ?? [];
    strips.push({
      kind: "stt",
      label: LANE_LABELS.stt,
      intervals: segs.map((s) => ({ start: s.start, end: s.end, text: s.text })),
    });
  }
  if (lanes.ipa.visible) {
    const ivs: AnnotationInterval[] = record?.tiers?.ipa?.intervals ?? [];
    strips.push({
      kind: "ipa",
      label: LANE_LABELS.ipa,
      intervals: ivs.filter((i) => i.text && i.text.trim().length > 0),
    });
  }
  if (lanes.ortho.visible) {
    const ivs: AnnotationInterval[] = record?.tiers?.ortho?.intervals ?? [];
    strips.push({
      kind: "ortho",
      label: LANE_LABELS.ortho,
      intervals: ivs.filter((i) => i.text && i.text.trim().length > 0),
    });
  }

  if (strips.length === 0 || !audioReady || pxPerSec <= 0 || duration <= 0) return null;

  const innerWidth = Math.max(viewportWidth, pxPerSec * duration);

  return (
    <div className="mt-1.5 space-y-1 px-5">
      {strips.map((strip) => {
        const color = lanes[strip.kind].color;
        return (
          <div key={strip.kind} className="relative flex items-stretch">
            <div
              className="flex w-10 shrink-0 items-center justify-center border-r border-slate-100 text-[9px] font-semibold uppercase tracking-wider"
              style={{ color }}
            >
              {strip.label}
            </div>
            <div
              ref={(el) => {
                laneScrollRefs.current[strip.kind] = el;
              }}
              className="relative flex-1 overflow-hidden"
              style={{ height: 26 }}
            >
              <div className="relative h-full" style={{ width: innerWidth }}>
                {strip.intervals.length === 0 ? (
                  <div
                    className="absolute inset-0 flex items-center pl-2 text-[10px] italic text-slate-300"
                    style={{ left: scrollLeft }}
                  >
                    No {strip.label} intervals for {speaker}
                  </div>
                ) : (
                  strip.intervals.map((iv, idx) => {
                    const left = iv.start * pxPerSec;
                    const width = Math.max(1, (iv.end - iv.start) * pxPerSec);
                    return (
                      <div
                        key={`${idx}-${iv.start}`}
                        className="absolute top-1 bottom-1 flex items-center overflow-hidden rounded px-1 text-[10px] font-medium"
                        style={{
                          left,
                          width,
                          backgroundColor: color + "22",
                          borderLeft: `2px solid ${color}`,
                          color: "#334155",
                        }}
                        title={`${iv.start.toFixed(3)}–${iv.end.toFixed(3)}s · ${iv.text}`}
                      >
                        <span className="truncate">{iv.text}</span>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
