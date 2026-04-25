import { Search } from 'lucide-react';
import { surveyBadgePrefix } from '../../lib/surveySort';

type ConceptTag = 'untagged' | 'review' | 'confirmed' | 'problematic';
type ConceptSortMode = 'az' | '1n' | 'survey';
type ConceptTagFilter = 'all' | 'unreviewed' | 'flagged' | 'borrowings' | 'untagged' | 'review' | 'confirmed' | 'problematic' | string;

interface SidebarConcept {
  id: number;
  name: string;
  tag: ConceptTag;
  surveyItem?: string;
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
  hasSurveyItems: boolean;
  filteredConcepts: SidebarConcept[];
  tagFilter: ConceptTagFilter;
  onTagFilterChange: (filter: ConceptTagFilter) => void;
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
  hasSurveyItems,
  filteredConcepts,
  tagFilter,
  onTagFilterChange,
  tags,
  activeConceptId,
  onConceptSelect,
}: ConceptSidebarProps) {
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
              disabled={!hasSurveyItems}
              title={hasSurveyItems ? 'Sort by original survey item (section.item)' : 'No survey_item values present in concepts.csv'}
              className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode === 'survey' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'} ${!hasSurveyItems ? 'cursor-not-allowed opacity-40' : ''}`}
            >
              Survey
            </button>
          </div>
          <span className="ml-auto text-[10px] text-slate-400">{filteredConcepts.length} concepts</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          <button
            onClick={() => onTagFilterChange('all')}
            data-testid="tagfilter-all"
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === 'all' ? 'bg-slate-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
          >
            All
          </button>
          <button
            onClick={() => onTagFilterChange(tagFilter === 'unreviewed' ? 'all' : 'unreviewed')}
            title="Concepts not yet confirmed and without a cognate assignment"
            data-testid="tagfilter-unreviewed"
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === 'unreviewed' ? 'bg-amber-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tagFilter === 'unreviewed' ? 'bg-white' : 'bg-amber-400'}`} />
            Unreviewed
          </button>
          <button
            onClick={() => onTagFilterChange(tagFilter === 'flagged' ? 'all' : 'flagged')}
            title="Concepts tagged problematic, or with a flagged speaker utterance"
            data-testid="tagfilter-flagged"
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === 'flagged' ? 'bg-rose-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tagFilter === 'flagged' ? 'bg-white' : 'bg-rose-400'}`} />
            Flagged
          </button>
          <button
            onClick={() => onTagFilterChange(tagFilter === 'borrowings' ? 'all' : 'borrowings')}
            title="Concepts with at least one borrowing"
            data-testid="tagfilter-borrowings"
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === 'borrowings' ? 'bg-violet-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tagFilter === 'borrowings' ? 'bg-white' : 'bg-violet-400'}`} />
            Borrowings
          </button>
          {tags.map((tag) => (
            <button
              key={tag.id}
              onClick={() => onTagFilterChange(tagFilter === tag.id ? 'all' : tag.id)}
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === tag.id ? 'text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
              style={tagFilter === tag.id ? { background: tag.color } : {}}
            >
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: tag.color }} />
              {tag.name}
            </button>
          ))}
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-6">
        {filteredConcepts.map((concept) => {
          const active = concept.id === activeConceptId;
          const badge = sortMode === 'survey' && concept.surveyItem ? concept.surveyItem : String(concept.id);
          const badgePrefix = surveyBadgePrefix(sortMode);
          return (
            <button
              key={concept.id}
              onClick={() => onConceptSelect(concept.id)}
              className={`group mb-0.5 flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition ${active ? 'bg-indigo-50 text-indigo-900' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${tagDot[concept.tag]}`} />
              <span className={`flex-1 text-[13px] ${active ? 'font-semibold' : 'font-medium'}`}>{concept.name}</span>
              <span className={`font-mono text-[10px] ${active ? 'text-indigo-400' : 'text-slate-300'}`}>{badgePrefix}{badge}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
