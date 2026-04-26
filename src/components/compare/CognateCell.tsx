import React from 'react';

const simColor = (v: number) =>
  v >= 0.8 ? 'text-emerald-600' : v >= 0.5 ? 'text-amber-600' : 'text-slate-400';
const simBar = (v: number) =>
  v >= 0.8 ? 'bg-emerald-500' : v >= 0.5 ? 'bg-amber-400' : 'bg-slate-300';

// null value == "no similarity score recorded for this speaker/concept/lang"
// -- either because the cognate compute hasn't run yet, or because the
// reference-forms dataset had no entry for this language. Rendering "—"
// instead of "0.00" keeps those two cases distinguishable, so the user
// knows to either run Populate or pick a different provider/language
// instead of concluding the speaker really has zero similarity.
export const SimBar: React.FC<{ value: number | null }> = ({ value }) => {
  if (value === null) {
    return (
      <div className="flex items-center gap-2" title="No similarity score yet — run Save & populate, or recompute cognate sets.">
        <div className="h-1.5 w-14 rounded-full bg-slate-100" />
        <span className="text-xs font-mono tabular-nums text-slate-300">—</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full rounded-full ${simBar(value)}`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className={`text-xs font-mono tabular-nums ${simColor(value)}`}>{value.toFixed(2)}</span>
    </div>
  );
};

// Per-speaker cognate cell. Click cycles A → B → … → Z → — → A. A long press
// (≥500 ms) resets to —. The button swallows the subsequent click after a
// long-press fires so cycle doesn't also run.
export const COGNATE_COLORS: Record<string, string> = {
  A: 'bg-indigo-100 text-indigo-700',
  B: 'bg-violet-100 text-violet-700',
  C: 'bg-fuchsia-100 text-fuchsia-700',
  D: 'bg-rose-100 text-rose-700',
  E: 'bg-orange-100 text-orange-700',
  F: 'bg-amber-100 text-amber-700',
  G: 'bg-lime-100 text-lime-700',
  H: 'bg-emerald-100 text-emerald-700',
  I: 'bg-teal-100 text-teal-700',
  J: 'bg-cyan-100 text-cyan-700',
  K: 'bg-sky-100 text-sky-700',
  L: 'bg-blue-100 text-blue-700',
  M: 'bg-indigo-200 text-indigo-800',
  N: 'bg-violet-200 text-violet-800',
  O: 'bg-fuchsia-200 text-fuchsia-800',
  P: 'bg-rose-200 text-rose-800',
  Q: 'bg-orange-200 text-orange-800',
  R: 'bg-amber-200 text-amber-800',
  S: 'bg-lime-200 text-lime-800',
  T: 'bg-emerald-200 text-emerald-800',
  U: 'bg-teal-200 text-teal-800',
  V: 'bg-cyan-200 text-cyan-800',
  W: 'bg-sky-200 text-sky-800',
  X: 'bg-blue-200 text-blue-800',
  Y: 'bg-slate-200 text-slate-800',
  Z: 'bg-stone-200 text-stone-800',
};

export const CognateCell: React.FC<{
  speaker: string;
  group: string;
  onCycle: () => void;
  onReset: () => void;
}> = ({ speaker, group, onCycle, onReset }) => {
  const timerRef = React.useRef<number | null>(null);
  const longPressFiredRef = React.useRef(false);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const startPress = () => {
    longPressFiredRef.current = false;
    clearTimer();
    timerRef.current = window.setTimeout(() => {
      longPressFiredRef.current = true;
      onReset();
    }, 500);
  };

  const cancelPress = () => {
    clearTimer();
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (longPressFiredRef.current) {
      longPressFiredRef.current = false;
      return;
    }
    onCycle();
  };

  const colorClass = /^[A-Z]$/.test(group)
    ? COGNATE_COLORS[group] ?? 'bg-slate-200 text-slate-800'
    : 'bg-slate-100 text-slate-400';

  const next = group === '—' || !/^[A-Z]$/.test(group) ? 'A'
    : group === 'Z' ? '—'
    : String.fromCharCode(group.charCodeAt(0) + 1);

  return (
    <button
      data-testid={`cognate-cycle-${speaker}`}
      title={`Click cycles → ${next} · Long-press resets to —`}
      onPointerDown={startPress}
      onPointerUp={cancelPress}
      onPointerLeave={cancelPress}
      onPointerCancel={cancelPress}
      onClick={handleClick}
      className={`inline-flex h-5 min-w-[24px] items-center justify-center rounded px-1 font-mono text-[10px] font-bold hover:ring-2 hover:ring-slate-300 ${colorClass}`}
    >
      {group}
    </button>
  );
};
