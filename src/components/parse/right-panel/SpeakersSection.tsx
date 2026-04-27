import { Check, Plus, X } from 'lucide-react';

import type { SpeakersSectionProps } from './types';

export function SpeakersSection({
  currentMode,
  selectedSpeakers,
  speakers,
  speakerPicker,
  onSpeakerSelect,
  onAddSpeaker,
  onToggleSpeaker,
}: SpeakersSectionProps) {
  return (
    <div className="border-b border-slate-100 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Speakers {currentMode === 'annotate' && <span className="ml-1 rounded bg-indigo-50 px-1 py-0.5 font-mono text-[8px] text-indigo-600">SINGLE</span>}
        </h4>
        <span className="text-[10px] text-slate-400">
          {currentMode === 'annotate' ? '1' : selectedSpeakers.length} / {speakers.length}
        </span>
      </div>
      <div className="mb-2 flex gap-1">
        <select
          value={currentMode === 'annotate' ? (selectedSpeakers[0] ?? '') : (speakerPicker ?? '')}
          onChange={(event) => onSpeakerSelect(event.target.value)}
          className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 focus:border-indigo-300 focus:outline-none"
        >
          {speakers.map((speaker) => <option key={speaker}>{speaker}</option>)}
        </select>
        {currentMode === 'compare' && (
          <button
            onClick={onAddSpeaker}
            data-testid="add-speaker-button"
            aria-label="Add speaker"
            className="grid h-6 w-6 place-items-center rounded-md bg-slate-900 text-white hover:bg-slate-700"
          >
            <Plus className="h-3 w-3" />
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1">
        {speakers.map((speaker) => {
          const active = currentMode === 'annotate' ? selectedSpeakers[0] === speaker : selectedSpeakers.includes(speaker);
          return (
            <button
              key={speaker}
              onClick={() => onToggleSpeaker(speaker)}
              className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[10px] transition ${active ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200' : 'bg-slate-50 text-slate-400 ring-1 ring-slate-100 hover:text-slate-600'}`}
            >
              {speaker}
              {active && currentMode === 'compare' && <X className="h-2.5 w-2.5" />}
              {active && currentMode === 'annotate' && <Check className="h-2.5 w-2.5" />}
            </button>
          );
        })}
      </div>
      {currentMode === 'annotate' && (
        <p className="mt-2 text-[10px] leading-snug text-slate-400">
          Concept list scoped to <span className="font-mono text-slate-600">{selectedSpeakers[0]}</span>'s dataset.
        </p>
      )}
    </div>
  );
}
