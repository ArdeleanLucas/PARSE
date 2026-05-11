import { useMemo, useState } from 'react';
import { deleteCanonicalLexeme, putCanonicalLexeme } from '../../api/client';
import type { CanonicalLexemeSelection, CompareBundle } from '../../api/types';
import { canonicalFor, enumerateVariants } from '../../lib/compareBundles';
import { useEnrichmentStore } from '../../stores/enrichmentStore';

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    const match = error.message.match(/repair_hint["']?\s*[:=]\s*["']([^"']+)/i);
    return match?.[1] ?? error.message;
  }
  return 'Could not save canonical lexeme.';
}

export interface CanonicalPickerProps {
  bundle: CompareBundle;
  speaker: string;
  onBundleUpdated?: (bundle: CompareBundle) => void;
  onClose?: () => void;
}

export function CanonicalPicker({ bundle, speaker, onBundleUpdated, onClose }: CanonicalPickerProps) {
  const current = canonicalFor(bundle, speaker);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(current?.csv_row_id ?? null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const variants = useMemo(() => enumerateVariants(bundle), [bundle]);

  const selectedEntry = variants.find(({ variant }) => variant.csv_row_id === selectedRowId) ?? null;
  const selectedCandidate = selectedRowId ? bundle.candidates?.[speaker]?.[selectedRowId] ?? null : null;

  async function saveSelection() {
    if (!selectedRowId || !selectedEntry) return;
    setSaving(true);
    setError(null);
    try {
      const response = await putCanonicalLexeme(bundle.bundle_id, speaker, {
        csv_row_id: selectedRowId,
        realization_index: selectedCandidate?.realization_index,
      });
      const nextSelection: CanonicalLexemeSelection = response.bundle.canonical?.[speaker] ?? {
        csv_row_id: selectedRowId,
        survey_id: selectedEntry.variant.survey_id ?? selectedEntry.bucket.survey_id,
        source_item: selectedEntry.variant.source_item ?? selectedEntry.bucket.source_item,
        bucket_key: selectedEntry.bucket.bucket_key,
        realization_index: selectedCandidate?.realization_index,
        source: 'manual',
        selected_at: '',
      };
      useEnrichmentStore.getState().patchCanonicalLexeme(bundle.bundle_id, speaker, nextSelection);
      onBundleUpdated?.(response.bundle);
      onClose?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function clearSelection() {
    setSaving(true);
    setError(null);
    try {
      const response = await deleteCanonicalLexeme(bundle.bundle_id, speaker);
      useEnrichmentStore.getState().patchCanonicalLexeme(bundle.bundle_id, speaker, null);
      onBundleUpdated?.(response.bundle);
      setSelectedRowId(null);
      onClose?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-2 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3" data-testid={`canonical-picker-${speaker}`}>
      {current?.source === 'migration:canonical_realizations' && (
        <div className="mb-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800" data-testid={`canonical-migration-hint-${speaker}`}>
          Migrated legacy choice — confirm or change.
        </div>
      )}
      {current?.source === 'default:single-candidate' && (
        <div className="mb-2 text-[11px] text-slate-500" data-testid={`canonical-auto-hint-${speaker}`}>
          Auto-picked single candidate. Save to confirm it manually.
        </div>
      )}
      <div className="space-y-1.5">
        {variants.map(({ bucket, variant }) => {
          const candidate = bundle.candidates?.[speaker]?.[variant.csv_row_id] ?? null;
          const missingForm = candidate === null;
          const label = variant.variant_label ?? variant.concept_en ?? variant.label ?? variant.csv_row_id;
          return (
            <label
              key={`${bucket.bucket_key}:${variant.csv_row_id}`}
              title={missingForm ? `selected canonical for ${speaker} has no recorded form` : undefined}
              className={`flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-[11px] ${missingForm ? 'border-slate-100 bg-white/60 text-slate-400 opacity-70' : 'border-slate-200 bg-white text-slate-700'}`}
              data-testid={`canonical-option-${speaker}-${variant.csv_row_id}`}
            >
              <input
                type="radio"
                name={`canonical-${bundle.bundle_id}-${speaker}`}
                checked={selectedRowId === variant.csv_row_id}
                onChange={() => setSelectedRowId(variant.csv_row_id)}
                className="h-3.5 w-3.5 accent-indigo-600"
              />
              <span className="min-w-[3rem] font-mono text-[10px] text-slate-400">{variant.csv_row_id}</span>
              <span className="font-semibold">{label}</span>
              <span className="text-slate-400">{bucket.survey_id.toUpperCase()} {bucket.source_item}</span>
              <span className="ml-auto font-mono">{candidate?.ipa ? `/${candidate.ipa}/` : missingForm ? 'no form' : 'candidate'}</span>
            </label>
          );
        })}
      </div>
      {error && <div className="mt-2 rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700" data-testid={`canonical-error-${speaker}`}>{error}</div>}
      <div className="mt-3 flex items-center justify-end gap-2">
        <button type="button" onClick={onClose} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50">Cancel</button>
        <button type="button" onClick={clearSelection} disabled={saving} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50">Clear</button>
        <button type="button" onClick={saveSelection} disabled={saving || !selectedRowId} className="rounded-md bg-indigo-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">Save</button>
      </div>
    </div>
  );
}
