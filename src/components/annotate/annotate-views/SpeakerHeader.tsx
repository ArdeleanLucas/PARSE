import type { SurveySettingsMap } from "../../../api/types";
import { defaultSurveySettings, SURVEY_CHIP_CLASSES, surveyLabelFor } from "../../../lib/surveyOverlap";
import type { Concept } from "./types";

interface SpeakerHeaderProps {
  annotated: boolean;
  complete: boolean;
  concept: Concept;
  speaker: string;
  totalConcepts: number;
  surveyLabel?: string;
  surveySourceItem?: string;
  surveyChoices?: string[];
  resolvedSurveyId?: string;
  availableSurveys?: Record<string, string>;
  surveySettings?: SurveySettingsMap;
  surveyColorCodingEnabled?: boolean;
  activeSpeaker?: string;
  conceptSurveyKey?: string;
  onSurveyChoiceChange?: (speaker: string, conceptKey: string, surveyId: string) => void;
  onPrev: () => void;
  onNext: () => void;
}

export function SpeakerHeader({
  annotated,
  complete,
  concept,
  speaker,
  totalConcepts,
  surveyLabel,
  surveySourceItem,
  surveyChoices,
  resolvedSurveyId,
  availableSurveys,
  surveySettings,
  surveyColorCodingEnabled = false,
  activeSpeaker,
  conceptSurveyKey,
  onSurveyChoiceChange,
  onPrev,
  onNext,
}: SpeakerHeaderProps) {
  const settings = surveySettings ?? {};
  return (
    <section className="px-8 pt-6">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-center gap-3">
          <button
            onClick={onPrev}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
          >
            <span>←</span>
            <span>Prev</span>
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
              Concept <span className="font-mono">#{concept.id}</span> <span>·</span> {concept.id} of {totalConcepts}
            </div>
            <div className="mt-0.5 flex items-center gap-3">
              <h1 className="text-[32px] font-semibold tracking-tight text-slate-900">{concept.name}</h1>
              <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-slate-700">
                {speaker}
              </span>
              {complete ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700 ring-1 ring-teal-200">
                  Complete
                </span>
              ) : annotated ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                  Annotated
                </span>
              ) : null}
            </div>
            <div className="mt-1 flex items-center gap-1 font-mono text-[11px] text-slate-400">
              <span className="text-[9px] uppercase tracking-wider text-slate-400">Source</span>
              <span className="text-slate-500">{speaker}.wav</span>
            </div>
            {surveyChoices && surveyChoices.length > 1 && activeSpeaker && conceptSurveyKey && onSurveyChoiceChange ? (
              <div className="mt-1 flex items-center gap-2" data-testid="annotate-survey-chip-row">
                <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono">Survey</span>
                <div className="flex flex-wrap gap-1">
                  {surveyChoices.map((surveyId) => {
                    const sourceItem = availableSurveys?.[surveyId] ?? '';
                    const label = surveyLabelFor(surveyId, settings);
                    const selected = resolvedSurveyId === surveyId;
                    const displayColor = (settings[surveyId] ?? defaultSurveySettings(surveyId)).display_color;
                    return (
                      <button
                        key={surveyId}
                        type="button"
                        aria-label={selected ? `Current survey ${label} ${sourceItem}` : `Switch ${concept.name} to ${label} ${sourceItem}`}
                        onClick={() => onSurveyChoiceChange(activeSpeaker, conceptSurveyKey, surveyId)}
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold font-mono transition ${
                          surveyColorCodingEnabled
                            ? (SURVEY_CHIP_CLASSES[displayColor] ?? SURVEY_CHIP_CLASSES.slate)
                            : (selected ? 'bg-slate-900 text-white ring-slate-900' : 'bg-white text-slate-500 ring-slate-200 hover:bg-slate-50')
                        } ${selected ? 'ring-2' : 'ring-1 opacity-60 hover:opacity-100'}`}
                      >
                        {label}&nbsp;<span className="font-normal opacity-80">{sourceItem}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : surveyLabel && surveySourceItem ? (
              <div className="mt-1 flex items-center gap-1 font-mono text-[11px] text-slate-400">
                <span className="text-[9px] uppercase tracking-wider text-slate-400">Survey</span>
                <span className="text-slate-600">{surveyLabel}</span>
                <span className="text-slate-400">{surveySourceItem}</span>
              </div>
            ) : null}
          </div>
          <button
            onClick={onNext}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
          >
            <span>Next</span>
            <span>→</span>
          </button>
        </div>
      </div>
    </section>
  );
}
