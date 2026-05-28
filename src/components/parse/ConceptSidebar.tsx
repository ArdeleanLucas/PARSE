import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';

import { deleteConceptSurveyLink, setConceptSurveyLink } from '../../api/client';
import { useConfigStore } from '../../stores/configStore';
import type { ConceptSurveyLinks, ConceptSurveyLinksByConcept, SpeakerConceptSurveyLinks, SpeakerSurveyChoices, SurveySettingsMap } from '../../api/types';
import { conceptMatchesElicitedKeys } from '../../lib/speakerElicitedConcepts';
import { resolveSurveyLinksForSpeaker, surveyRowIdsForConcept, type SpeakerSurveyLinkBucket } from '../../lib/surveyLinksForSpeaker';
import { SurveyBadge } from '../shared/SurveyBadge';
import { VariantChip } from '../shared/VariantChip';
import { defaultSurveySettings, normalizeSurveyId, resolveConceptSurvey, surveyLabelFor } from '../../lib/surveyOverlap';

type ConceptTag = 'untagged' | 'review' | 'confirmed' | 'problematic';
export type ConceptSortParent = 'concept' | 'source';
export type ConceptSortConceptSub = 'az' | '1n';
export type ConceptSortSourceSub = 'time' | 'row';
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
  variants?: Array<{ conceptKey: string; conceptEn: string; variantLabel: string; tag?: ConceptTag }>;
  mergedVariants?: Array<{ conceptKey: string; conceptEn: string; variantLabel: string; tag?: ConceptTag }>;
}

type SidebarVariant = NonNullable<SidebarConcept['variants']>[number];
const BUCKET_KEY_SEPARATOR = String.fromCharCode(0);
type SurveyLinkEditorMode = 'edit' | 'add';

interface SurveyLinkEditorState {
  concept: SidebarConcept;
  mode: SurveyLinkEditorMode;
  bucket: SpeakerSurveyLinkBucket | null;
  rowIds: string[];
  surveyId: string;
  sourceItem: string;
  error: string | null;
  saving: boolean;
}

interface SidebarTag {
  id: string;
  name: string;
  color: string;
}

interface ConceptSidebarProps {
  query: string;
  onQueryChange: (query: string) => void;
  sortParent: ConceptSortParent;
  conceptSub: ConceptSortConceptSub;
  sourceSub: ConceptSortSourceSub;
  onSortParentChange: (parent: ConceptSortParent) => void;
  onConceptSubChange: (sub: ConceptSortConceptSub) => void;
  onSourceSubChange: (sub: ConceptSortSourceSub) => void;
  sourceDisabled: boolean;
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
  conceptSurveyLinks?: ConceptSurveyLinksByConcept;
  speakerConceptSurveyLinks?: SpeakerConceptSurveyLinks;
  speakerSurveyChoices?: SpeakerSurveyChoices;
  surveyColorCodingEnabled?: boolean;
  onSurveyChoiceChange?: (speaker: string, conceptKey: string, surveyId: string) => void;
  onPromoteSurveyPrimary?: (conceptId: string, surveyId: string, sourceItem: string) => void | Promise<void>;
  onMergeRequest?: (concept: SidebarConcept) => void;
  onUnmergeConcept?: (concept: SidebarConcept) => void;
  onAddElicitation?: (concept: SidebarConcept) => void;
  onDeleteConcept?: (concept: SidebarConcept) => void;
  /**
   * Optional grouped/source-item variant visibility predicate. ParseUI wires this to
   * src/lib/sidebarVisibility.ts so speaker-scope and tag filters are applied to each
   * raw variant key before expanded child rows are rendered or parent clicks select
   * the first visible variant.
   */
  isConceptVariantVisibleInSidebar?: (concept: SidebarConcept, variant: SidebarVariant) => boolean;
  /** When true, suppress the per-concept variant pill strip (A/B/C/...). Used in compare
   * mode where the strip floods the panel as more speakers are added. */
  hideVariantPills?: boolean;
  scopedToSpeaker?: boolean;
  onScopedToSpeakerChange?: (next: boolean) => void;
  elicitedConceptKeys?: ReadonlySet<string>;
  elicitationVariantLabelsByConceptKey?: Record<string, string[]>;
  actionFeedback?: { message: string; variant: 'error' | 'warning' } | null;
  onDismissActionFeedback?: () => void;
}

const tagDot: Record<ConceptTag, string> = {
  untagged: 'bg-slate-300',
  review: 'bg-amber-400',
  confirmed: 'bg-emerald-500',
  problematic: 'bg-rose-500',
};

function surveyLinksForSidebarConcept(concept: SidebarConcept): ConceptSurveyLinks {
  const links: ConceptSurveyLinks = {};
  for (const [surveyId, sourceItem] of Object.entries(concept.surveys ?? {})) {
    const key = surveyId.trim().toLocaleLowerCase();
    const item = String(sourceItem ?? '').trim();
    if (key && item) links[key] = item;
  }
  const legacySurvey = concept.sourceSurvey?.trim().toLocaleLowerCase() ?? '';
  const legacyItem = concept.sourceItem?.trim() ?? '';
  if (legacySurvey && legacyItem && !links[legacySurvey]) links[legacySurvey] = legacyItem;
  return links;
}

function bundleRowIds(concept: SidebarConcept): string[] {
  return surveyRowIdsForConcept(concept).filter(Boolean);
}

function variantLabelForRowId(concept: SidebarConcept, rowId: string): string {
  const variant = concept.variants?.find((candidate) => candidate.conceptKey === rowId);
  return variant?.variantLabel ?? concept.mergedVariants?.find((candidate) => candidate.conceptKey === rowId)?.variantLabel ?? concept.name;
}

function rowPreview(concept: SidebarConcept, rowIds: readonly string[]): string {
  return rowIds.map((rowId) => `${variantLabelForRowId(concept, rowId)} (id ${rowId})`).join(', ');
}

function globalLinksForConcept(concept: SidebarConcept, conceptSurveyLinks: ConceptSurveyLinksByConcept): ConceptSurveyLinksByConcept {
  const links: ConceptSurveyLinksByConcept = {};
  const fallback = surveyLinksForSidebarConcept(concept);
  for (const rowId of bundleRowIds(concept)) {
    const sidecar = conceptSurveyLinks[rowId];
    links[rowId] = sidecar ? { ...fallback, ...sidecar } : fallback;
  }
  return links;
}

function bucketsForConcept(
  concept: SidebarConcept,
  activeSpeaker: string | null | undefined,
  conceptSurveyLinks: ConceptSurveyLinksByConcept,
  speakerConceptSurveyLinks: SpeakerConceptSurveyLinks,
): SpeakerSurveyLinkBucket[] {
  return resolveSurveyLinksForSpeaker(
    bundleRowIds(concept),
    activeSpeaker,
    globalLinksForConcept(concept, conceptSurveyLinks),
    speakerConceptSurveyLinks,
  );
}

function surveyLinkChoiceIds(concept: SidebarConcept, settings: SurveySettingsMap, buckets: readonly SpeakerSurveyLinkBucket[] = []): string[] {
  const ids = new Set<string>();
  Object.keys(settings ?? {}).forEach((id) => { const normalized = normalizeSurveyId(id); if (normalized) ids.add(normalized); });
  Object.keys(surveyLinksForSidebarConcept(concept)).forEach((id) => ids.add(normalizeSurveyId(id)));
  buckets.forEach((bucket) => ids.add(bucket.surveyId));
  return [...ids].filter(Boolean).sort();
}

export function ConceptSidebar({
  query,
  onQueryChange,
  sortParent,
  conceptSub,
  sourceSub,
  onSortParentChange,
  onConceptSubChange,
  onSourceSubChange,
  sourceDisabled,
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
  conceptSurveyLinks = {},
  speakerConceptSurveyLinks = {},
  speakerSurveyChoices = {},
  surveyColorCodingEnabled = false,
  onSurveyChoiceChange,
  onPromoteSurveyPrimary,
  onMergeRequest,
  onUnmergeConcept,
  onAddElicitation,
  onDeleteConcept,
  isConceptVariantVisibleInSidebar,
  hideVariantPills = false,
  scopedToSpeaker = false,
  onScopedToSpeakerChange,
  elicitedConceptKeys = new Set<string>(),
  elicitationVariantLabelsByConceptKey = {},
  actionFeedback = null,
  onDismissActionFeedback,
}: ConceptSidebarProps) {
  const [contextMenu, setContextMenu] = useState<{ concept: SidebarConcept; x: number; y: number } | null>(null);
  const [menuPos, setMenuPos] = useState<{ left: number; top: number } | null>(null);
  const [surveyLinkEditor, setSurveyLinkEditor] = useState<SurveyLinkEditorState | null>(null);
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

  useLayoutEffect(() => {
    if (!contextMenu) {
      setMenuPos(null);
      return;
    }
    const el = menuRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = contextMenu.x;
    let top = contextMenu.y;
    if (left + rect.width + margin > vw) {
      left = Math.max(margin, vw - rect.width - margin);
    }
    if (top + rect.height + margin > vh) {
      top = Math.max(margin, vh - rect.height - margin);
    }
    setMenuPos({ left, top });
  }, [contextMenu, surveyLinkEditor]);
  const openSurveyLinkEditor = (concept: SidebarConcept) => {
    const buckets = bucketsForConcept(concept, activeSpeaker, conceptSurveyLinks, speakerConceptSurveyLinks);
    const resolved = resolveConceptSurvey(
      { ...concept, key: concept.key ?? String(concept.id) },
      activeSpeaker,
      speakerSurveyChoices,
      surveySettings,
    );
    const firstBucket = buckets.find((bucket) => bucket.surveyId === resolved.surveyId) ?? buckets[0] ?? null;
    const surveyIds = surveyLinkChoiceIds(concept, surveySettings, buckets);
    setSurveyLinkEditor({
      concept,
      mode: firstBucket ? 'edit' : 'add',
      bucket: firstBucket,
      rowIds: firstBucket?.rowIds ?? bundleRowIds(concept),
      surveyId: firstBucket?.surveyId ?? surveyIds[0] ?? '',
      sourceItem: firstBucket?.sourceItem ?? '',
      error: null,
      saving: false,
    });
  };

  const selectSurveyBucket = (bucket: SpeakerSurveyLinkBucket) => {
    setSurveyLinkEditor((current) => current ? {
      ...current,
      mode: 'edit',
      bucket,
      rowIds: bucket.rowIds,
      surveyId: bucket.surveyId,
      sourceItem: bucket.sourceItem,
      error: null,
    } : current);
  };

  const startAddSurveyLink = () => {
    setSurveyLinkEditor((current) => {
      if (!current) return current;
      const buckets = bucketsForConcept(current.concept, activeSpeaker, conceptSurveyLinks, speakerConceptSurveyLinks);
      const used = new Set(buckets.map((bucket) => bucket.surveyId));
      const nextSurveyId = surveyLinkChoiceIds(current.concept, surveySettings, buckets).find((surveyId) => !used.has(surveyId)) ?? '';
      return {
        ...current,
        mode: 'add',
        bucket: null,
        rowIds: bundleRowIds(current.concept),
        surveyId: nextSurveyId,
        sourceItem: '',
        error: null,
      };
    });
  };

  const saveSurveyLinkEditor = async () => {
    if (!surveyLinkEditor) return;
    const conceptIdOrList = surveyLinkEditor.rowIds.join(',');
    const payload = { survey_id: surveyLinkEditor.surveyId, source_item: surveyLinkEditor.sourceItem.trim(), ...(activeSpeaker ? { speaker: activeSpeaker } : {}) };
    if (!conceptIdOrList || !payload.survey_id || !payload.source_item) {
      setSurveyLinkEditor((current) => current ? { ...current, error: 'Survey ID and source item are required.' } : current);
      return;
    }
    setSurveyLinkEditor((current) => current ? { ...current, saving: true, error: null } : current);
    try {
      const response = await setConceptSurveyLink(conceptIdOrList, payload);
      if (response.survey_overlap) useConfigStore.getState().applySurveyOverlap(response.survey_overlap);
      setSurveyLinkEditor(null);
      setContextMenu(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setSurveyLinkEditor((current) => current ? { ...current, saving: false, error: message } : current);
    }
  };

  const removeSurveyLinkEditor = async () => {
    if (!surveyLinkEditor || surveyLinkEditor.mode !== 'edit') return;
    const conceptIdOrList = surveyLinkEditor.rowIds.join(',');
    setSurveyLinkEditor((current) => current ? { ...current, saving: true, error: null } : current);
    try {
      const response = await deleteConceptSurveyLink(conceptIdOrList, { survey_id: surveyLinkEditor.surveyId, source_item: surveyLinkEditor.sourceItem.trim(), ...(activeSpeaker ? { speaker: activeSpeaker } : {}) });
      if (response.survey_overlap) useConfigStore.getState().applySurveyOverlap(response.survey_overlap);
      setSurveyLinkEditor(null);
      setContextMenu(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setSurveyLinkEditor((current) => current ? { ...current, saving: false, error: message } : current);
    }
  };

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
  const scopeButtonLabel = scopedToSpeaker ? 'Show all' : 'Scope to speaker';
  const scopeButtonText = scopedToSpeaker ? 'all' : 'scope';
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
        {actionFeedback && (
          <div
            role="status"
            data-testid="sidebar-action-feedback"
            className={`mt-3 flex items-center gap-2 rounded-md border px-2 py-1.5 text-[11px] ${
              actionFeedback.variant === 'warning'
                ? 'border-amber-200 bg-amber-50 text-amber-900'
                : 'border-rose-200 bg-rose-50 text-rose-900'
            }`}
          >
            <span className="flex-1">{actionFeedback.message}</span>
            <button
              type="button"
              aria-label="Dismiss"
              className="shrink-0 rounded p-0.5 hover:bg-white/70"
              onClick={onDismissActionFeedback}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}
        <div className="mt-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="inline-flex rounded-md bg-slate-100 p-0.5">
              <button
                data-testid="concept-sort-parent-concept"
                data-toggle-state={sortParent === 'concept' ? 'on' : 'off'}
                type="button"
                onClick={() => onSortParentChange('concept')}
                className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortParent === 'concept' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'}`}
              >
                Concept
              </button>
              <button
                data-testid="concept-sort-parent-source"
                data-toggle-state={sortParent === 'source' ? 'on' : 'off'}
                type="button"
                onClick={() => { if (!sourceDisabled) onSortParentChange('source'); }}
                aria-disabled={sourceDisabled ? 'true' : undefined}
                title={sourceDisabled ? 'Select one speaker to enable Source ordering' : 'Order concepts by this speaker source sequence'}
                className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortParent === 'source' ? 'bg-sky-600 text-white shadow-sm' : 'text-sky-700'} ${sourceDisabled ? 'cursor-not-allowed opacity-50' : 'hover:bg-sky-100'}`}
              >
                Source
              </button>
            </div>
            {activeSpeaker && onScopedToSpeakerChange ? (
              <div className="flex flex-col items-end text-[10px] text-slate-400">
                <span data-testid="concept-scope-breadcrumb" className="inline-flex items-center gap-1 whitespace-nowrap">
                  {scopedToSpeaker && hasElicitedScope ? (
                    <>
                      <span>{scopedConcepts.length} in</span>
                      {' '}
                      <span className="font-semibold text-sky-700">{activeSpeaker}</span>
                    </>
                  ) : (
                    <span>{scopedConcepts.length} concepts</span>
                  )}
                  <span aria-hidden="true">·</span>
                  <button
                    type="button"
                    aria-label={scopeButtonLabel}
                    onClick={() => onScopedToSpeakerChange(!scopedToSpeaker)}
                    className="rounded-full bg-white px-1.5 py-0.5 font-semibold text-indigo-600 ring-1 ring-slate-200 hover:bg-indigo-50"
                  >
                    {scopeButtonText}
                  </button>
                </span>
                {showMissingAnnotationNote && (
                  <span className="mt-1 text-slate-400">No annotation file for {activeSpeaker} — showing master list</span>
                )}
              </div>
            ) : (
              <span className="text-[10px] text-slate-400">{scopedConcepts.length} concepts</span>
            )}
          </div>
          {sortParent === 'concept' ? (
            <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1">
              <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">Order by</span>
              <div className="inline-flex rounded-md bg-slate-100 p-0.5">
                <button
                  data-testid="concept-sort-az"
                  data-toggle-state={conceptSub === 'az' ? 'on' : 'off'}
                  type="button"
                  onClick={() => onConceptSubChange('az')}
                  title="Sort alphabetically by label"
                  className={`px-2 py-0.5 text-[10px] font-semibold rounded ${conceptSub === 'az' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'}`}
                >
                  A→Z
                </button>
                <button
                  data-testid="concept-sort-1n"
                  data-toggle-state={conceptSub === '1n' ? 'on' : 'off'}
                  type="button"
                  onClick={() => onConceptSubChange('1n')}
                  title="Sort by concept id"
                  className={`px-2 py-0.5 text-[10px] font-semibold rounded ${conceptSub === '1n' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'}`}
                >
                  1–N
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-md border border-sky-200 bg-sky-100 px-2 py-1">
              <span className="text-[9px] font-semibold uppercase tracking-wider text-sky-700">Order by</span>
              <div className="inline-flex rounded-md bg-sky-50 p-0.5">
                <button
                  data-testid="concept-sort-source-time"
                  data-toggle-state={sourceSub === 'time' ? 'on' : 'off'}
                  type="button"
                  onClick={() => onSourceSubChange('time')}
                  className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sourceSub === 'time' ? 'bg-sky-600 text-white shadow-sm' : 'text-sky-700 hover:bg-sky-200'}`}
                >
                  Time
                </button>
                <button
                  data-testid="concept-sort-source-row"
                  data-toggle-state={sourceSub === 'row' ? 'on' : 'off'}
                  type="button"
                  onClick={() => onSourceSubChange('row')}
                  className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sourceSub === 'row' ? 'bg-sky-600 text-white shadow-sm' : 'text-sky-700 hover:bg-sky-200'}`}
                >
                  Row
                </button>
              </div>
              {activeSpeaker && <span className="ml-auto text-[10px] text-sky-700/80">{activeSpeaker}</span>}
            </div>
          )}
        </div>
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
          const hasSpeakerAwareSurveyLinks = Object.keys(conceptSurveyLinks).length > 0 || Object.keys(speakerConceptSurveyLinks).length > 0;
          const speakerBuckets = hasSpeakerAwareSurveyLinks ? bucketsForConcept(surveyConcept, activeSpeaker, conceptSurveyLinks, speakerConceptSurveyLinks) : [];
          const fallbackResolvedSurvey = resolveConceptSurvey(surveyConcept, activeSpeaker, speakerSurveyChoices, surveySettings);
          const sourceSurvey = normalizeSurveyId(concept.sourceSurvey);
          const speakerChoice = activeSpeaker
            ? normalizeSurveyId(speakerSurveyChoices?.[activeSpeaker]?.[surveyConcept.key] ?? '')
            : '';
          const preferredSpeakerBucket = activeSpeaker && speakerChoice
            ? speakerBuckets.find((bucket) => bucket.surveyId === speakerChoice) ?? speakerBuckets[0]
            : !activeSpeaker && sourceSurvey
            ? speakerBuckets.find((bucket) => bucket.surveyId === sourceSurvey) ?? speakerBuckets[0]
            : speakerBuckets[0];
          const resolvedSurvey = preferredSpeakerBucket ? {
            conceptKey: surveyConcept.key,
            surveyId: preferredSpeakerBucket.surveyId,
            sourceItem: preferredSpeakerBucket.sourceItem,
            displayLabel: surveyLabelFor(preferredSpeakerBucket.surveyId, surveySettings),
            displayColor: (surveySettings[preferredSpeakerBucket.surveyId] ?? defaultSurveySettings(preferredSpeakerBucket.surveyId)).display_color,
            hasOverlap: speakerBuckets.length > 1,
            availableSurveys: Object.fromEntries(speakerBuckets.map((bucket) => [bucket.surveyId, bucket.sourceItem])),
          } : fallbackResolvedSurvey;
          const resolvedSurveyLabel = surveyLabelFor(resolvedSurvey.surveyId, surveySettings);
          const fallbackBadge = (concept.sourceSurvey && concept.sourceItem)
            ? `${concept.sourceSurvey} ${concept.sourceItem}`
            : concept.sourceItem;
          const badge = resolvedSurvey.surveyId && resolvedSurvey.sourceItem
            ? `${resolvedSurveyLabel} ${resolvedSurvey.sourceItem}`
            : (resolvedSurvey.sourceItem || fallbackBadge || `#${concept.id}`);
          const variants = concept.variants ?? [];
          const visibleVariants = isConceptVariantVisibleInSidebar ? variants.filter((variant) => isConceptVariantVisibleInSidebar(concept, variant)) : variants;
          const elicitationLabels = !hideVariantPills && !visibleVariants.length
            ? (elicitationVariantLabelsByConceptKey[concept.key ?? String(concept.id)] ?? [])
            : [];
          const hasVariants = !hideVariantPills && visibleVariants.length > 1;
          const hasElicitationVariants = elicitationLabels.length > 1;
          const firstVariantKey = visibleVariants[0]?.conceptKey ?? variants[0]?.conceptKey ?? null;
          const parentActive = !!(concept.id === activeConceptId && (!activeConceptKey || activeConceptKey === concept.key || concept.mergedKeys?.includes(activeConceptKey)));
          const parentName = concept.name;
          const noDataSuffix = !isElicited && !scopedToSpeaker && hasElicitedScope ? ' no data' : '';
          const mergeCountSuffix = concept.mergedKeys && concept.mergedKeys.length > 1 ? ` +${concept.mergedKeys.length - 1}` : '';
          const variantSuffix = hasVariants
            ? ` variants ${visibleVariants.map((variant) => variant.variantLabel).join(' ')}`
            : hasElicitationVariants
              ? ` variants ${elicitationLabels.join(' ')}`
              : '';
          const parentButtonLabel = `${parentName}${noDataSuffix}${mergeCountSuffix} ${badge}${variantSuffix}`.trim();
          return (
            <div key={concept.id} data-testid={`concept-row-${concept.id}`} className="mb-0.5 rounded-md hover:bg-slate-50">
              <div className="flex items-center">
                <button
                  aria-label={parentButtonLabel}
                  data-testid={`concept-parent-button-${concept.id}`}
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
                {hasVariants && (
                  <div className="ml-1 flex shrink-0 items-center gap-0.5" aria-label={`${parentName} variants`}>
                    {visibleVariants.map((variant) => {
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
                        <VariantChip
                          as="button"
                          key={variant.conceptKey}
                          letter={variant.variantLabel}
                          dotClassName={tagDot[variant.tag ?? concept.tag]}
                          dotTestId={`concept-variant-pill-dot-${variant.conceptKey}`}
                          conceptEn={variant.conceptEn}
                          active={childActive}
                          aria-label={`${parentName} variant ${variant.variantLabel} ${variant.conceptEn}`}
                          title={`${variant.conceptEn} (${variant.conceptKey})`}
                          data-testid={`concept-variant-pill-${variant.conceptKey}`}
                          onClick={() => onConceptSelect(concept.id, variant.conceptKey)}
                          onContextMenu={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            setContextMenu({ concept: childConcept, x: event.clientX, y: event.clientY });
                          }}
                        />
                      );
                    })}
                  </div>
                )}
                {hasElicitationVariants && (
                  <div className="ml-1 flex shrink-0 items-center gap-0.5" aria-label={`${parentName} elicitations`}>
                    {elicitationLabels.map((letter) => (
                      <VariantChip
                        as="button"
                        key={`${concept.key ?? concept.id}:${letter}`}
                        letter={letter}
                        dotClassName={tagDot[concept.tag]}
                        conceptEn={parentName}
                        aria-label={`${parentName} (${letter})`}
                        title={`${parentName} (${letter})`}
                        active={parentActive}
                        onClick={() => {
                          if (concept.key) onConceptSelect(concept.id, concept.key);
                          else onConceptSelect(concept.id);
                        }}
                      />
                    ))}
                  </div>
                )}
                <SurveyBadge
                  conceptId={String(concept.id)}
                  conceptKey={surveyConcept.key}
                  conceptName={concept.name}
                  resolvedSurveyId={resolvedSurvey.surveyId}
                  resolvedSourceItem={resolvedSurvey.sourceItem || fallbackBadge || ''}
                  resolvedDisplayColor={resolvedSurvey.displayColor}
                  availableSurveys={resolvedSurvey.availableSurveys}
                  surveySettings={surveySettings}
                  surveyColorCodingEnabled={surveyColorCodingEnabled}
                  activeSpeaker={activeSpeaker ?? null}
                  parentActive={parentActive}
                  onCycle={onSurveyChoiceChange ? (next) => onSurveyChoiceChange(activeSpeaker ?? '', surveyConcept.key, next.surveyId) : undefined}
                  onPromote={onPromoteSurveyPrimary ? (next) => onPromoteSurveyPrimary(String(concept.id), next.surveyId, next.sourceItem) : undefined}
                />
              </div>
            </div>
          );
        })}
      </nav>
      {contextMenu && (
        <div
          ref={menuRef}
          role="menu"
          className="fixed z-50 min-w-[130px] rounded-md border border-slate-200 bg-white p-1 text-xs shadow-lg"
          style={{
            left: menuPos?.left ?? contextMenu.x,
            top: menuPos?.top ?? contextMenu.y,
            visibility: menuPos ? 'visible' : 'hidden',
          }}
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
            title="Add another elicitation interval for this concept"
            className="block w-full rounded px-2 py-1 text-left text-slate-700 hover:bg-slate-50"
            onClick={() => {
              onAddElicitation?.(contextMenu.concept);
              setContextMenu(null);
            }}
          >
            + Add elicitation
          </button>
          <button
            type="button"
            role="menuitem"
            className="block w-full rounded px-2 py-1 text-left text-slate-700 hover:bg-slate-50"
            onClick={() => openSurveyLinkEditor(contextMenu.concept)}
          >
            Change survey ID…
          </button>
          {!contextMenu.concept.variants?.length && (
            <button
              type="button"
              role="menuitem"
              title="Delete this variant"
              className="block w-full rounded px-2 py-1 text-left text-rose-700 hover:bg-rose-50"
              onClick={() => {
                onDeleteConcept?.(contextMenu.concept);
                setContextMenu(null);
              }}
            >
              Delete variant…
            </button>
          )}
          {surveyLinkEditor && surveyLinkEditor.concept.id === contextMenu.concept.id && (() => {
            const buckets = bucketsForConcept(surveyLinkEditor.concept, activeSpeaker, conceptSurveyLinks, speakerConceptSurveyLinks);
            const selectedBucketKey = surveyLinkEditor.bucket ? `${surveyLinkEditor.bucket.surveyId}${BUCKET_KEY_SEPARATOR}${surveyLinkEditor.bucket.sourceItem}` : '';
            const usedSurveyIds = new Set(buckets.map((bucket) => bucket.surveyId));
            const selectableSurveyIds = surveyLinkEditor.mode === 'add'
              ? surveyLinkChoiceIds(surveyLinkEditor.concept, surveySettings, buckets).filter((surveyId) => !usedSurveyIds.has(surveyId) || surveyId === surveyLinkEditor.surveyId)
              : surveyLinkChoiceIds(surveyLinkEditor.concept, surveySettings, buckets);
            const blockingNoSpeaker = surveyLinkEditor.rowIds.length > 1 && !activeSpeaker;
            const saveDisabledReason = 'Select a speaker before changing the survey ID for a grouped concept.';
            return (
            <div className="mt-1 w-64 space-y-1.5 border-t border-slate-100 pt-2" role="group" aria-label="Change survey ID editor">
              <div className="text-[10px] font-semibold text-slate-500">Current buckets</div>
              <div className="space-y-1">
                {buckets.map((bucket) => {
                  const bucketKey = `${bucket.surveyId}${BUCKET_KEY_SEPARATOR}${bucket.sourceItem}`;
                  const selected = surveyLinkEditor.mode === 'edit' && selectedBucketKey === bucketKey;
                  return (
                    <button
                      key={bucketKey}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => selectSurveyBucket(bucket)}
                      className={`block w-full rounded border px-2 py-1 text-left text-[10px] ${selected ? 'border-indigo-300 bg-indigo-50 text-indigo-900' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                    >
                      <span className="font-semibold">{surveyLabelFor(bucket.surveyId, surveySettings)} {bucket.sourceItem}</span>
                      <span className="block text-slate-400">variants: {rowPreview(surveyLinkEditor.concept, bucket.rowIds)}</span>
                    </button>
                  );
                })}
              </div>
              <button type="button" onClick={startAddSurveyLink} className="text-[10px] font-semibold text-indigo-600">+ Add new link</button>
              <div className="rounded bg-slate-50 px-2 py-1 text-[10px] text-slate-500">
                Will update variants: {rowPreview(surveyLinkEditor.concept, surveyLinkEditor.rowIds)}
              </div>
              <label className="block text-[10px] font-semibold text-slate-500">
                survey_id
                <select
                  aria-label="survey_id"
                  value={surveyLinkEditor.surveyId}
                  onChange={(event) => {
                    const surveyId = event.target.value;
                    const existing = buckets.find((bucket) => bucket.surveyId === surveyId);
                    setSurveyLinkEditor((current) => current ? {
                      ...current,
                      surveyId,
                      sourceItem: current.mode === 'edit' ? existing?.sourceItem ?? current.sourceItem : current.sourceItem,
                    } : current);
                  }}
                  className="mt-0.5 w-full rounded border border-slate-200 px-1 py-0.5 text-[11px] text-slate-700"
                >
                  {selectableSurveyIds.map((surveyId) => (
                    <option key={surveyId} value={surveyId}>{surveyId}</option>
                  ))}
                </select>
              </label>
              <label className="block text-[10px] font-semibold text-slate-500">
                source_item
                <input
                  aria-label="source_item"
                  value={surveyLinkEditor.sourceItem}
                  onChange={(event) => setSurveyLinkEditor((current) => current ? { ...current, sourceItem: event.target.value } : current)}
                  className="mt-0.5 w-full rounded border border-slate-200 px-1 py-0.5 text-[11px] text-slate-700"
                />
              </label>
              {surveyLinkEditor.error ? <div className="text-[10px] text-rose-600">{surveyLinkEditor.error}</div> : null}
              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={surveyLinkEditor.saving || blockingNoSpeaker}
                  title={blockingNoSpeaker ? saveDisabledReason : undefined}
                  onClick={() => { void saveSurveyLinkEditor(); }}
                  className="flex-1 rounded bg-indigo-600 px-2 py-1 text-[10px] font-semibold text-white disabled:opacity-60"
                >
                  Save
                </button>
                <button type="button" disabled={surveyLinkEditor.saving} onClick={() => { setSurveyLinkEditor(null); }} className="rounded border border-slate-200 px-2 py-1 text-[10px] font-semibold text-slate-600">Cancel</button>
              </div>
              {surveyLinkEditor.mode === 'edit' ? (
                <button type="button" disabled={surveyLinkEditor.saving} onClick={() => { void removeSurveyLinkEditor(); }} className="text-[10px] font-semibold text-rose-600 disabled:opacity-60">Remove link</button>
              ) : null}
            </div>
            );
          })()}
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
