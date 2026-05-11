import { Flag } from 'lucide-react';
import type { CompareBundle } from '../../api/types';
import type { SpeakerForm } from '../../lib/speakerForm';
import { enumerateVariants, resolveActiveBucketForSpeaker } from '../../lib/compareBundles';
import { CognateCell, SimBar } from './CognateCell';
import { CanonicalLexemeCell } from './CanonicalLexemeCell';

export interface CompareBundleTableProps {
  bundle: CompareBundle;
  speakers: string[];
  speakerForms?: SpeakerForm[];
  primaryContactCodes?: string[];
  contactLanguageNames?: Record<string, string>;
  onBundleUpdated?: (bundle: CompareBundle) => void;
  onCycleCognate?: (speaker: string, current: string) => void;
  onResetCognate?: (speaker: string) => void;
  onToggleSpeakerFlag?: (speaker: string, current: boolean) => void;
}

export function CompareBundleTable({
  bundle,
  speakers,
  speakerForms = [],
  primaryContactCodes = [],
  contactLanguageNames = {},
  onBundleUpdated,
  onCycleCognate,
  onResetCognate,
  onToggleSpeakerFlag,
}: CompareBundleTableProps) {
  const formsBySpeaker = new Map(speakerForms.map((form) => [form.speaker, form]));
  const variants = enumerateVariants(bundle);

  return (
    <div className="space-y-4" data-testid="compare-bundle-table">
      <div className="rounded-lg border border-slate-100 bg-white p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Bundle</div>
            <h2 className="text-lg font-semibold text-slate-900">{bundle.label}</h2>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400">{bundle.row_ids.join(', ')}</div>
          </div>
          <div className="text-right text-[11px] text-slate-500">{bundle.buckets.length} bucket{bundle.buckets.length === 1 ? '' : 's'} · {variants.length} variant{variants.length === 1 ? '' : 's'}</div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full min-w-[760px] text-xs">
          <thead>
            <tr className="bg-slate-50/70 text-[10px] uppercase tracking-wider text-slate-500">
              <th className="px-3 py-2 text-left font-semibold">Speaker</th>
              <th className="px-3 py-2 text-left font-semibold">Canonical lexeme</th>
              {primaryContactCodes.map((code) => (
                <th key={code} className="px-3 py-2 text-left font-semibold" data-testid={`sim-col-header-${code}`}>
                  {(contactLanguageNames[code] ?? code.toUpperCase())} sim.
                </th>
              ))}
              <th className="px-3 py-2 text-left font-semibold">Cognate</th>
              <th className="px-3 py-2 text-right font-semibold">Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {speakers.map((speaker) => {
              const form = formsBySpeaker.get(speaker);
              const activeBucket = resolveActiveBucketForSpeaker(bundle, speaker);
              return (
                <tr key={speaker} data-testid={`speaker-row-${speaker}`} className="bg-white align-top">
                  <td className="px-3 py-2.5 font-mono text-[11px] font-medium text-slate-700">
                    <div>{speaker}</div>
                    {activeBucket && <div className="mt-1 text-[10px] font-normal text-slate-400">{activeBucket.survey_id.toUpperCase()} {activeBucket.source_item}</div>}
                  </td>
                  <td className="px-3 py-2.5">
                    <CanonicalLexemeCell bundle={bundle} speaker={speaker} onBundleUpdated={onBundleUpdated} />
                  </td>
                  {primaryContactCodes.map((code) => (
                    <td key={code} className="px-3 py-2.5" data-testid={`sim-cell-${speaker}-${code}`}>
                      <SimBar value={form?.similarityByLang[code] ?? null} />
                    </td>
                  ))}
                  <td className="px-3 py-2.5">
                    <CognateCell
                      speaker={speaker}
                      group={form?.cognate ?? '—'}
                      onCycle={() => onCycleCognate?.(speaker, form?.cognate ?? '—')}
                      onReset={() => onResetCognate?.(speaker)}
                    />
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      type="button"
                      data-testid={`speaker-flag-${speaker}`}
                      title={`Toggle flag for ${speaker}`}
                      onClick={() => onToggleSpeakerFlag?.(speaker, Boolean(form?.flagged))}
                      className={`inline-grid h-6 w-6 place-items-center rounded-md ${form?.flagged ? 'bg-amber-100 text-amber-600' : 'text-slate-300 hover:bg-slate-100 hover:text-slate-500'}`}
                    >
                      <Flag className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-100" data-testid="compare-variant-rows">
        {bundle.buckets.map((bucket) => (
          <div key={bucket.bucket_key}>
            <div className="bg-slate-50 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500" data-testid={`compare-bucket-${bucket.bucket_key}`}>
              {bucket.survey_id.toUpperCase()} · {bucket.source_item}
            </div>
            <div className="divide-y divide-slate-100 bg-white">
              {bucket.variants.map((variant) => {
                const label = variant.concept_en ?? variant.label ?? variant.variant_label ?? variant.csv_row_id;
                return (
                  <div key={variant.csv_row_id} className="grid grid-cols-[10rem_1fr] gap-3 px-3 py-2" data-testid={`compare-variant-${variant.csv_row_id}`}>
                    <div>
                      <div className="font-semibold text-slate-700">{label}</div>
                      <div className="font-mono text-[10px] text-slate-400">row {variant.csv_row_id}</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {speakers.map((speaker) => {
                        const candidate = bundle.candidates?.[speaker]?.[variant.csv_row_id] ?? null;
                        return (
                          <span key={speaker} className={`rounded border px-2 py-1 font-mono text-[11px] ${candidate ? 'border-slate-200 bg-slate-50 text-slate-700' : 'border-slate-100 bg-slate-50/50 text-slate-400'}`}>
                            {speaker}: {candidate?.ipa ? `/${candidate.ipa}/` : 'no form'}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
