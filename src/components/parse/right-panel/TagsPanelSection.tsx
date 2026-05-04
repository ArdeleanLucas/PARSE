import { useMemo, useState } from 'react';
import { Check, Plus, Search, Tag as TagIcon } from 'lucide-react';

import { useTagStore } from '@/stores/tagStore';
import type { Tag } from '@/api/types';

const COLOR_SWATCHES = ['#3554B8', '#0f766e', '#7c3aed', '#b45309', '#be123c', '#475569'] as const;

interface TagsPanelSectionProps {
  conceptId: string;
}

export function TagsPanelSection({ conceptId }: TagsPanelSectionProps) {
  const tags = useTagStore((state) => state.tags);
  const addTag = useTagStore((state) => state.addTag);
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return tags;
    return tags.filter((tag) => tag.label.toLowerCase().includes(needle));
  }, [search, tags]);

  return (
    <section className="border-b border-slate-100 p-4" aria-labelledby="concept-tags-title">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 id="concept-tags-title" className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <TagIcon className="h-3 w-3" /> Concept Tags
        </h4>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[9px] text-slate-500" aria-label="Tag vocabulary size">
          {tags.length} tag{tags.length === 1 ? '' : 's'}
        </span>
      </div>
      <p className="mb-3 text-[10px] leading-snug text-slate-400">
        Tags are vocabulary only here; speaker-specific membership lives on each annotation record.
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

      <div className="space-y-1" aria-label="Concept tag list" data-concept-id={conceptId}>
        {filtered.length > 0 ? (
          filtered.map((tag) => <TagRow key={tag.id} tag={tag} />)
        ) : (
          <p className="rounded-md border border-dashed border-slate-200 px-2.5 py-2 text-[10px] text-slate-400">
            {tags.length === 0 ? 'No tags yet. Create one below.' : 'No tags match this search.'}
          </p>
        )}
      </div>

      <CreateTagInline onCreate={addTag} />
    </section>
  );
}

function TagRow({ tag }: { tag: Tag }) {
  return (
    <div
      className="tag-row flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-slate-700"
    >
      <span className="check grid h-3.5 w-3.5 place-items-center rounded border border-slate-300 bg-white text-[9px] text-transparent" aria-hidden="true">
        <Check className="h-2.5 w-2.5" />
      </span>
      <span className="tag-dot h-2.5 w-2.5 rounded-full ring-1 ring-black/10" style={{ backgroundColor: tag.color }} aria-hidden="true" />
      <span className="tag-name min-w-0 flex-1 truncate text-[11px] font-medium">{tag.label}</span>
    </div>
  );
}

function CreateTagInline({ onCreate }: { onCreate: (label: string, color: string) => Tag }) {
  const [expanded, setExpanded] = useState(false);
  const [name, setName] = useState('');
  const [color, setColor] = useState<string>(COLOR_SWATCHES[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      onCreate(trimmed, color);
      setName('');
      setExpanded(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      console.warn('[TagsPanelSection] create tag failed:', err);
    } finally {
      setBusy(false);
    }
  };

  if (!expanded) {
    return (
      <button
        type="button"
        className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-slate-200 px-2 py-1.5 text-[11px] font-medium text-slate-500 transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700"
        onClick={() => setExpanded(true)}
      >
        <Plus className="h-3 w-3" /> Create tag
      </button>
    );
  }

  return (
    <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-2">
      <input
        className="mb-2 w-full rounded border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 outline-none focus:border-indigo-300"
        placeholder="Tag name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        autoFocus
      />
      <div className="mb-2 flex flex-wrap gap-1">
        {COLOR_SWATCHES.map((swatch) => (
          <button
            key={swatch}
            type="button"
            className={`h-5 w-5 rounded-full ring-2 ${color === swatch ? 'ring-slate-700' : 'ring-transparent'}`}
            style={{ backgroundColor: swatch }}
            aria-label={`Use color ${swatch}`}
            onClick={() => setColor(swatch)}
          />
        ))}
      </div>
      <div className="flex gap-1.5">
        <button
          type="button"
          disabled={busy || !name.trim()}
          onClick={() => void submit()}
          className="flex-1 rounded bg-indigo-600 px-2 py-1 text-[11px] font-medium text-white disabled:bg-slate-300"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => {
            setExpanded(false);
            setName('');
            setError(null);
          }}
          className="rounded border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600"
        >
          Cancel
        </button>
      </div>
      {error && <p className="mt-1 text-[10px] text-rose-600">{error}</p>}
    </div>
  );
}
