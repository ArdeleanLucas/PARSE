import { LaneColorPicker } from './LaneColorPicker';
import { useTranscriptionLanesStore, type LaneKind } from '../../stores/transcriptionLanesStore';

const LANE_ORDER: LaneKind[] = ['ipa_phone', 'ipa', 'stt', 'ortho', 'stt_words', 'boundaries'];
const LANE_DISPLAY: Record<LaneKind, { label: string; hint: string }> = {
  ipa_phone: { label: 'Phones tier', hint: 'Phone-level IPA' },
  ipa: { label: 'IPA tier', hint: 'Word/lexeme IPA' },
  stt: { label: 'STT segments', hint: 'Coarse transcript' },
  ortho: { label: 'Ortho tier', hint: 'Orthographic' },
  stt_words: { label: 'Words (Tier 1)', hint: 'Raw faster-whisper word boundaries' },
  boundaries: { label: 'Boundaries (Tier 2)', hint: 'Forced-aligned edges; colored by Tier 1 ↔ Tier 2 shift' },
};

export function TranscriptionLanesControls() {
  const lanes = useTranscriptionLanesStore((s) => s.lanes);
  const toggleLane = useTranscriptionLanesStore((s) => s.toggleLane);
  const setLaneColor = useTranscriptionLanesStore((s) => s.setLaneColor);

  return (
    <div className="mb-3 rounded-md bg-slate-50 p-2">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Transcription lanes
      </div>
      <div className="space-y-1">
        {LANE_ORDER.map((kind) => {
          const cfg = lanes[kind];
          const { label, hint } = LANE_DISPLAY[kind];
          return (
            <div key={kind} className="flex items-center gap-2 rounded-md px-1 py-1 hover:bg-white">
              <input
                id={`lane-toggle-${kind}`}
                type="checkbox"
                checked={cfg.visible}
                onChange={() => toggleLane(kind)}
                className="h-3.5 w-3.5 cursor-pointer rounded border-slate-300 text-indigo-600 focus:ring-indigo-400"
              />
              <LaneColorPicker
                value={cfg.color}
                onChange={(c) => setLaneColor(kind, c)}
                ariaLabel={`Color for ${label}`}
              />
              <label htmlFor={`lane-toggle-${kind}`} className="flex-1 min-w-0 cursor-pointer">
                <div className="text-[11px] font-medium text-slate-700 truncate">{label}</div>
                <div className="text-[9px] text-slate-400 truncate">{hint}</div>
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}
