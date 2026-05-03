import { useMemo, useState } from 'react';
import type { Concept } from '../../../lib/speakerForm';

interface ConceptMergePickerProps {
  primary: Concept;
  concepts: readonly Concept[];
  onConfirm: (absorbedKeys: string[]) => void;
  onCancel: () => void;
}

function normalizeStem(label: string): string {
  return label
    .replace(/\s*\(([A-Z])\)\s*$/i, '')
    .replace(/\s+[A-Z]\s*$/i, '')
    .trim()
    .toLocaleLowerCase();
}

function conceptUnderlyingKeys(concept: Concept): string[] {
  return concept.variants?.map((variant) => variant.conceptKey) ?? [concept.key];
}

export function ConceptMergePicker({ primary, concepts, onConfirm, onCancel }: ConceptMergePickerProps) {
  const [query, setQuery] = useState('');
  const suggestedKeys = useMemo(() => {
    const primaryStem = normalizeStem(primary.name);
    if (!primaryStem) return new Set<string>();
    return new Set(concepts
      .filter((concept) => concept.id !== primary.id && normalizeStem(concept.name) === primaryStem)
      .map((concept) => concept.key));
  }, [concepts, primary]);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set(suggestedKeys));

  const filteredConcepts = useMemo(() => {
    const q = query.trim().toLocaleLowerCase();
    return concepts.filter((concept) => {
      if (concept.id === primary.id) return false;
      if (!q) return true;
      return concept.name.toLocaleLowerCase().includes(q) || concept.key.toLocaleLowerCase().includes(q);
    });
  }, [concepts, primary.id, query]);

  const selectedConcepts = concepts.filter((concept) => selectedKeys.has(concept.key));
  const toggle = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/35 p-4" role="dialog" aria-modal="true" aria-label={`Merge into ${primary.name}`}>
      <div className="w-full max-w-lg rounded-xl bg-white p-4 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Merge into {primary.name}</h2>
            <p className="mt-1 text-xs text-slate-500">Selected concepts collapse into this sidebar entry. Underlying concept ids stay intact.</p>
          </div>
          <button type="button" onClick={onCancel} className="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">Cancel</button>
        </div>

        {suggestedKeys.size > 0 && (
          <section className="mt-4 rounded-lg border border-indigo-100 bg-indigo-50/50 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-indigo-700">Suggested stem matches</h3>
              <button
                type="button"
                onClick={() => setSelectedKeys(new Set(suggestedKeys))}
                className="rounded bg-indigo-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-indigo-700"
              >
                Merge with all {suggestedKeys.size} suggested
              </button>
            </div>
            <div className="space-y-1">
              {concepts.filter((concept) => suggestedKeys.has(concept.key)).map((concept) => (
                <label key={concept.key} className="flex items-center gap-2 text-xs text-slate-700">
                  <input type="checkbox" checked={selectedKeys.has(concept.key)} onChange={() => toggle(concept.key)} className="accent-indigo-600" />
                  <span>{concept.name}</span>
                  <span className="ml-auto font-mono text-[10px] text-slate-400">{conceptUnderlyingKeys(concept).join(', ')}</span>
                </label>
              ))}
            </div>
          </section>
        )}

        <div className="mt-4">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search concepts to merge…"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
          <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-slate-100">
            {filteredConcepts.map((concept) => (
              <label key={concept.key} className="flex cursor-pointer items-center gap-2 border-b border-slate-50 px-3 py-2 text-xs last:border-0 hover:bg-slate-50">
                <input type="checkbox" checked={selectedKeys.has(concept.key)} onChange={() => toggle(concept.key)} className="accent-indigo-600" />
                <span>{concept.name}</span>
                <span className="ml-auto font-mono text-[10px] text-slate-400">{conceptUnderlyingKeys(concept).join(', ')}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
          {selectedConcepts.length > 0 ? `Selected: ${selectedConcepts.map((concept) => concept.name).join(', ')}` : 'Select at least one concept to merge.'}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100">Cancel</button>
          <button
            type="button"
            disabled={selectedKeys.size === 0}
            onClick={() => onConfirm(Array.from(selectedKeys))}
            className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            Merge {selectedKeys.size} concepts
          </button>
        </div>
      </div>
    </div>
  );
}
