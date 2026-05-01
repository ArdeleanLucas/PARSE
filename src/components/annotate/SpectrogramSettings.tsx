import { useEffect, useRef } from "react";
import {
  PRAAT_DEFAULTS,
  useSpectrogramSettings,
} from "../../stores/useSpectrogramSettings";
import type {
  ColorScheme,
  WindowShape,
} from "../../workers/spectrogram-worker";

interface Props {
  anchor: { x: number; y: number };
  onClose: () => void;
}

const WINDOW_SHAPES: { value: WindowShape; label: string }[] = [
  { value: "gaussian", label: "Gaussian (Praat)" },
  { value: "hann", label: "Hann" },
  { value: "hamming", label: "Hamming" },
];

const COLOR_SCHEMES: { value: ColorScheme; label: string }[] = [
  { value: "praat", label: "Praat (dark = loud)" },
  { value: "inverted", label: "Inverted (light = loud)" },
  { value: "viridis", label: "Viridis" },
];

const PRESETS = [
  { label: "Wideband 0.005s", value: 0.005 },
  { label: "Narrowband 0.029s", value: 0.029 },
];

const PRAAT_DEFAULT_PRE_EMPHASIS_HZ = PRAAT_DEFAULTS.preEmphasisHz;

export function SpectrogramSettings({ anchor, onClose }: Props) {
  const settings = useSpectrogramSettings();
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onDocMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Spectrogram settings"
      data-testid="spectrogram-settings"
      className="fixed z-50 w-[300px] rounded-md border border-slate-200 bg-white p-3 text-[11px] shadow-lg"
      style={{ top: anchor.y, left: Math.max(8, anchor.x - 280) }}
    >
      <div className="mb-2 flex items-center justify-between">
        <strong className="text-[12px] text-slate-900">Spectrogram settings</strong>
        <button
          type="button"
          data-testid="spectrogram-settings-reset"
          onClick={() => settings.resetDefaults()}
          className="rounded border border-slate-200 bg-white px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-50"
        >
          Reset Praat
        </button>
      </div>

      <Field label={`Window length: ${(settings.windowLengthSec * 1000).toFixed(1)} ms`}>
        <input
          aria-label="Window length"
          type="range"
          min={1}
          max={50}
          step={0.5}
          value={settings.windowLengthSec * 1000}
          onChange={(e) => settings.set("windowLengthSec", Number(e.target.value) / 1000)}
          className="w-full"
        />
        <div className="mt-1 flex gap-1.5">
          {PRESETS.map((preset) => {
            const active = Math.abs(settings.windowLengthSec - preset.value) < 1e-4;
            return (
              <button
                key={preset.value}
                type="button"
                data-testid={`spectrogram-preset-${preset.value}`}
                onClick={() => settings.set("windowLengthSec", preset.value)}
                className={`rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-600 ${
                  active ? "bg-indigo-50" : "bg-white hover:bg-slate-50"
                }`}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      </Field>

      <Field label={`Dynamic range: ${settings.dynamicRangeDb} dB`}>
        <input
          aria-label="Dynamic range"
          type="range"
          min={20}
          max={80}
          step={1}
          value={settings.dynamicRangeDb}
          onChange={(e) => settings.set("dynamicRangeDb", Number(e.target.value))}
          className="w-full"
        />
      </Field>

      <Field label={`Max frequency: ${settings.maxFrequencyHz} Hz`}>
        <input
          aria-label="Max frequency"
          type="range"
          min={1000}
          max={11000}
          step={500}
          value={settings.maxFrequencyHz}
          onChange={(e) => settings.set("maxFrequencyHz", Number(e.target.value))}
          className="w-full"
        />
      </Field>

      <Field label="Pre-emphasis">
        <label className="flex items-center gap-1.5 text-slate-600">
          <input
            type="checkbox"
            data-testid="spectrogram-pre-emphasis"
            checked={settings.preEmphasisHz > 0}
            onChange={(e) =>
              settings.set("preEmphasisHz", e.target.checked ? PRAAT_DEFAULT_PRE_EMPHASIS_HZ : 0)
            }
          />
          <span>+6 dB/oct above 50 Hz {settings.preEmphasisHz > 0 ? "(on)" : "(off)"}</span>
        </label>
      </Field>

      <Field label="Window shape">
        <select
          aria-label="Window shape"
          value={settings.windowShape}
          onChange={(e) => settings.set("windowShape", e.target.value as WindowShape)}
          className="w-full rounded border border-slate-200 px-1.5 py-1 text-[11px] text-slate-700"
        >
          {WINDOW_SHAPES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Color scheme">
        <select
          aria-label="Color scheme"
          value={settings.colorScheme}
          onChange={(e) => settings.set("colorScheme", e.target.value as ColorScheme)}
          className="w-full rounded border border-slate-200 px-1.5 py-1 text-[11px] text-slate-700"
        >
          {COLOR_SCHEMES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <div className="mt-2 text-[10px] text-slate-400">
        Defaults match Praat — Gaussian window, 50 dB range, 5500 Hz, pre-emphasis on. Settings persist locally.
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-2">
      <div className="mb-1 text-[10px] text-slate-500">{label}</div>
      {children}
    </div>
  );
}
