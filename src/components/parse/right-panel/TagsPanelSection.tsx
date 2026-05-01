import { useMemo, useState } from 'react';
import { Check, Plus, Search, Tag as TagIcon } from 'lucide-react';

import { useConceptTagIds, useTagsStore, useTagUsageCounts, type Tag } from '@/state/tags';

const COLOR_SWATCHES = ['#3554B8', '#0f766e', '#7c3aed', '#b45309', '#be123c', '#475569'] as const;

interface TagsPanelSectionProps {
  conceptId: string;
}

export function TagsPanelSection({ conceptId }: TagsPanelSectionProps) {
  const tags = useTagsStore((state) => state.tags);
  const attachTag = useTagsStore((state) => state.attachTag);
  const detachTag = useTagsStore((state) => state.detachTag);
  const createTag = useTagsStore((state) => state.createTag);
  const conceptTagIds = useConceptTagIds(conceptId);
  const counts = useTagUsageCounts();
  const [search, setSearch] = useState('');

  const appliedIds = useMemo(() => new Set(conceptTagIds), [conceptTagIds]);
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return tags;
    return tags.filter((tag) => tag.name.toLowerCase().includes(needle));
  }, [search, tags]);

  return (
    <section className="border-b border-slate-100 p-4" aria-labelledby="concept-tags-title">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 id="concept-tags-title" className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <TagIcon className="h-3 w-3" /> Concept tags
        </h4>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[9px] text-slate-500" aria-label="Applied concept tags">
          {appliedIds.size} of {tags.length}
        </span>
      </div>
      <p className="mb-3 text-[10px] leading-snug text-slate-400">
        Tags travel with the concept across speakers. Counts show usage in this dataset.
      </p>

      <label className="mb-2 flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[11px] text-slate-500 focus-within:border-indigo-300 focus-within:ring-1 focus-within:ring-indigo-100">
        <Search className="h-3 w-3 text-slate-400" />
        <span className="sr-only">Search tags</span>
        <input
          className="tag-search min-w-0 flex-1 bg-transparent text-[11px] text-slate-700 outline-none placeholder:text-slate-400"
          placeholder="Search tags..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label="Search tags"
        />
      </label>

      <div className="space-y-1" aria-label="Concept tag list">
        {filtered.length > 0 ? (
          filtered.map((tag) => {
            const checked = appliedIds.has(tag.id);
            return (
              <TagRow
                key={tag.id}
                tag={tag}
                checked={checked}
                count={counts[tag.id] ?? 0}
                onToggle={() => {
                  const action = checked ? detachTag(conceptId, tag.id) : attachTag(conceptId, tag.id);
                  void action.catch((error: unknown) => console.warn('[tags] update failed', error));
                }}
              />
            );
          })
        ) : (
          <p className="rounded-md border border-dashed border-slate-200 px-2.5 py-2 text-[10px] text-slate-400">
            {tags.length === 0 ? 'No tags yet. Create one below.' : 'No tags match this search.'}
          </p>
        )}
      </div>

      <CreateTagInline onCreate={createTag} />
    </section>
  );
}

function TagRow({ tag, checked, count, onToggle }: {
  tag: Tag;
  checked: boolean;
  count: number;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={`tag-row flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition hover:bg-slate-50 ${checked ? 'checked bg-indigo-50 text-indigo-900 ring-1 ring-indigo-100' : 'text-slate-700'}`}
      onClick={onToggle}
      aria-pressed={checked}
    >
      <span className="check grid h-3.5 w-3.5 place-items-center rounded border border-slate-300 bg-white text-[9px] text-indigo-700" aria-hidden="true">
        {checked ? <Check className="h-2.5 w-2.5" /> : null}
      </span>
      <span className="tag-dot h-2.5 w-2.5 rounded-full ring-1 ring-black/10" style={{ backgroundColor: tag.color }} aria-hidden="true" />
      <span className="tag-name min-w-0 flex-1 truncate text-[11px] font-medium">{tag.name}</span>
      <span className="tag-count rounded bg-white/80 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">{count}</span>
    </button>
  );
}

function CreateTagInline({ onCreate }: { onCreate: (name: string, color: string) => Promise<Tag> }) {
  const [expanded, setExpanded] = useState(false);
  const [name, setName] = useState('');
  const [color, setColor] = useState<string>(COLOR_SWATCHES[0]);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await onCreate(trimmed, color);
      setName('');
      setColor(COLOR_SWATCHES[0]);
      setExpanded(false);
    } catch (error) {
      console.warn('[tags] create failed', error);
    } finally {
      setBusy(false);
    }
  };

  if (!expanded) {
    return (
      <button
        type="button"
        className="mt-2 flex w-full items-center gap-2 rounded-md border border-dashed border-slate-200 px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-500 transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700"
        onClick={() => setExpanded(true)}
      >
        <Plus className="h-3 w-3" /> Create tag
      </button>
    );
  }

  return (
    <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-2" data-testid="create-tag-form">
      <input
        className="mb-2 w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-[11px] text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-1 focus:ring-indigo-100"
        placeholder="Tag name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        aria-label="Tag name"
      />
      <div className="mb-2 flex flex-wrap gap-1" aria-label="Tag color">
        {COLOR_SWATCHES.map((swatch) => (
          <button
            key={swatch}
            type="button"
            className={`h-5 w-5 rounded-full ring-1 ring-black/10 ${color === swatch ? 'outline outline-2 outline-offset-1 outline-indigo-400' : ''}`}
            style={{ backgroundColor: swatch }}
            aria-label={`Use color ${swatch}`}
            aria-pressed={color === swatch}
            onClick={() => setColor(swatch)}
          />
        ))}
      </div>
      <div className="flex gap-1.5">
        <button
          type="button"
          className="flex-1 rounded bg-indigo-600 px-2 py-1 text-[10px] font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!name.trim() || busy}
          onClick={() => { void submit(); }}
        >
          {busy ? 'Creating...' : 'Create'}
        </button>
        <button
          type="button"
          className="rounded px-2 py-1 text-[10px] font-medium text-slate-500 hover:bg-slate-100"
          onClick={() => setExpanded(false)}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
