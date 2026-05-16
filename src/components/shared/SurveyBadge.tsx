import type { KeyboardEvent, MouseEvent } from 'react';

import type { SurveySettingsMap } from '../../api/types';
import { normalizeDisplayColor, SURVEY_BADGE_TEXT_CLASSES, surveyLabelFor } from '../../lib/surveyOverlap';

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
  onPromote?: (next: { surveyId: string; sourceItem: string }) => void | Promise<void>;
  onEdit?: (current: { surveyId: string; sourceItem: string }) => void;
  variant?: 'sidebar' | 'editor';
  className?: string;
}

function surveyBadgeLabel(surveyId: string, sourceItem: string, fallback: string, settings: SurveySettingsMap): string {
  if (surveyId && sourceItem) return `${surveyLabelFor(surveyId, settings)} ${sourceItem}`;
  return sourceItem || fallback;
}

function slugForTestId(value: string): string {
  return value.replace(/[^A-Za-z0-9_-]+/g, '-');
}

export function SurveyBadge({
  conceptId,
  conceptKey,
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
  onPromote,
  onEdit,
  variant = 'sidebar',
  className = '',
}: SurveyBadgeProps) {
  const surveyChoices = Object.keys(availableSurveys).sort();
  const normalizedDisplayColor = normalizeDisplayColor(resolvedDisplayColor);
  const fallbackBadge = resolvedSourceItem || `#${conceptId}`;
  const baseTextClass = surveyColorCodingEnabled && resolvedSurveyId
    ? (SURVEY_BADGE_TEXT_CLASSES[normalizedDisplayColor] ?? 'text-slate-400')
    : parentActive ? 'text-indigo-400' : 'text-slate-300';
  const baseClassName = `font-mono text-[10px] ${baseTextClass}${className ? ` ${className}` : ''}`;
  const containerClassName = variant === 'editor'
    ? 'inline-flex flex-wrap items-center gap-1'
    : 'mr-2 inline-flex flex-wrap items-center gap-1';

  const fireEdit = (surveyId: string, sourceItem: string) => {
    if (!onEdit) return;
    onEdit({ surveyId, sourceItem });
  };

  const handleEditContextMenu = (surveyId: string, sourceItem: string) => (event: MouseEvent) => {
    if (!onEdit) return;
    event.preventDefault();
    event.stopPropagation();
    fireEdit(surveyId, sourceItem);
  };

  const handleKeyboardEdit = (surveyId: string, sourceItem: string) => (event: KeyboardEvent<HTMLElement>) => {
    if (!onEdit || event.key !== 'ContextMenu') return;
    event.preventDefault();
    fireEdit(surveyId, sourceItem);
  };

  const renderStaticPill = (surveyId: string, sourceItem: string, label: string, selected: boolean) => (
    <span
      key={surveyId || 'fallback'}
      data-testid={`survey-badge-pill-${slugForTestId(conceptKey)}-${slugForTestId(surveyId || 'fallback')}`}
      onContextMenu={handleEditContextMenu(surveyId, sourceItem)}
      onKeyDown={handleKeyboardEdit(surveyId, sourceItem)}
      tabIndex={onEdit ? 0 : undefined}
      className={`rounded px-1 py-0.5 ${baseClassName} ${selected && surveyChoices.length > 1 ? 'bg-slate-50 ring-1 ring-slate-200' : ''}`}
    >
      {label}
    </span>
  );

  if (surveyChoices.length >= 2 && variant !== 'editor') {
    const currentSurveyIndex = surveyChoices.indexOf(resolvedSurveyId);
    const nextSurveyId = resolvedSurveyId
      ? surveyChoices[((currentSurveyIndex >= 0 ? currentSurveyIndex : 0) + 1) % surveyChoices.length]
      : undefined;
    const nextSurveySourceItem = nextSurveyId ? availableSurveys[nextSurveyId] ?? '' : '';
    const nextSurveyLabel = nextSurveyId ? surveyLabelFor(nextSurveyId, surveySettings) : '';
    const label = surveyBadgeLabel(resolvedSurveyId, resolvedSourceItem, fallbackBadge, surveySettings);
    const resolvedSurveyLabel = surveyLabelFor(resolvedSurveyId, surveySettings);
    const canCycleSurveyBadge = !!(activeSpeaker && onCycle && nextSurveyId);
    const canPromoteSurveyBadge = !!(!activeSpeaker && onPromote && nextSurveyId);
    if (canCycleSurveyBadge || canPromoteSurveyBadge) {
      return (
        <button
          type="button"
          data-testid={`survey-badge-pill-${slugForTestId(conceptKey)}-${slugForTestId(resolvedSurveyId || 'fallback')}`}
          aria-label={canCycleSurveyBadge
            ? `Switch survey for ${conceptName} from ${resolvedSurveyLabel} ${resolvedSourceItem} to ${nextSurveyLabel} ${nextSurveySourceItem}`
            : `Promote survey for ${conceptName} from ${resolvedSurveyLabel} ${resolvedSourceItem} to ${nextSurveyLabel} ${nextSurveySourceItem}`}
          onClick={() => {
            if (canCycleSurveyBadge && onCycle && nextSurveyId) onCycle({ surveyId: nextSurveyId, sourceItem: nextSurveySourceItem });
            else if (canPromoteSurveyBadge && onPromote && nextSurveyId) void onPromote({ surveyId: nextSurveyId, sourceItem: nextSurveySourceItem });
          }}
          onContextMenu={handleEditContextMenu(resolvedSurveyId, resolvedSourceItem)}
          onKeyDown={handleKeyboardEdit(resolvedSurveyId, resolvedSourceItem)}
          className={`mr-2 rounded px-1 py-0.5 hover:bg-slate-100 hover:underline ${baseClassName}`}
        >
          {label}
        </button>
      );
    }
    return (
      <span
        data-testid={`survey-badge-pill-${slugForTestId(conceptKey)}-${slugForTestId(resolvedSurveyId || 'fallback')}`}
        onContextMenu={handleEditContextMenu(resolvedSurveyId, resolvedSourceItem)}
        onKeyDown={handleKeyboardEdit(resolvedSurveyId, resolvedSourceItem)}
        tabIndex={onEdit ? 0 : undefined}
        className={`mr-2 px-1 py-0.5 ${baseClassName}`}
      >
        {label}
      </span>
    );
  }

  if (surveyChoices.length >= 2) {
    const canCycleSurveyBadge = !!(activeSpeaker && onCycle);
    const canPromoteSurveyBadge = !!(!activeSpeaker && onPromote);
    const canFlipSurveyBadge = canCycleSurveyBadge || canPromoteSurveyBadge;
    return (
      <span data-testid={`survey-badge-${slugForTestId(conceptKey)}`} className={containerClassName}>
        {surveyChoices.map((surveyId) => {
          const sourceItem = availableSurveys[surveyId] ?? '';
          const label = surveyBadgeLabel(surveyId, sourceItem, fallbackBadge, surveySettings);
          const selected = surveyId === resolvedSurveyId;
          const display = surveySettings[surveyId]?.display_color ?? resolvedDisplayColor;
          const normalized = normalizeDisplayColor(display);
          const colorClass = surveyColorCodingEnabled
            ? (SURVEY_BADGE_TEXT_CLASSES[normalized] ?? baseTextClass)
            : selected && parentActive ? 'text-indigo-400' : selected ? baseTextClass : 'text-slate-400';
          const pillClassName = `rounded px-1 py-0.5 font-mono text-[10px] ${colorClass}${className ? ` ${className}` : ''} ${selected ? 'bg-slate-50 ring-1 ring-slate-200' : ''}`;
          if (canFlipSurveyBadge && !selected) {
            return (
              <button
                key={surveyId}
                type="button"
                data-testid={`survey-badge-pill-${slugForTestId(conceptKey)}-${slugForTestId(surveyId)}`}
                aria-label={canCycleSurveyBadge
                  ? `Switch survey for ${conceptName} to ${label}`
                  : `Promote survey for ${conceptName} to ${label}`}
                onClick={() => {
                  if (canCycleSurveyBadge && onCycle) onCycle({ surveyId, sourceItem });
                  else if (canPromoteSurveyBadge && onPromote) void onPromote({ surveyId, sourceItem });
                }}
                onContextMenu={handleEditContextMenu(surveyId, sourceItem)}
                onKeyDown={handleKeyboardEdit(surveyId, sourceItem)}
                className={`${pillClassName} hover:bg-slate-100 hover:underline`}
              >
                {label}
              </button>
            );
          }
          return renderStaticPill(surveyId, sourceItem, label, selected);
        })}
      </span>
    );
  }

  const label = surveyBadgeLabel(resolvedSurveyId, resolvedSourceItem, fallbackBadge, surveySettings);
  const canEdit = !!onEdit;
  if (canEdit) {
    return (
      <span data-testid={`survey-badge-${slugForTestId(conceptKey)}`} className={containerClassName}>
        <span
          data-testid={`survey-badge-pill-${slugForTestId(conceptKey)}-${slugForTestId(resolvedSurveyId || 'fallback')}`}
          onContextMenu={handleEditContextMenu(resolvedSurveyId, resolvedSourceItem)}
          onKeyDown={handleKeyboardEdit(resolvedSurveyId, resolvedSourceItem)}
          tabIndex={0}
          className={`rounded px-1 py-0.5 ${baseClassName}`}
        >
          {label}
        </span>
      </span>
    );
  }

  return (
    <span data-testid={`survey-badge-${slugForTestId(conceptKey)}`} className={containerClassName}>
      <span
        data-testid={`survey-badge-pill-${slugForTestId(conceptKey)}-${slugForTestId(resolvedSurveyId || 'fallback')}`}
        className={`rounded px-1 py-0.5 ${baseClassName}`}
      >
        {label}
      </span>
    </span>
  );
}
