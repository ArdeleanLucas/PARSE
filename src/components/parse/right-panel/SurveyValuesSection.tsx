import { useMemo, useState } from 'react';
import { Database, Link2, Pencil, RotateCcw, X } from 'lucide-react';

import type { Concept } from '../../../lib/speakerForm';
import {
  aggregateWorkspaceSurveys,
  defaultSurveySettings,
  normalizeSurveyId,
  resolveConceptSurvey,
  SURVEY_CHIP_CLASSES,
  surveyChoiceKeysForConcept,
  surveyLabelFor,
} from '../../../lib/surveyOverlap';
import { resolveSurveyLinksForSpeaker, surveyRowIdsForConcept } from '../../../lib/surveyLinksForSpeaker';
import { relinkConceptsByGloss } from '../../../api/client';
import type {
  ConceptSurveyLinksByConcept,
  RelinkByGlossRequest,
  RelinkByGlossResponse,
  SpeakerConceptSurveyLinks,
  SpeakerSurveyChoices,
  SurveyOverlapPatch,
  SurveySettingsMap,
} from '../../../api/types';
import { CollapsibleSection } from './CollapsibleSection';
import { RelinkReviewDialog } from './RelinkReviewDialog';

interface SurveyValuesSectionProps {
  activeConcept?: Concept | null;
  activeSpeaker?: string | null;
  workspaceConcepts?: Concept[];
  conceptSurveyLinks?: ConceptSurveyLinksByConcept;
  speakerConceptSurveyLinks?: SpeakerConceptSurveyLinks;
  surveyColorCodingEnabled: boolean;
  surveySettings: SurveySettingsMap;
  speakerSurveyChoices: SpeakerSurveyChoices;
  onSurveyOverlapUpdate: (patch: SurveyOverlapPatch) => void;
  onRelinkApplied?: () => void | Promise<void>;
}

const SURVEY_COLOR_PALETTE = [
  'indigo',
  'emerald',
  'amber',
  'rose',
  'slate',
] as const;

function chipClass(active: boolean, colorKey: string, colorCoding: boolean): string {
  if (active && colorCoding) return SURVEY_CHIP_CLASSES[colorKey] ?? SURVEY_CHIP_CLASSES.slate;
  if (active) return 'bg-slate-900 text-white ring-slate-900';
  return 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50';
}

export function SurveyValuesSection({
  activeConcept,
  activeSpeaker,
  workspaceConcepts = [],
  conceptSurveyLinks,
  speakerConceptSurveyLinks,
  surveyColorCodingEnabled,
  surveySettings,
  speakerSurveyChoices,
  onSurveyOverlapUpdate,
  onRelinkApplied,
}: SurveyValuesSectionProps) {
  const [editingSurveyId, setEditingSurveyId] = useState<string | null>(null);
  const [draftLabel, setDraftLabel] = useState('');
  const [relinkStatus, setRelinkStatus] = useState<string | null>(null);
  const [relinkReview, setRelinkReview] = useState<RelinkByGlossResponse | null>(null);
  const workspaceChoices = useMemo(() => {
    const concepts = workspaceConcepts.length > 0 ? workspaceConcepts : (activeConcept ? [activeConcept] : []);
    return aggregateWorkspaceSurveys(concepts, surveySettings, conceptSurveyLinks);
  }, [activeConcept, conceptSurveyLinks, surveySettings, workspaceConcepts]);
  const speakerBuckets = useMemo(() => {
    if (!activeConcept) return [];
    const rowIds = surveyRowIdsForConcept(activeConcept);
    const fallbackByRowId = Object.fromEntries(rowIds.map((rowId) => [rowId, conceptSurveyLinks?.[rowId] ?? activeConcept.surveys ?? {}]));
    return resolveSurveyLinksForSpeaker(rowIds, activeSpeaker, fallbackByRowId, speakerConceptSurveyLinks);
  }, [activeConcept, activeSpeaker, conceptSurveyLinks, speakerConceptSurveyLinks]);
  const hasSpeakerOverride = useMemo(() => {
    if (!activeConcept || !activeSpeaker) return false;
    return surveyRowIdsForConcept(activeConcept).some((rowId) => {
      const links = speakerConceptSurveyLinks?.[activeSpeaker]?.[rowId];
      return Object.entries(links ?? {}).some(([surveyId, sourceItem]) => normalizeSurveyId(surveyId) && String(sourceItem ?? '').trim());
    });
  }, [activeConcept, activeSpeaker, speakerConceptSurveyLinks]);
  const bucketSourceItemBySurveyId = useMemo(
    () => Object.fromEntries(speakerBuckets.map((bucket) => [bucket.surveyId, bucket.sourceItem])),
    [speakerBuckets],
  );
  const conceptChoices = useMemo(() => {
    if (speakerBuckets.length > 0) return speakerBuckets.map((bucket) => bucket.surveyId);
    return activeConcept ? surveyChoiceKeysForConcept(activeConcept) : [];
  }, [activeConcept, speakerBuckets]);
  const resolved = useMemo<{ surveyId: string; sourceItem: string }>(() => {
    if (!activeConcept) return { surveyId: '', sourceItem: '' };
    if (speakerBuckets.length === 0) {
      return resolveConceptSurvey(activeConcept, activeSpeaker, speakerSurveyChoices, surveySettings);
    }
    const choice = activeSpeaker ? normalizeSurveyId(speakerSurveyChoices?.[activeSpeaker]?.[activeConcept.key] ?? '') : '';
    const choiceMatch = choice ? speakerBuckets.find((bucket) => bucket.surveyId === choice) : undefined;
    const sourceSurvey = hasSpeakerOverride ? '' : normalizeSurveyId(activeConcept.sourceSurvey);
    const sourceMatch = sourceSurvey ? speakerBuckets.find((bucket) => bucket.surveyId === sourceSurvey) : undefined;
    const bucket = choiceMatch ?? sourceMatch ?? speakerBuckets[0];
    return { surveyId: bucket.surveyId, sourceItem: bucket.sourceItem };
  }, [activeConcept, activeSpeaker, hasSpeakerOverride, speakerBuckets, speakerSurveyChoices, surveySettings]);
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

  const summarizeAppliedRelink = (acceptedGroups: NonNullable<RelinkByGlossRequest['accepted_groups']>, response: RelinkByGlossResponse): string => {
    const rewrites = response.annotation_rewrites ?? {};
    const rewriteTotal = Object.values(rewrites).reduce((sum, count) => sum + count, 0);
    const fileCount = Object.keys(rewrites).length;
    const conceptCount = acceptedGroups.length;
    return `Reconciled ${conceptCount} concepts; rewrote ${rewriteTotal} annotation occurrences across ${fileCount} files.`;
  };

  const applyRelinkReview = async (acceptedGroups: NonNullable<RelinkByGlossRequest['accepted_groups']>) => {
    setRelinkStatus('Applying concept reconciliation…');
    try {
      const applied = await relinkConceptsByGloss({
        apply: true,
        accepted_groups: acceptedGroups,
      });
      setRelinkReview(null);
      await onRelinkApplied?.();
      setRelinkStatus(summarizeAppliedRelink(acceptedGroups, applied));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setRelinkStatus(message);
    }
  };

  const reconcileConcepts = async () => {
    setRelinkStatus('Checking concepts…');
    try {
      const dryRun = await relinkConceptsByGloss();
      if (!dryRun.groups.length && !dryRun.fuzzy_candidates.length) {
        setRelinkStatus('No strict cross-survey merges found.');
        return;
      }
      setRelinkReview(dryRun);
      setRelinkStatus(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setRelinkStatus(message);
    }
  };

  const resetDefaults = () => {
    onSurveyOverlapUpdate({
      reset_surveys: true,
      reset_speaker_choices: true,
      color_coding_enabled: false,
    });
  };

  return (
    <>
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
            data-toggle-state={surveyColorCodingEnabled ? 'on' : 'off'}
            data-toggle-style="standalone"
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
                const sourceItem = bucketSourceItemBySurveyId[surveyId] ?? activeConcept.surveys?.[surveyId] ?? '';
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
                        <div className={`grid grid-cols-5 gap-1 ${surveyColorCodingEnabled ? '' : 'opacity-40'}`}>
                          {SURVEY_COLOR_PALETTE.map((color) => (
                            <button
                              key={color}
                              type="button"
                              aria-label={`Set ${label} color to ${color}`}
                              title={color}
                              disabled={!surveyColorCodingEnabled}
                              onClick={() => updateColor(surveyId, color)}
                              className={`h-5 rounded-full ring-1 disabled:cursor-not-allowed ${SURVEY_CHIP_CLASSES[color] ?? SURVEY_CHIP_CLASSES.slate} ${displayColor === color ? 'outline outline-2 outline-offset-1 outline-slate-400' : ''}`}
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
                aria-label="Reconcile concepts across surveys"
                onClick={() => { void reconcileConcepts(); }}
                className="inline-flex items-center gap-1 text-left text-[10px] font-semibold text-indigo-600 hover:text-indigo-800"
              >
                <Link2 className="h-3 w-3" />
                Reconcile concepts across surveys
              </button>
              {relinkStatus ? <div className="rounded bg-slate-50 px-2 py-1 text-[10px] text-slate-500">{relinkStatus}</div> : null}
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
      {relinkReview ? (
        <RelinkReviewDialog
          response={relinkReview}
          onApply={(acceptedGroups) => { void applyRelinkReview(acceptedGroups); }}
          onCancel={() => {
            setRelinkReview(null);
            setRelinkStatus('Reconciliation cancelled.');
          }}
        />
      ) : null}
    </>
  );
}
