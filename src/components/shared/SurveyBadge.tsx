import type { SurveySettingsMap } from '../../api/types';
import { SURVEY_BADGE_TEXT_CLASSES, surveyLabelFor } from '../../lib/surveyOverlap';

export interface SurveyBadgeProps {
  conceptId: string;
  conceptKey: string;
  conceptName: string;
  resolvedSurveyId: string;
  resolvedSourceItem: string;
  resolvedDisplayColor: string;
  availableSurveys: Record<string, string>;
  surveySettings: SurveySettingsMap;
  surveyColorCodingEnabled: boolean;
  activeSpeaker: string | null;
  parentActive: boolean;
  onCycle?: (next: { surveyId: string; sourceItem: string }) => void;
  className?: string;
}

export function SurveyBadge({
  conceptId,
  conceptName,
  resolvedSurveyId,
  resolvedSourceItem,
  resolvedDisplayColor,
  availableSurveys,
  surveySettings,
  surveyColorCodingEnabled,
  activeSpeaker,
  parentActive,
  onCycle,
  className = '',
}: SurveyBadgeProps) {
  const resolvedSurveyLabel = surveyLabelFor(resolvedSurveyId, surveySettings);
  const badge = resolvedSurveyId && resolvedSourceItem
    ? `${resolvedSurveyLabel} ${resolvedSourceItem}`
    : resolvedSourceItem || `#${conceptId}`;
  const surveyChoices = Object.keys(availableSurveys).sort();
  const multiSurveyBadge = surveyChoices.length >= 2;
  const currentSurveyIndex = surveyChoices.indexOf(resolvedSurveyId);
  const nextSurveyId = multiSurveyBadge && resolvedSurveyId
    ? surveyChoices[((currentSurveyIndex >= 0 ? currentSurveyIndex : 0) + 1) % surveyChoices.length]
    : undefined;
  const nextSurveySourceItem = nextSurveyId ? availableSurveys[nextSurveyId] ?? '' : '';
  const nextSurveyLabel = nextSurveyId ? surveyLabelFor(nextSurveyId, surveySettings) : '';
  const canFlipSurveyBadge = !!(activeSpeaker && onCycle && multiSurveyBadge && nextSurveyId);
  const surveyBadgeClassName = `font-mono text-[10px] ${surveyColorCodingEnabled && resolvedSurveyId ? (SURVEY_BADGE_TEXT_CLASSES[resolvedDisplayColor] ?? 'text-slate-400') : parentActive ? 'text-indigo-400' : 'text-slate-300'}`;
  const mergedClassName = `${surveyBadgeClassName}${className ? ` ${className}` : ''}`;

  if (canFlipSurveyBadge) {
    return (
      <button
        type="button"
        aria-label={`Switch survey for ${conceptName} from ${resolvedSurveyLabel} ${resolvedSourceItem} to ${nextSurveyLabel} ${nextSurveySourceItem}`}
        onClick={() => onCycle({ surveyId: nextSurveyId, sourceItem: nextSurveySourceItem })}
        className={`mr-2 rounded px-1 py-0.5 hover:bg-slate-100 hover:underline ${mergedClassName}`}
      >
        {badge}
      </button>
    );
  }

  return <span className={`mr-2 px-1 py-0.5 ${mergedClassName}`}>{badge}</span>;
}
