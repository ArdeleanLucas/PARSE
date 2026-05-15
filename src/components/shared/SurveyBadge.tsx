import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';

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
  onPromote?: (next: { surveyId: string; sourceItem: string }) => void | Promise<void>;
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
  onPromote,
  className = '',
}: SurveyBadgeProps) {
  const resolvedSurveyLabel = surveyLabelFor(resolvedSurveyId, surveySettings);
  const badge = resolvedSurveyId && resolvedSourceItem
    ? `${resolvedSurveyLabel} ${resolvedSourceItem}`
    : resolvedSourceItem || `#${conceptId}`;
  const surveyChoices = Object.keys(availableSurveys).sort();
  const multiSurveyBadge = surveyChoices.length >= 2;
  const popoverSurveyBadge = surveyChoices.length >= 3;
  const currentSurveyIndex = surveyChoices.indexOf(resolvedSurveyId);
  const nextSurveyId = multiSurveyBadge && resolvedSurveyId
    ? surveyChoices[((currentSurveyIndex >= 0 ? currentSurveyIndex : 0) + 1) % surveyChoices.length]
    : undefined;
  const nextSurveySourceItem = nextSurveyId ? availableSurveys[nextSurveyId] ?? '' : '';
  const nextSurveyLabel = nextSurveyId ? surveyLabelFor(nextSurveyId, surveySettings) : '';
  const canCycleSurveyBadge = !!(activeSpeaker && onCycle && multiSurveyBadge && nextSurveyId);
  const canPromoteSurveyBadge = !!(!activeSpeaker && onPromote && multiSurveyBadge && nextSurveyId);
  const canFlipSurveyBadge = canCycleSurveyBadge || canPromoteSurveyBadge;
  const surveyBadgeClassName = `font-mono text-[10px] ${surveyColorCodingEnabled && resolvedSurveyId ? (SURVEY_BADGE_TEXT_CLASSES[resolvedDisplayColor] ?? 'text-slate-400') : parentActive ? 'text-indigo-400' : 'text-slate-300'}`;
  const mergedClassName = `${surveyBadgeClassName}${className ? ` ${className}` : ''}`;
  const [open, setOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const popoverRef = useRef<HTMLSpanElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return undefined;

    const handleDocumentMouseDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && popoverRef.current?.contains(target)) return;
      setOpen(false);
    };

    document.addEventListener('mousedown', handleDocumentMouseDown);
    return () => document.removeEventListener('mousedown', handleDocumentMouseDown);
  }, [open]);

  const focusMenuItem = (index: number) => {
    window.setTimeout(() => itemRefs.current[index]?.focus(), 0);
  };

  const selectSurveyChoice = (surveyId: string) => {
    const sourceItem = availableSurveys[surveyId] ?? '';
    if (canCycleSurveyBadge && onCycle) onCycle({ surveyId, sourceItem });
    else if (canPromoteSurveyBadge && onPromote) void onPromote({ surveyId, sourceItem });
    setOpen(false);
  };

  const openMenu = () => {
    const initialIndex = currentSurveyIndex >= 0 ? currentSurveyIndex : 0;
    setFocusedIndex(initialIndex);
    setOpen(true);
  };

  const handlePopoverKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      return;
    }

    if (!open) return;

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setFocusedIndex((previousIndex) => {
        const nextIndex = event.key === 'ArrowDown'
          ? (previousIndex + 1) % surveyChoices.length
          : (previousIndex - 1 + surveyChoices.length) % surveyChoices.length;
        focusMenuItem(nextIndex);
        return nextIndex;
      });
      return;
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      const surveyId = surveyChoices[focusedIndex];
      if (surveyId) selectSurveyChoice(surveyId);
    }
  };

  if (canFlipSurveyBadge && popoverSurveyBadge) {
    return (
      <span ref={popoverRef} className="relative mr-2 inline-block">
        <button
          type="button"
          aria-label={canCycleSurveyBadge
            ? `Choose survey for ${conceptName} from ${surveyChoices.length} linked surveys`
            : `Choose primary survey for ${conceptName} from ${surveyChoices.length} linked surveys`}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => (open ? setOpen(false) : openMenu())}
          onKeyDown={handlePopoverKeyDown}
          className={`rounded px-1 py-0.5 hover:bg-slate-100 hover:underline ${mergedClassName}`}
        >
          {badge}
        </button>
        {open ? (
          <div
            role="menu"
            aria-label={`Survey choices for ${conceptName}`}
            className="absolute left-0 top-full z-30 mt-1 min-w-max rounded border border-slate-200 bg-white py-1 text-slate-700 shadow-lg"
          >
            {surveyChoices.map((surveyId, index) => {
              const sourceItem = availableSurveys[surveyId] ?? '';
              const surveyLabel = surveyLabelFor(surveyId, surveySettings);
              const selected = surveyId === resolvedSurveyId;
              return (
                <button
                  key={surveyId}
                  ref={(element) => { itemRefs.current[index] = element; }}
                  type="button"
                  role="menuitem"
                  aria-current={selected ? 'true' : undefined}
                  tabIndex={-1}
                  onClick={() => selectSurveyChoice(surveyId)}
                  onKeyDown={handlePopoverKeyDown}
                  className="flex w-full items-center gap-2 whitespace-nowrap px-3 py-1 text-left text-xs hover:bg-slate-100 focus:bg-slate-100 focus:outline-none"
                >
                  <span aria-hidden="true" className="w-2 text-center">{selected ? '•' : ''}</span>
                  <span>{surveyLabel} {sourceItem}</span>
                </button>
              );
            })}
          </div>
        ) : null}
      </span>
    );
  }

  if (canFlipSurveyBadge) {
    return (
      <button
        type="button"
        aria-label={canCycleSurveyBadge
          ? `Switch survey for ${conceptName} from ${resolvedSurveyLabel} ${resolvedSourceItem} to ${nextSurveyLabel} ${nextSurveySourceItem}`
          : `Promote survey for ${conceptName} from ${resolvedSurveyLabel} ${resolvedSourceItem} to ${nextSurveyLabel} ${nextSurveySourceItem}`}
        onClick={() => {
          if (canCycleSurveyBadge && onCycle) onCycle({ surveyId: nextSurveyId, sourceItem: nextSurveySourceItem });
          else if (canPromoteSurveyBadge && onPromote) void onPromote({ surveyId: nextSurveyId, sourceItem: nextSurveySourceItem });
        }}
        className={`mr-2 rounded px-1 py-0.5 hover:bg-slate-100 hover:underline ${mergedClassName}`}
      >
        {badge}
      </button>
    );
  }

  return <span className={`mr-2 px-1 py-0.5 ${mergedClassName}`}>{badge}</span>;
}
