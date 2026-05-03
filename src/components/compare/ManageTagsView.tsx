import React, { useMemo, useState } from 'react';
import { Check, Plus, Search, Tag } from 'lucide-react';

import { useTagStore } from '../../stores/tagStore';

export interface ManageTagsTag {
  id: string;
  name: string;
  color: string;
  dotClass: string;
  count: number;
}

export interface ManageTagsConcept {
  id: number;
  key: string;
  name: string;
  tag: 'untagged' | 'review' | 'confirmed' | 'problematic';
  sourceItem?: string;
  sourceSurvey?: string;
  customOrder?: number;
}

export interface ManageTagsViewProps {
  tags: ManageTagsTag[];
  concepts: ManageTagsConcept[];
  onCreateTag: (name: string, color: string) => void;
  onUpdateTag: (id: string, name: string) => void;
  tagSearch: string;
  setTagSearch: (s: string) => void;
  newTagName: string;
  setNewTagName: (s: string) => void;
  newTagColor: string;
  setNewTagColor: (s: string) => void;
  showUntagged: boolean;
  setShowUntagged: (b: boolean) => void;
  selectedTagId: string | null;
  setSelectedTagId: (s: string | null) => void;
  conceptSearch: string;
  setConceptSearch: (s: string) => void;
  tagConcept: (tagId: string, conceptKey: string) => void;
  untagConcept: (tagId: string, conceptKey: string) => void;
}

const SWATCHES = ['#6366f1', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#06b6d4', '#ec4899', '#64748b'];

const tagDotClass: Record<ManageTagsConcept['tag'], string> = {
  untagged: 'bg-slate-300',
  review: 'bg-amber-400',
  confirmed: 'bg-emerald-500',
  problematic: 'bg-rose-500',
};

export const ManageTagsView: React.FC<ManageTagsViewProps> = ({
  tags,
  concepts,
  onCreateTag,
  onUpdateTag,
  tagSearch,
  setTagSearch,
  newTagName,
  setNewTagName,
  newTagColor,
  setNewTagColor,
  showUntagged,
  setShowUntagged,
  selectedTagId,
  setSelectedTagId,
  conceptSearch,
  setConceptSearch,
  tagConcept,
  untagConcept,
}) => {
  const [editingTagId, setEditingTagId] = useState<string | null>(null);
  const [editingTagName, setEditingTagName] = useState('');
  const storeTags = useTagStore((s) => s.tags);
  const filteredTags = tags.filter((t) => t.name.toLowerCase().includes(tagSearch.toLowerCase()));
  const selectedTag = tags.find((t) => t.id === selectedTagId);
  const filteredConcepts = concepts.filter((c) => c.name.toLowerCase().includes(conceptSearch.toLowerCase()));
  const taggedKeys = useMemo<Set<string>>(() => {
    if (!selectedTagId) return new Set();
    const t = storeTags.find((s) => s.id === selectedTagId);
    return new Set(t?.concepts ?? []);
  }, [storeTags, selectedTagId]);

  return (
    <div className="flex flex-1 min-h-0 bg-slate-50">
      <div className="w-[360px] shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
        <div className="p-6">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Linguistic tags</h2>
          <p className="mt-1 text-xs text-slate-400">Organize concepts by review state, borrowing, or custom labels.</p>

          <div className="relative mt-5">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              value={tagSearch}
              onChange={(e) => setTagSearch(e.target.value)}
              placeholder="Filter tags…"
              className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-2 pl-9 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </div>

          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/40 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Create tag</div>
            <div className="mt-2 flex items-center gap-2">
              <input
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
                placeholder="New tag name…"
                className="flex-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              />
              <div className="relative">
                <div
                  className="h-7 w-7 rounded-md ring-2 ring-white"
                  style={{ background: newTagColor, boxShadow: '0 0 0 1px rgb(226 232 240)' }}
                />
              </div>
            </div>
            <div className="mt-2 flex gap-1.5">
              {SWATCHES.map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-label={`Select tag color ${c}`}
                  onClick={() => setNewTagColor(c)}
                  className={`h-5 w-5 rounded-full transition ${newTagColor === c ? 'ring-2 ring-offset-1 ring-slate-400' : 'ring-1 ring-slate-200 hover:scale-110'}`}
                  style={{ background: c }}
                />
              ))}
            </div>
            <button
              type="button"
              onClick={() => onCreateTag(newTagName, newTagColor)}
              disabled={!newTagName.trim()}
              className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-indigo-600 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200"
            >
              <Plus className="h-3 w-3" /> Create
            </button>
          </div>

          <div className="mt-5 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
            <span className="text-xs font-medium text-slate-700">Show untagged</span>
            <button
              type="button"
              aria-label="Toggle show untagged"
              onClick={() => setShowUntagged(!showUntagged)}
              className={`relative h-5 w-9 rounded-full transition ${showUntagged ? 'bg-indigo-600' : 'bg-slate-300'}`}
            >
              <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${showUntagged ? 'left-4' : 'left-0.5'}`} />
            </button>
          </div>

          <div className="mt-5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Tags · {filteredTags.length}</div>
            <div className="mt-2 space-y-1">
              {filteredTags.map((t) => {
                const active = selectedTagId === t.id;
                const editing = editingTagId === t.id;
                return (
                  <div key={t.id} className={`rounded-lg ${active ? 'bg-indigo-50 ring-1 ring-indigo-200' : 'hover:bg-slate-50'}`}>
                    <div className="flex items-center gap-2 px-3 py-2">
                      <button
                        type="button"
                        onClick={() => setSelectedTagId(t.id)}
                        className="group flex min-w-0 flex-1 items-center gap-3 text-left"
                      >
                        <span className="h-2.5 w-2.5 rounded-full ring-2 ring-white" style={{ background: t.color, boxShadow: '0 0 0 1px rgb(226 232 240)' }} />
                        <span className={`flex-1 truncate text-[13px] ${active ? 'font-semibold text-indigo-900' : 'font-medium text-slate-700'}`}>{t.name}</span>
                        <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">{t.count}</span>
                      </button>
                      <button
                        type="button"
                        aria-label="Edit tag"
                        onClick={() => {
                          setEditingTagId(t.id);
                          setEditingTagName(t.name);
                        }}
                        className="rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 hover:bg-white hover:text-slate-800"
                      >
                        Edit
                      </button>
                    </div>
                    {editing && (
                      <div className="border-t border-indigo-100 px-3 py-2">
                        <div className="flex items-center gap-2">
                          <input
                            aria-label="Rename tag"
                            value={editingTagName}
                            onChange={(e) => setEditingTagName(e.target.value)}
                            className="flex-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                          />
                          <button
                            type="button"
                            aria-label="Save tag"
                            onClick={() => {
                              if (!editingTagName.trim()) return;
                              onUpdateTag(t.id, editingTagName.trim());
                              setEditingTagId(null);
                              setEditingTagName('');
                            }}
                            className="rounded-md bg-indigo-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700"
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            aria-label="Cancel rename"
                            onClick={() => {
                              setEditingTagId(null);
                              setEditingTagName('');
                            }}
                            className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-1 min-h-0 flex-col">
        {!selectedTag ? (
          <div className="grid h-full place-items-center px-10 py-20">
            <div className="text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-50 to-violet-50 ring-1 ring-indigo-100">
                <Tag className="h-6 w-6 text-indigo-500" />
              </div>
              <h3 className="mt-5 text-lg font-semibold text-slate-900">Select a tag to assign concepts</h3>
              <p className="mt-2 max-w-md text-sm text-slate-500">
                Choose a linguistic tag on the left to browse and bulk-assign it across your {concepts.length} concepts.
                You can also create a new tag above.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="shrink-0 border-b border-slate-200 bg-white px-6 py-4">
              <div className="flex items-center gap-3">
                <span className="h-3 w-3 rounded-full ring-2 ring-white" style={{ background: selectedTag.color, boxShadow: '0 0 0 1px rgb(226 232 240)' }} />
                <h1 className="text-lg font-semibold tracking-tight text-slate-900">{selectedTag.name}</h1>
                <span className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-700">{selectedTag.count} concepts</span>
              </div>
              <div className="relative mt-3">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                <input
                  value={conceptSearch}
                  onChange={(e) => setConceptSearch(e.target.value)}
                  placeholder="Search concepts…"
                  className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-1.5 pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </div>
            </div>
            <nav className="flex-1 overflow-y-auto px-2 py-2">
              {filteredConcepts.map((c) => {
                const tagged = taggedKeys.has(c.key);
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => selectedTagId && (tagged ? untagConcept(selectedTagId, c.key) : tagConcept(selectedTagId, c.key))}
                    className={`group mb-0.5 flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition ${tagged ? 'bg-indigo-50 text-indigo-900' : 'text-slate-600 hover:bg-slate-50'}`}
                  >
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tagDotClass[c.tag]}`} />
                    <span className={`flex-1 text-[13px] ${tagged ? 'font-semibold' : 'font-medium'}`}>{c.name}</span>
                    <span className={`font-mono text-[10px] ${tagged ? 'text-indigo-400' : 'text-slate-300'}`}>#{c.id}</span>
                    {tagged && <Check className="h-3.5 w-3.5 shrink-0 text-indigo-500" />}
                  </button>
                );
              })}
            </nav>
          </>
        )}
      </div>
    </div>
  );
};
