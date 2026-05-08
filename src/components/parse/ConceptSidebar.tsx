import { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';

import type { ConceptSurveyLinks, SpeakerSurveyChoices, SurveySettingsMap } from '../../api/types';
import { conceptMatchesElicitedKeys } from '../../lib/speakerElicitedConcepts';
import { defaultSurveySettings, resolveConceptSurvey, SURVEY_BADGE_TEXT_CLASSES, SURVEY_CHIP_CLASSES, surveyChoiceKeysForConcept, surveyLabelFor } from '../../lib/surveyOverlap';

type ConceptTag = 'untagged' | 'review' | 'confirmed' | 'problematic';
type ConceptSortMode = 'az' | '1n' | 'survey';
export type ConceptStatusFilter = 'all' | 'unreviewed' | 'flagged' | 'borrowings';

export interface SidebarConcept {
  id: number;
  key?: string;
  name: string;
  tag: ConceptTag;
  sourceItem?: string;
  sourceSurvey?: string;
  surveys?: ConceptSurveyLinks;
  mergedKeys?: string[];
  mergeAbsorbedNames?: string[];
  /** Present when concepts.csv already groups multiple variants by source_item
   * (e.g. `deep (A)`, `deep (B)`, `deep (C)`). Mirrors the `ConceptVariant`
   * shape from `speakerForm.ts` so each underlying row can be surfaced as a
   * selectable child while N-ary duplicate actions remain enabled. */
  variants?: Array<{ conceptKey: string; conceptEn: string; variantLabel: string }>;
  mergedVariants?: Array<{ conceptKey: string; conceptEn: string; variantLabel: string }>;
}

type SidebarVariant = NonNullable<SidebarConcept['variants']>[number];

interface SidebarTag {
  id: string;
  name: string;
  color: string;
}

interface ConceptSidebarProps {
  query: string;
  onQueryChange: (query: string) => void;
  sortMode: ConceptSortMode;
  onSortModeChange: (mode: ConceptSortMode) => void;
  hasSourceItems: boolean;
  filteredConcepts: SidebarConcept[];
  statusFilter: ConceptStatusFilter;
  onStatusFilterChange: (filter: ConceptStatusFilter) => void;
  selectedTagIds: Set<string>;
  onTagSelectionChange: (selected: Set<string>) => void;
  tags: SidebarTag[];
  activeConceptId: number;
  activeConceptKey?: string | null;
  onConceptSelect: (conceptId: number, conceptKey?: string) => void;
  activeSpeaker?: string | null;
  surveySettings?: SurveySettingsMap;
  speakerSurveyChoices?: SpeakerSurveyChoices;
  surveyColorCodingEnabled?: boolean;
  onSurveyChoiceChange?: (speaker: string, conceptKey: string, surveyId: string) => void;
  onMergeRequest?: (concept: SidebarConcept) => void;
  onUnmergeConcept?: (concept: SidebarConcept) => void;
  onDuplicateConcept?: (concept: SidebarConcept) => void;
  isVariantVisible?: (concept: SidebarConcept, variant: SidebarVariant) => boolean;
  scopedToSpeaker?: boolean;
  onScopedToSpeakerChange?: (next: boolean) => void;
  elicitedConceptKeys?: ReadonlySet<string>;
}

const tagDot: Record<ConceptTag, string> = {
  untagged: 'bg-slate-300',
  review: 'bg-amber-400',
  confirmed: 'bg-emerald-500',
  problematic: 'bg-rose-500',
};

export function ConceptSidebar({
  query,
  onQueryChange,
  sortMode,
  onSortModeChange,
  hasSourceItems,
  filteredConcepts,
  statusFilter,
  onStatusFilterChange,
  selectedTagIds,
  onTagSelectionChange,
  tags,
  activeConceptId,
  activeConceptKey = null,
  onConceptSelect,
  activeSpeaker = null,
  surveySettings = {},
  speakerSurveyChoices = {},
  surveyColorCodingEnabled = false,
  onSurveyChoiceChange,
  onMergeRequest,
  onUnmergeConcept,
  onDuplicateConcept,
  isVariantVisible,
  scopedToSpeaker = false,
  onScopedToSpeakerChange,
  elicitedConceptKeys = new Set<string>(),
}: ConceptSidebarProps) {
  const [contextMenu, setContextMenu] = useState<{ concept: SidebarConcept; x: number; y: number } | null>(null);
  const [expandedConceptIds, setExpandedConceptIds] = useState<Set<number>>(() => new Set());
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!contextMenu) return undefined;
    const close = (event: MouseEvent) => {
      if (menuRef.current?.contains(event.target as Node)) return;
      setContextMenu(null);
    };
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [contextMenu]);
  const toggleStatus = (filter: ConceptStatusFilter) => {
    onStatusFilterChange(statusFilter === filter ? 'all' : filter);
  };
  const toggleTag = (tagId: string) => {
    const next = new Set(selectedTagIds);
    if (next.has(tagId)) next.delete(tagId);
    else next.add(tagId);
    onTagSelectionChange(next);
  };
  const hasElicitedScope = elicitedConceptKeys.size > 0;
  const scopedConcepts = scopedToSpeaker && hasElicitedScope
    ? filteredConcepts.filter((concept) => conceptMatchesElicitedKeys(concept, elicitedConceptKeys))
    : filteredConcepts;
  const scopeLabel = scopedToSpeaker && activeSpeaker
    ? `Scoped to ${activeSpeaker}`
    : `Showing all ${filteredConcepts.length} master`;
  const scopeButtonLabel = scopedToSpeaker ? 'Show all' : 'Scope to speaker';
  const showMissingAnnotationNote = scopedToSpeaker && activeSpeaker && !hasElicitedScope;

  return (
    <aside className="w-[250px] shrink-0 border-r border-slate-200/80 bg-white flex flex-col" data-testid="concept-sidebar">
      <div className="p-4 shrink-0">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search concepts…"
            className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-1.5 pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <div className="inline-flex rounded-md bg-slate-100 p-0.5">
            <button
              data-testid="concept-sort-az"
              onClick={() => onSortModeChange('az')}
              title="Sort alphabetically by label"
              className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode === 'az' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'}`}
            >
              A→Z
            </button>
            <button
              data-testid="concept-sort-1n"
              onClick={() => onSortModeChange('1n')}
              title="Sort by concept id"
              className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode === '1n' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'}`}
            >
              1→N
            </button>
            <button
              data-testid="concept-sort-survey"
              onClick={() => onSortModeChange('survey')}
              disabled={!hasSourceItems}
              title={hasSourceItems ? 'Sort by original source item (section.item)' : 'No source_item values present in concepts.csv'}
              className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode === 'survey' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'} ${!hasSourceItems ? 'cursor-not-allowed opacity-40' : ''}`}
            >
              Source
            </button>
          </div>
          <span className="ml-auto text-[10px] text-slate-400">{scopedConcepts.length} concepts</span>
        </div>
        {activeSpeaker && onScopedToSpeakerChange && (
          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-[10px] text-slate-500">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-slate-600">{scopeLabel}</span>
              <button
                type="button"
                onClick={() => onScopedToSpeakerChange(!scopedToSpeaker)}
                className="rounded-full bg-white px-2 py-0.5 font-semibold text-indigo-600 ring-1 ring-slate-200 hover:bg-indigo-50"
              >
                {scopeButtonLabel}
              </button>
            </div>
            {showMissingAnnotationNote && (
              <div className="mt-1 text-slate-400">No annotation file for {activeSpeaker} — showing master list</div>
            )}
          </div>
        )}
        <div className="mt-2 flex flex-wrap gap-1">
          <button
            onClick={() => {
              onStatusFilterChange('all');
              onTagSelectionChange(new Set());
            }}
            data-testid="tagfilter-all"
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${statusFilter === 'all' ? 'bg-slate-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
          >
            All
          </button>
          <button
            onClick={() => toggleStatus('unreviewed')}
            title="Concepts not yet confirmed and without a cognate assignment"
            data-testid="tagfilter-unreviewed"
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${statusFilter === 'unreviewed' ? 'bg-amber-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusFilter === 'unreviewed' ? 'bg-white' : 'bg-amber-400'}`} />
            Unreviewed
          </button>
          <button
            onClick={() => toggleStatus('flagged')}
            title="Concepts tagged problematic, or with a flagged speaker utterance"
            data-testid="tagfilter-flagged"
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${statusFilter === 'flagged' ? 'bg-rose-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusFilter === 'flagged' ? 'bg-white' : 'bg-rose-400'}`} />
            Flagged
          </button>
          <button
            onClick={() => toggleStatus('borrowings')}
            title="Concepts with at least one borrowing"
            data-testid="tagfilter-borrowings"
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${statusFilter === 'borrowings' ? 'bg-violet-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusFilter === 'borrowings' ? 'bg-white' : 'bg-violet-400'}`} />
            Borrowings
          </button>
          {tags.map((tag) => {
            const selected = selectedTagIds.has(tag.id);
            return (
              <button
                key={tag.id}
                onClick={() => toggleTag(tag.id)}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${selected ? 'text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                style={selected ? { background: tag.color } : {}}
              >
                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: selected ? '#fff' : tag.color }} />
                {tag.name}
              </button>
            );
          })}
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-6">
        {scopedConcepts.map((concept) => {
          const isElicited = !hasElicitedScope || conceptMatchesElicitedKeys(concept, elicitedConceptKeys);
          const inactiveRowClass = isElicited ? 'text-slate-600' : 'text-slate-400';
          const surveyConcept = { ...concept, key: concept.key ?? String(concept.id) };
          const resolvedSurvey = resolveConceptSurvey(surveyConcept, activeSpeaker, speakerSurveyChoices, surveySettings);
          const resolvedSurveyLabel = surveyLabelFor(resolvedSurvey.surveyId, surveySettings);
          const sourceLabel = resolvedSurvey.surveyId && resolvedSurvey.sourceItem
            ? `${resolvedSurveyLabel} ${resolvedSurvey.sourceItem}`
            : resolvedSurvey.sourceItem || (concept.sourceSurvey && concept.sourceItem
              ? `${concept.sourceSurvey} ${concept.sourceItem}`
              : concept.sourceItem);
          const badge = sourceLabel ?? `#${concept.id}`;
          const surveyChoices = surveyChoiceKeysForConcept(surveyConcept);
          const nextSurveyId = surveyChoices.length > 1 && resolvedSurvey.surveyId
            ? surveyChoices[(surveyChoices.indexOf(resolvedSurvey.surveyId) + 1) % surveyChoices.length]
            : undefined;
          const nextSurveySourceItem = nextSurveyId ? surveyConcept.surveys?.[nextSurveyId] ?? '' : '';
          const nextSurveyLabel = nextSurveyId ? surveyLabelFor(nextSurveyId, surveySettings) : '';
          const canFlipSurveyBadge = !!(activeSpeaker && onSurveyChoiceChange && nextSurveyId);
          const variants = concept.variants ?? [];
          const visibleVariants = isVariantVisible ? variants.filter((variant) => isVariantVisible(concept, variant)) : variants;
          const hasVariants = visibleVariants.length > 1;
          const firstVariantKey = visibleVariants[0]?.conceptKey ?? variants[0]?.conceptKey ?? null;
          const parentActive = concept.id === activeConceptId && (!activeConceptKey || activeConceptKey === firstVariantKey || activeConceptKey === concept.key || concept.mergedKeys?.includes(activeConceptKey));
          const surveyBadgeClassName = `font-mono text-[10px] ${surveyColorCodingEnabled && resolvedSurvey.surveyId ? (SURVEY_BADGE_TEXT_CLASSES[resolvedSurvey.displayColor] ?? 'text-slate-400') : parentActive ? 'text-indigo-400' : 'text-slate-300'}`;
          const expanded = expandedConceptIds.has(concept.id);
          const parentName = concept.name;
          const noDataSuffix = !isElicited && !scopedToSpeaker && hasElicitedScope ? ' no data' : '';
          const mergeCountSuffix = concept.mergedKeys && concept.mergedKeys.length > 1 ? ` +${concept.mergedKeys.length - 1}` : '';
          const parentButtonLabel = `${parentName}${noDataSuffix}${mergeCountSuffix} ${badge}`.trim();
          return (
            <div key={concept.id} data-testid={`concept-row-${concept.id}`} className={`mb-0.5 rounded-md ${parentActive ? 'bg-indigo-50' : 'hover:bg-slate-50'}`}>
              <div className="flex items-center">
                {hasVariants ? (
                  <button
                    type="button"
                    aria-label={expanded ? 'Collapse variants' : 'Expand variants'}
                    data-testid={`concept-variant-toggle-${concept.id}`}
                    aria-expanded={expanded}
                    onClick={() => setExpandedConceptIds((current) => {
                      const next = new Set(current);
                      if (next.has(concept.id)) next.delete(concept.id);
                      else next.add(concept.id);
                      return next;
                    })}
                    className="ml-0.5 rounded px-1 py-1 text-[10px] font-semibold text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  >
                    {expanded ? '−' : '+'}
                  </button>
                ) : (
                  <span className="ml-0.5 w-[18px]" />
                )}
                <button
                  aria-label={parentButtonLabel}
                  onClick={() => {
                    if (firstVariantKey ?? concept.key) onConceptSelect(concept.id, firstVariantKey ?? concept.key);
                    else onConceptSelect(concept.id);
                  }}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    setContextMenu({ concept, x: event.clientX, y: event.clientY });
                  }}
                  className={`group flex min-w-0 flex-1 items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition ${parentActive ? 'bg-indigo-50 text-indigo-900' : inactiveRowClass}`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${tagDot[concept.tag]}`} />
                  <span className={`flex-1 text-[13px] ${parentActive ? 'font-semibold' : 'font-medium'}`}>{parentName}{!isElicited && !scopedToSpeaker && hasElicitedScope && (
                    <span className="ml-1 text-[10px] italic text-slate-400">no data</span>
                  )}</span>
                  {concept.mergedKeys && concept.mergedKeys.length > 1 && (
                    <span
                      title={(concept.mergeAbsorbedNames ?? []).join(', ')}
                      className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700"
                    >
                      +{concept.mergedKeys.length - 1}
                    </span>
                  )}
                </button>
                {canFlipSurveyBadge ? (
                  <button
                    type="button"
                    aria-label={`Switch survey for ${concept.name} from ${resolvedSurveyLabel} ${resolvedSurvey.sourceItem} to ${nextSurveyLabel} ${nextSurveySourceItem}`}
                    onClick={() => onSurveyChoiceChange(activeSpeaker, surveyConcept.key, nextSurveyId)}
                    className={`mr-2 rounded px-1 py-0.5 hover:bg-slate-100 ${surveyBadgeClassName}`}
                  >
                    {badge}
                  </button>
                ) : (
                  <span className={`mr-2 px-1 py-0.5 ${surveyBadgeClassName}`}>{badge}</span>
                )}
              </div>
              {expanded && hasVariants && visibleVariants.map((variant) => {
                const childActive = concept.id === activeConceptId && activeConceptKey === variant.conceptKey;
                const childConcept: SidebarConcept = {
                  ...concept,
                  key: variant.conceptKey,
                  name: variant.conceptEn,
                  variants: undefined,
                  mergedKeys: undefined,
                  mergedVariants: undefined,
                  mergeAbsorbedNames: undefined,
                };
                return (
                  <button
                    key={variant.conceptKey}
                    data-testid={`concept-variant-row-${variant.conceptKey}`}
                    onClick={() => onConceptSelect(concept.id, variant.conceptKey)}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      setContextMenu({ concept: childConcept, x: event.clientX, y: event.clientY });
                    }}
                    className={`ml-7 flex w-[calc(100%-1.75rem)] items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition ${childActive ? 'bg-indigo-50 text-indigo-900' : inactiveRowClass}`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${tagDot[concept.tag]}`} />
                    <span className={`flex-1 text-[12px] ${childActive ? 'font-semibold' : 'font-medium'}`}>{variant.conceptEn}</span>
                    <span className="font-mono text-[10px] text-slate-300">{variant.conceptKey}</span>
                  </button>
                );
              })}
              {surveyChoices.length > 1 && activeSpeaker && onSurveyChoiceChange && (
                <div className="flex flex-wrap gap-1 px-7 pb-1.5">
                  {surveyChoices.map((surveyId) => {
                    const sourceItem = surveyConcept.surveys?.[surveyId] ?? '';
                    const label = surveyLabelFor(surveyId, surveySettings);
                    const selected = resolvedSurvey.surveyId === surveyId;
                    const displayColor = (surveySettings[surveyId] ?? defaultSurveySettings(surveyId)).display_color;
                    return (
                      <button
                        key={surveyId}
                        type="button"
                        aria-label={selected ? `Current survey ${label} ${sourceItem}` : `Switch ${concept.name} to ${label} ${sourceItem}`}
                        onClick={() => onSurveyChoiceChange(activeSpeaker, surveyConcept.key, surveyId)}
                        className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold ring-1 ${selected ? (surveyColorCodingEnabled ? (SURVEY_CHIP_CLASSES[displayColor] ?? SURVEY_CHIP_CLASSES.slate) : 'bg-slate-900 text-white ring-slate-900') : 'bg-white text-slate-500 ring-slate-200 hover:bg-slate-50'}`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      {contextMenu && (
        <div
          ref={menuRef}
          role="menu"
          className="fixed z-50 min-w-[130px] rounded-md border border-slate-200 bg-white p-1 text-xs shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            type="button"
            role="menuitem"
            className="block w-full rounded px-2 py-1 text-left text-slate-700 hover:bg-slate-50"
            onClick={() => { onMergeRequest?.(contextMenu.concept); setContextMenu(null); }}
          >
            Merge with…
          </button>
          <button
            type="button"
            role="menuitem"
            aria-disabled="false"
            title="Add a new variant"
            className="block w-full rounded px-2 py-1 text-left text-slate-700 hover:bg-slate-50"
            onClick={() => {
              onDuplicateConcept?.(contextMenu.concept);
              setContextMenu(null);
            }}
          >
            Duplicate (split into next variant)
          </button>
          {contextMenu.concept.mergedKeys && contextMenu.concept.mergedKeys.length > 1 && (
            <button
              type="button"
              role="menuitem"
              className="block w-full rounded px-2 py-1 text-left text-slate-700 hover:bg-slate-50"
              onClick={() => { onUnmergeConcept?.(contextMenu.concept); setContextMenu(null); }}
            >
              Unmerge
            </button>
          )}
        </div>
      )}
    </aside>
  );
}
