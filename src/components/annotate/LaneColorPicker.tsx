import { useEffect, useRef, useState } from "react";

const PRESET_COLORS = [
  "#6366f1", // indigo
  "#059669", // emerald
  "#d97706", // amber
  "#dc2626", // red
  "#0ea5e9", // sky
  "#a855f7", // violet
  "#db2777", // pink
  "#14b8a6", // teal
  "#eab308", // yellow
  "#475569", // slate
];

interface LaneColorPickerProps {
  value: string;
  onChange: (color: string) => void;
  ariaLabel: string;
}

/**
 * Compact color swatch that opens a preset palette popover on click. Avoids
 * the ugly native OS color dialog while keeping the choice set curated and
 * readable on a white background.
 */
export function LaneColorPicker({ value, onChange, ariaLabel }: LaneColorPickerProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          setOpen((v) => !v);
        }}
        className="h-4 w-4 rounded-sm border border-slate-300 ring-offset-1 transition hover:ring-2 focus:outline-none focus:ring-2"
        style={{ backgroundColor: value }}
        aria-label={ariaLabel}
        aria-haspopup="true"
        aria-expanded={open}
        title={ariaLabel}
      />
      {open && (
        <div
          role="dialog"
          className="absolute left-0 top-5 z-50 grid w-[108px] grid-cols-5 gap-1 rounded-md border border-slate-200 bg-white p-1.5 shadow-lg"
        >
          {PRESET_COLORS.map((color) => {
            const active = color.toLowerCase() === value.toLowerCase();
            return (
              <button
                key={color}
                type="button"
                onClick={() => {
                  onChange(color);
                  setOpen(false);
                }}
                className={
                  "h-4 w-4 rounded-sm border transition hover:scale-110 " +
                  (active ? "border-slate-700 ring-1 ring-slate-700" : "border-slate-200")
                }
                style={{ backgroundColor: color }}
                aria-label={`Color ${color}`}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
