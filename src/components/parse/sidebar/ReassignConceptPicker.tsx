import { useMemo, useState } from 'react';

export interface ReassignConceptOption {
  id: string;
  name: string;
}

interface ReassignConceptPickerProps {
  sourceName: string;
  options: readonly ReassignConceptOption[];
  onConfirm: (targetConceptId: string) => void;
  onCancel: () => void;
}

/**
 * Single-select concept picker for non-destructively moving one realization
 * (concept-tier interval) to a different concept. Mirrors ConceptMergePicker's
 * styling but returns exactly one target concept id and never deletes data.
 */
export function ReassignConceptPicker({ sourceName, options, onConfirm, onCancel }: ReassignConceptPickerProps) {
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase();
    if (!q) return options;
    return options.filter(
      (option) =>
        option.name.toLocaleLowerCase().includes(q) ||
        option.id.toLocaleLowerCase().includes(q),
    );
  }, [options, query]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-900/35 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Move recording from ${sourceName}`}
    >
      <div className="w-full max-w-lg rounded-xl bg-white p-4 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Move this recording to another concept</h2>
            <p className="mt-1 text-xs text-slate-500">
              Currently linked to <span className="font-medium">{sourceName}</span>. Pick the concept it actually
              belongs to — the recording and its IPA/orthography are kept; only the concept link changes.
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
          >
            Cancel
          </button>
        </div>

        <div className="mt-4">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search concepts…"
            aria-label="Search concepts"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
          <div className="mt-2 max-h-64 overflow-y-auto rounded-lg border border-slate-100">
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-xs text-slate-400">No matching concepts.</div>
            )}
            {filtered.map((option) => (
              <label
                key={option.id}
                className="flex cursor-pointer items-center gap-2 border-b border-slate-50 px-3 py-2 text-xs last:border-0 hover:bg-slate-50"
              >
                <input
                  type="radio"
                  name="reassign-target"
                  checked={selectedId === option.id}
                  onChange={() => setSelectedId(option.id)}
                  className="accent-indigo-600"
                />
                <span>{option.name}</span>
                <span className="ml-auto font-mono text-[10px] text-slate-400">{option.id}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!selectedId}
            onClick={() => {
              if (selectedId) onConfirm(selectedId);
            }}
            className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            Move recording
          </button>
        </div>
      </div>
    </div>
  );
}
