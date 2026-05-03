import { Search } from 'lucide-react';

type ConceptTag = 'untagged' | 'review' | 'confirmed' | 'problematic';
type ConceptSortMode = 'az' | '1n' | 'survey';
export type ConceptStatusFilter = 'all' | 'unreviewed' | 'flagged' | 'borrowings';

interface SidebarConcept {
  id: number;
  name: string;
  tag: ConceptTag;
  sourceItem?: string;
  sourceSurvey?: string;
}

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
  onConceptSelect: (conceptId: number) => void;
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
  onConceptSelect,
}: ConceptSidebarProps) {
  const toggleStatus = (filter: ConceptStatusFilter) => {
    onStatusFilterChange(statusFilter === filter ? 'all' : filter);
  };
  const toggleTag = (tagId: string) => {
    const next = new Set(selectedTagIds);
    if (next.has(tagId)) next.delete(tagId);
    else next.add(tagId);
    onTagSelectionChange(next);
  };

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
          <span className="ml-auto text-[10px] text-slate-400">{filteredConcepts.length} concepts</span>
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
        {filteredConcepts.map((concept) => {
          const active = concept.id === activeConceptId;
          const sourceLabel = concept.sourceSurvey && concept.sourceItem
            ? `${concept.sourceSurvey} ${concept.sourceItem}`
            : concept.sourceItem;
          const badge = sourceLabel ?? `#${concept.id}`;
          return (
            <button
              key={concept.id}
              onClick={() => onConceptSelect(concept.id)}
              className={`group mb-0.5 flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition ${active ? 'bg-indigo-50 text-indigo-900' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${tagDot[concept.tag]}`} />
              <span className={`flex-1 text-[13px] ${active ? 'font-semibold' : 'font-medium'}`}>{concept.name}</span>
              <span className={`font-mono text-[10px] ${active ? 'text-indigo-400' : 'text-slate-300'}`}>{badge}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
