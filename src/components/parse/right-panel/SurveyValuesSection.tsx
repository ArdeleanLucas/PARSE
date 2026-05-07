import { useMemo, useState } from 'react';
import { Database, Pencil, X } from 'lucide-react';

import type { Concept } from '../../../lib/speakerForm';
import {
  defaultSurveySettings,
  resolveConceptSurvey,
  surveyChoiceKeysForConcept,
  surveyLabelFor,
} from '../../../lib/surveyOverlap';
import type { SpeakerSurveyChoices, SurveyOverlapPatch, SurveySettingsMap } from '../../../api/types';
import { CollapsibleSection } from './CollapsibleSection';

interface SurveyValuesSectionProps {
  activeConcept?: Concept | null;
  activeSpeaker?: string | null;
  surveyColorCodingEnabled: boolean;
  surveySettings: SurveySettingsMap;
  speakerSurveyChoices: SpeakerSurveyChoices;
  onSurveyOverlapUpdate: (patch: SurveyOverlapPatch) => void;
}

const colorClass: Record<string, string> = {
  indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  blue: 'bg-blue-50 text-blue-700 ring-blue-200',
  sky: 'bg-sky-50 text-sky-700 ring-sky-200',
  teal: 'bg-teal-50 text-teal-700 ring-teal-200',
  emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200',
  orange: 'bg-orange-50 text-orange-700 ring-orange-200',
  rose: 'bg-rose-50 text-rose-700 ring-rose-200',
  pink: 'bg-pink-50 text-pink-700 ring-pink-200',
  slate: 'bg-slate-100 text-slate-600 ring-slate-200',
};

function chipClass(active: boolean, colorKey: string, colorCoding: boolean): string {
  if (active && colorCoding) return colorClass[colorKey] ?? colorClass.slate;
  if (active) return 'bg-slate-900 text-white ring-slate-900';
  return 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50';
}

export function SurveyValuesSection({
  activeConcept,
  activeSpeaker,
  surveyColorCodingEnabled,
  surveySettings,
  speakerSurveyChoices,
  onSurveyOverlapUpdate,
}: SurveyValuesSectionProps) {
  const [editingSurveyId, setEditingSurveyId] = useState<string | null>(null);
  const [draftLabel, setDraftLabel] = useState('');
  const choices = useMemo(() => activeConcept ? surveyChoiceKeysForConcept(activeConcept) : [], [activeConcept]);
  const resolved = activeConcept ? resolveConceptSurvey(activeConcept, activeSpeaker, speakerSurveyChoices, surveySettings) : { surveyId: '', sourceItem: '' };
  const hasOverlap = choices.length > 1;
  const conceptKey = activeConcept?.key ?? '';
  const speaker = activeSpeaker ?? '';

  const updateChoice = (surveyId: string) => {
    if (!speaker || !conceptKey) return;
    onSurveyOverlapUpdate({
      speaker_choices: {
        ...speakerSurveyChoices,
        [speaker]: {
          ...(speakerSurveyChoices[speaker] ?? {}),
          [conceptKey]: surveyId,
        },
      },
    });
  };

  const updateLabel = (surveyId: string, label: string) => {
    const existing = surveySettings[surveyId] ?? defaultSurveySettings(surveyId);
    onSurveyOverlapUpdate({
      surveys: {
        ...surveySettings,
        [surveyId]: { ...existing, display_label: label.trim() || defaultSurveySettings(surveyId).display_label },
      },
    });
    setEditingSurveyId(null);
    setDraftLabel('');
  };

  return (
    <CollapsibleSection
      title="Survey Values"
      icon={<Database className="h-3 w-3" />}
      meta={<span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">{choices.length}</span>}
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px]">
          <span className="font-semibold text-slate-600">Color coding</span>
          <button
            type="button"
            data-testid="survey-color-coding-toggle"
            disabled={!hasOverlap}
            onClick={() => onSurveyOverlapUpdate({ color_coding_enabled: !surveyColorCodingEnabled })}
            className="rounded border border-slate-200 bg-white px-2 py-0.5 font-semibold text-slate-600 disabled:cursor-not-allowed disabled:opacity-45"
            title={hasOverlap ? 'Toggle optional survey color coding' : 'Only one survey value is available for this concept'}
          >
            {surveyColorCodingEnabled ? 'On' : 'Off'}
          </button>
        </div>

        {!activeConcept || choices.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 px-2.5 py-2 text-[10px] text-slate-400">
            No survey values are attached to this concept yet.
          </p>
        ) : (
          <>
            <div className="rounded-md bg-slate-50 px-2.5 py-2 text-[10px] text-slate-500">
              <span className="font-semibold text-slate-600">
                Current survey <span className="ml-1 font-mono text-slate-700">{surveyLabelFor(resolved.surveyId, surveySettings)} {resolved.sourceItem}</span>
              </span>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {choices.map((surveyId) => {
                const sourceItem = activeConcept.surveys?.[surveyId] ?? '';
                const label = surveyLabelFor(surveyId, surveySettings);
                const displayColor = (surveySettings[surveyId] ?? defaultSurveySettings(surveyId)).display_color;
                const active = resolved.surveyId === surveyId;
                return (
                  <button
                    key={surveyId}
                    type="button"
                    aria-label={active ? `Current survey ${label} ${sourceItem}` : `Switch ${activeConcept.name} to ${label} ${sourceItem}`}
                    onClick={() => updateChoice(surveyId)}
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ${chipClass(active, displayColor, surveyColorCodingEnabled)}`}
                  >
                    {label} <span className="font-mono">{sourceItem}</span>
                  </button>
                );
              })}
            </div>

            <div className="space-y-1.5">
              {choices.map((surveyId) => {
                const label = surveyLabelFor(surveyId, surveySettings);
                const editing = editingSurveyId === surveyId;
                return (
                  <div key={surveyId} className="rounded-md border border-slate-200 bg-white px-2 py-1.5">
                    {editing ? (
                      <div className="space-y-1.5">
                        <label className="sr-only" htmlFor={`survey-label-${surveyId}`}>Survey label for {surveyId}</label>
                        <input
                          id={`survey-label-${surveyId}`}
                          aria-label={`Survey label for ${surveyId}`}
                          value={draftLabel}
                          onChange={(event) => setDraftLabel(event.target.value)}
                          className="w-full rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-700 outline-none focus:border-indigo-300"
                        />
                        <div className="flex gap-1.5">
                          <button
                            type="button"
                            aria-label={`Save survey label ${surveyId}`}
                            onClick={() => updateLabel(surveyId, draftLabel)}
                            className="flex-1 rounded bg-indigo-600 px-2 py-1 text-[10px] font-semibold text-white"
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            aria-label={`Cancel survey label ${surveyId}`}
                            onClick={() => { setEditingSurveyId(null); setDraftLabel(''); }}
                            className="rounded border border-slate-200 px-2 py-1 text-[10px] font-semibold text-slate-600"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-slate-700">{label}</span>
                        <span className="font-mono text-[9px] text-slate-400">{surveyId}</span>
                        <button
                          type="button"
                          aria-label={`Edit survey label ${label}`}
                          onClick={() => { setEditingSurveyId(surveyId); setDraftLabel(label); }}
                          className="rounded border border-slate-200 p-1 text-slate-500 hover:bg-slate-50"
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </CollapsibleSection>
  );
}
