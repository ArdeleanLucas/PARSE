import { useState } from 'react';
import type { CompareBundle } from '../../api/types';
import { activeCandidateFor, canonicalFor } from '../../lib/compareBundles';
import { CanonicalPicker } from './CanonicalPicker';

export interface CanonicalLexemeCellProps {
  bundle: CompareBundle;
  speaker: string;
  onBundleUpdated?: (bundle: CompareBundle) => void;
}

export function CanonicalLexemeCell({ bundle, speaker, onBundleUpdated }: CanonicalLexemeCellProps) {
  const [open, setOpen] = useState(false);
  const canonical = canonicalFor(bundle, speaker);
  const candidate = activeCandidateFor(bundle, speaker);
  const hasAnyCandidate = Object.values(bundle.candidates?.[speaker] ?? {}).some(Boolean);

  const statusLabel = !hasAnyCandidate
    ? 'no form for this speaker'
    : canonical
      ? canonical.source === 'manual'
        ? 'manual'
        : canonical.source === 'migration:canonical_realizations'
          ? 'migrated — confirm'
          : 'auto'
      : 'no canonical chosen';

  return (
    <div className="min-w-[150px]" data-testid={`canonical-cell-${speaker}-${bundle.bundle_id}`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={`Choose canonical lexeme for ${speaker}`}
        className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-left hover:border-indigo-200 hover:bg-indigo-50/30"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[12px] text-indigo-700">{candidate?.ipa ? `/${candidate.ipa}/` : '—'}</span>
          {canonical?.source === 'manual' && <span className="text-[11px] font-bold text-indigo-600">✓</span>}
        </div>
        <div className="mt-0.5 truncate text-[10px] text-slate-500">{candidate?.ortho ?? statusLabel}</div>
        {canonical?.source === 'migration:canonical_realizations' && (
          <div className="mt-0.5 text-[10px] text-amber-700">migrated — confirm</div>
        )}
        {canonical?.source === 'default:single-candidate' && (
          <div className="mt-0.5 text-[10px] text-slate-400">(auto)</div>
        )}
        {!canonical && hasAnyCandidate && (
          <div className="mt-0.5 text-[10px] font-semibold text-indigo-600">open picker</div>
        )}
      </button>
      {open && (
        <CanonicalPicker
          bundle={bundle}
          speaker={speaker}
          onBundleUpdated={onBundleUpdated}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}
