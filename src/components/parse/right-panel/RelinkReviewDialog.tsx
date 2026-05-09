import { useEffect, useMemo, useState } from 'react';

import type { RelinkByGlossGroup, RelinkByGlossRequest, RelinkByGlossResponse } from '../../../api/types';

interface RelinkReviewDialogProps {
  response: RelinkByGlossResponse;
  onApply: (acceptedGroups: NonNullable<RelinkByGlossRequest['accepted_groups']>) => void;
  onCancel: () => void;
}

function groupKey(group: RelinkByGlossGroup): string {
  return `${group.keep_concept_id}:${group.merge_concept_ids.join(',')}`;
}

function displayLabel(group: RelinkByGlossGroup, conceptId: string): string {
  const label = group.labels?.[conceptId];
  return label ? `${conceptId} ${label}` : conceptId;
}

function displayGroupName(group: RelinkByGlossGroup): string {
  return group.canonical_gloss ?? group.labels?.[group.keep_concept_id] ?? group.keep_concept_id;
}

export function humanizeRelinkKeepReason(reason?: string): string {
  if (!reason) return 'keep rule';
  if (reason === 'lowest_numeric_id') return 'lowest id';
  if (reason === 'metadata_rich_over_lowest_empty') return 'metadata-rich';
  return reason.replace(/_/g, ' ');
}

function plural(count: number, singular: string, pluralLabel = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralLabel}`;
}

export function RelinkReviewDialog({ response, onApply, onCancel }: RelinkReviewDialogProps) {
  const [checkedKeys, setCheckedKeys] = useState<Set<string>>(() => new Set(response.groups.map(groupKey)));

  useEffect(() => {
    setCheckedKeys(new Set(response.groups.map(groupKey)));
  }, [response]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onCancel]);

  const selectedGroups = useMemo(
    () => response.groups.filter((group) => checkedKeys.has(groupKey(group))),
    [checkedKeys, response.groups],
  );
  const selectedPayload = selectedGroups.map((group) => ({
    keep_concept_id: group.keep_concept_id,
    merge_concept_ids: group.merge_concept_ids,
  }));
  const hasStrictGroups = response.groups.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-900/35 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="relink-review-title"
        className="flex max-h-[82vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
      >
        <header className="border-b border-slate-200 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="relink-review-title" className="text-sm font-semibold text-slate-800">
              Review cross-survey concept merges
            </h2>
            <div className="flex flex-wrap gap-1.5 text-[10px] font-semibold text-slate-500">
              <span className="rounded bg-indigo-50 px-2 py-0.5 text-indigo-700">{plural(response.groups.length, 'strict group')}</span>
              <span className="rounded bg-amber-50 px-2 py-0.5 text-amber-700">{plural(response.fuzzy_candidates.length, 'fuzzy candidate')}</span>
              <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-slate-600">{response.algorithm}</span>
            </div>
          </div>
          <p className="mt-1 text-[11px] text-slate-500">
            Review each strict merge before applying. Fuzzy candidates are informational only and require manual relabel.
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <section className="space-y-2" aria-label="Strict merge groups">
            {hasStrictGroups ? response.groups.map((group) => {
              const key = groupKey(group);
              const name = displayGroupName(group);
              const checked = checkedKeys.has(key);
              return (
                <div key={key} data-testid={`relink-group-${group.keep_concept_id}`} className="rounded-lg border border-slate-200 bg-white p-3 text-[11px] shadow-sm">
                  <div className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600"
                      aria-label={`Include ${name}`}
                      checked={checked}
                      onChange={(event) => {
                        setCheckedKeys((current) => {
                          const next = new Set(current);
                          if (event.target.checked) next.add(key);
                          else next.delete(key);
                          return next;
                        });
                      }}
                    />
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-semibold text-slate-800">{name}</span>
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">algorithm {response.algorithm}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 text-slate-600">
                        <span>keep</span>
                        <span className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 font-mono text-emerald-700">{displayLabel(group, group.keep_concept_id)}</span>
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">{humanizeRelinkKeepReason(group.keep_reason)}</span>
                      </div>
                      <div className="font-mono text-slate-700">
                        merge {group.merge_concept_ids.map((id) => displayLabel(group, id)).join(', ')}
                      </div>
                      {group.links_by_survey && Object.keys(group.links_by_survey).length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(group.links_by_survey).map(([surveyId, sourceItem]) => (
                            <span key={`${surveyId}:${sourceItem}`} className="rounded-full bg-indigo-50 px-2 py-0.5 font-mono text-[10px] font-semibold text-indigo-700">
                              {surveyId} {sourceItem}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            }) : (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-500">
                No strict merge groups were proposed. Review fuzzy candidates below for manual relabel candidates.
              </div>
            )}
          </section>

          {response.fuzzy_candidates.length > 0 ? (
            <section className="mt-3 space-y-2" aria-label="Fuzzy candidates">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Fuzzy candidates</h3>
              {response.fuzzy_candidates.map((candidate, index) => (
                <div key={`${candidate.incoming_label}:${candidate.candidate_label}:${index}`} data-testid={`relink-fuzzy-${index}`} className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-[11px] text-slate-700">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-slate-800">{candidate.incoming_label}</span>
                    <span className="text-slate-400">↔</span>
                    <span className="font-semibold text-slate-800">{candidate.candidate_label}</span>
                    {candidate.candidate_concept_id ? <span className="rounded bg-white px-1.5 py-0.5 font-mono text-[10px] text-slate-500">{candidate.candidate_concept_id}</span> : null}
                    <span className="rounded bg-white px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">{candidate.reason.replace(/_/g, ' ')}</span>
                  </div>
                  <p className="mt-1 text-[10px] text-amber-700">Requires manual relabel; fuzzy candidates are never applied automatically.</p>
                </div>
              ))}
            </section>
          ) : null}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-slate-200 px-4 py-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-slate-200 px-3 py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
          >
            Cancel
          </button>
          {hasStrictGroups ? (
            <button
              type="button"
              disabled={selectedGroups.length === 0}
              onClick={() => onApply(selectedPayload)}
              className="rounded bg-indigo-600 px-3 py-1.5 text-[11px] font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              Apply selected ({selectedGroups.length})
            </button>
          ) : null}
        </footer>
      </div>
    </div>
  );
}
