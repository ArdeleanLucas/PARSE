import { useMemo, useState } from 'react';
import { Database, Pencil, RotateCcw, X } from 'lucide-react';

import type { Concept } from '../../../lib/speakerForm';
import {
  aggregateWorkspaceSurveys,
  defaultSurveySettings,
  resolveConceptSurvey,
  surveyChoiceKeysForConcept,
  surveyLabelFor,
} from '../../../lib/surveyOverlap';
import type { ConceptSurveyLinksByConcept, SpeakerSurveyChoices, SurveyOverlapPatch, SurveySettingsMap } from '../../../api/types';
import { CollapsibleSection } from './CollapsibleSection';

interface SurveyValuesSectionProps {
  activeConcept?: Concept | null;
  activeSpeaker?: string | null;
  workspaceConcepts?: Concept[];
  conceptSurveyLinks?: ConceptSurveyLinksByConcept;
  surveyColorCodingEnabled: boolean;
  surveySettings: SurveySettingsMap;
  speakerSurveyChoices: SpeakerSurveyChoices;
  onSurveyOverlapUpdate: (patch: SurveyOverlapPatch) => void;
}

const SURVEY_COLOR_PALETTE = [
  'indigo',
  'violet',
  'blue',
  'sky',
  'teal',
  'emerald',
  'amber',
  'orange',
  'rose',
  'pink',
  'slate',
] as const;

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
  workspaceConcepts = [],
  conceptSurveyLinks,
  surveyColorCodingEnabled,
  surveySettings,
  speakerSurveyChoices,
  onSurveyOverlapUpdate,
}: SurveyValuesSectionProps) {
  const [editingSurveyId, setEditingSurveyId] = useState<string | null>(null);
  const [draftLabel, setDraftLabel] = useState('');
  const conceptChoices = useMemo(() => activeConcept ? surveyChoiceKeysForConcept(activeConcept) : [], [activeConcept]);
  const workspaceChoices = useMemo(() => {
    const concepts = workspaceConcepts.length > 0 ? workspaceConcepts : (activeConcept ? [activeConcept] : []);
    return aggregateWorkspaceSurveys(concepts, surveySettings, conceptSurveyLinks);
  }, [activeConcept, conceptSurveyLinks, surveySettings, workspaceConcepts]);
  const resolved = activeConcept ? resolveConceptSurvey(activeConcept, activeSpeaker, speakerSurveyChoices, surveySettings) : { surveyId: '', sourceItem: '' };
  const hasWorkspaceSurveys = workspaceChoices.length > 0;
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
        [surveyId]: { ...existing, display_label: label.trim() || defaultSurveySettings(surveyId).display_label },
      },
    });
    setEditingSurveyId(null);
    setDraftLabel('');
  };

  const updateColor = (surveyId: string, displayColor: string) => {
    if (!surveyColorCodingEnabled) return;
    const existing = surveySettings[surveyId] ?? defaultSurveySettings(surveyId);
    onSurveyOverlapUpdate({
      surveys: {
        [surveyId]: { ...existing, display_color: displayColor },
      },
    });
  };

  const resetDefaults = () => {
    onSurveyOverlapUpdate({
      reset_surveys: true,
      reset_speaker_choices: true,
      color_coding_enabled: false,
    });
  };

  return (
    <CollapsibleSection
      title="Survey Values"
      icon={<Database className="h-3 w-3" />}
      meta={<span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">{workspaceChoices.length}</span>}
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px]">
          <span className="font-semibold text-slate-600">Color coding</span>
          <button
            type="button"
            data-testid="survey-color-coding-toggle"
            disabled={!hasWorkspaceSurveys}
            onClick={() => onSurveyOverlapUpdate({ color_coding_enabled: !surveyColorCodingEnabled })}
            className="rounded border border-slate-200 bg-white px-2 py-0.5 font-semibold text-slate-600 disabled:cursor-not-allowed disabled:opacity-45"
            title="Toggle survey color coding workspace-wide."
          >
            {surveyColorCodingEnabled ? 'On' : 'Off'}
          </button>
        </div>

        {workspaceChoices.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 px-2.5 py-2 text-[10px] text-slate-400">
            No survey values are attached to this workspace yet.
          </p>
        ) : (
          <>
            {activeConcept ? (
              <div className="rounded-md bg-slate-50 px-2.5 py-2 text-[10px] text-slate-500 space-y-0.5" data-testid="survey-current-summary">
                <div>
                  <span className="font-semibold text-slate-600">Active survey</span>
                  <span className="ml-1 font-mono text-slate-700">{surveyLabelFor(resolved.surveyId, surveySettings) || '—'}</span>
                </div>
                {resolved.sourceItem ? (
                  <div>
                    <span className="font-semibold text-slate-600">Source item</span>
                    <span className="ml-1 font-mono text-slate-700">{resolved.sourceItem}</span>
                  </div>
                ) : null}
              </div>
            ) : null}

            {activeConcept && conceptChoices.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {conceptChoices.map((surveyId) => {
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
            ) : null}

            <div className="space-y-1.5">
              {workspaceChoices.map((surveyId) => {
                const label = surveyLabelFor(surveyId, surveySettings);
                const editing = editingSurveyId === surveyId;
                const displayColor = (surveySettings[surveyId] ?? defaultSurveySettings(surveyId)).display_color;
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
                      <div className="space-y-1.5">
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
                        {!surveyColorCodingEnabled ? <p className="text-[9px] text-slate-400">Turn on color-coding to apply.</p> : null}
                        <div className={`grid grid-cols-6 gap-1 ${surveyColorCodingEnabled ? '' : 'opacity-40'}`}>
                          {SURVEY_COLOR_PALETTE.map((color) => (
                            <button
                              key={color}
                              type="button"
                              aria-label={`Set ${label} color to ${color}`}
                              title={color}
                              disabled={!surveyColorCodingEnabled}
                              onClick={() => updateColor(surveyId, color)}
                              className={`h-5 rounded-full ring-1 disabled:cursor-not-allowed ${colorClass[color]} ${displayColor === color ? 'outline outline-2 outline-offset-1 outline-slate-400' : ''}`}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex flex-col gap-1.5 border-t border-slate-100 pt-2">
              <button
                type="button"
                aria-label="Reset survey display defaults"
                onClick={resetDefaults}
                className="inline-flex items-center gap-1 text-left text-[10px] font-semibold text-slate-500 hover:text-slate-700"
              >
                <RotateCcw className="h-3 w-3" />
                Reset to defaults
              </button>
              <button
                type="button"
                aria-label="Add survey placeholder"
                disabled
                title="Future surveys (e.g. WALS, SSWL) will appear here."
                className="rounded-md border border-dashed border-slate-200 px-2 py-1.5 text-[10px] font-medium text-slate-400 disabled:cursor-not-allowed"
              >
                + Add survey
              </button>
            </div>
          </>
        )}
      </div>
    </CollapsibleSection>
  );
}
