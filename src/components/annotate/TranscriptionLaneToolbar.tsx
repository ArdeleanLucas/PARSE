interface TranscriptionLaneToolbarProps {
  x: number;
  y: number;
  laneLabel: string;
  start: number;
  end: number;
  onEdit: (() => void) | null;
  onSplit: () => void;
  onMerge: () => void;
  onDelete: () => void;
}

export function TranscriptionLaneToolbar({
  x,
  y,
  laneLabel,
  start,
  end,
  onEdit,
  onSplit,
  onMerge,
  onDelete,
}: TranscriptionLaneToolbarProps) {
  return (
    <div
      onMouseDown={(e) => e.stopPropagation()}
      className="fixed z-50 min-w-[200px] rounded border border-slate-200 bg-white py-1 text-[12px] shadow-lg"
      style={{ left: x, top: y }}
      role="menu"
    >
      <div className="px-3 pt-1 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {laneLabel}
        <span className="ml-2 font-mono text-[10px] font-normal normal-case tracking-normal text-slate-400">
          {start.toFixed(3)}–{end.toFixed(3)}s
        </span>
      </div>
      <div className="mb-1 h-px bg-slate-100" />
      {onEdit ? <MenuItem label="Edit text" hint="dbl-click" onClick={onEdit} /> : null}
      <MenuItem label="Split at playhead" hint="S" onClick={onSplit} />
      <MenuItem label="Merge with next" onClick={onMerge} />
      <div className="my-1 h-px bg-slate-100" />
      <MenuItem label="Delete" danger onClick={onDelete} />
    </div>
  );
}

function MenuItem({
  label,
  hint,
  danger,
  onClick,
}: {
  label: string;
  hint?: string;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={
        "flex w-full items-center justify-between px-3 py-1 text-left hover:bg-slate-50" +
        (danger ? " text-red-600" : " text-slate-700")
      }
    >
      <span>{label}</span>
      {hint ? <span className="ml-4 text-[10px] text-slate-400">{hint}</span> : null}
    </button>
  );
}
