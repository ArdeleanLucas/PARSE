import { Check, Plus, Users, X } from 'lucide-react';

import type { SpeakersSectionProps } from './types';
import { CollapsibleSection } from './CollapsibleSection';

export function SpeakersSection({
  currentMode,
  selectedSpeakers,
  speakers,
  speakerPicker,
  onSpeakerSelect,
  onAddSpeaker,
  onToggleSpeaker,
  onSelectAllSpeakers,
  onClearSpeakers,
}: SpeakersSectionProps) {
  const bulkDisabled = currentMode === 'annotate';
  const bulkButtonClass = bulkDisabled
    ? 'cursor-not-allowed opacity-40'
    : 'hover:bg-slate-200';

  return (
    <CollapsibleSection
      title={currentMode === 'annotate' ? 'Speakers SINGLE' : 'Speakers'}
      icon={<Users className="h-3 w-3" />}
      meta={<span className="text-[10px] text-slate-400">{currentMode === 'annotate' ? '1' : selectedSpeakers.length} / {speakers.length}</span>}
    >
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
      <div className="mb-2 flex gap-1">
        <button
          type="button"
          data-testid="speakers-select-all"
          aria-label="Select all speakers"
          aria-disabled={bulkDisabled ? 'true' : undefined}
          disabled={bulkDisabled}
          onClick={() => {
            if (!bulkDisabled) onSelectAllSpeakers();
          }}
          className={`rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600 ring-1 ring-slate-200 ${bulkButtonClass}`}
        >
          Select all
        </button>
        <button
          type="button"
          data-testid="speakers-clear"
          aria-label="Clear speaker selection"
          aria-disabled={bulkDisabled ? 'true' : undefined}
          disabled={bulkDisabled}
          onClick={() => {
            if (!bulkDisabled) onClearSpeakers();
          }}
          className={`rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600 ring-1 ring-slate-200 ${bulkButtonClass}`}
        >
          Clear
        </button>
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
    </CollapsibleSection>
  );
}
