// Scrollbar CSS injected into the wavesurfer shadow root so the native
// horizontal scrollbar under the waveform picks up our dark-theme styling.
// Custom properties (--accent, --bg-deep, --border-strong) inherit through the
// shadow DOM boundary, so each active theme (amber/violet/blue) produces its
// own accent on hover/drag without a re-injection.

export const WAVESURFER_SCROLLBAR_CSS = `
::-webkit-scrollbar { width: 10px; height: 12px; }
::-webkit-scrollbar-track { background: var(--bg-deep, #0A0E13); }
::-webkit-scrollbar-thumb {
  background: var(--border-strong, #303A47);
  border-radius: 3px;
  border: 2px solid var(--bg-deep, #0A0E13);
  transition: background 0.15s;
}
::-webkit-scrollbar-thumb:hover,
::-webkit-scrollbar-thumb:active {
  background: var(--accent, #E8A872);
}
::-webkit-scrollbar-button {
  background: var(--bg-elevated, #1B222C);
  border: none;
  height: 14px;
  width: 14px;
}
::-webkit-scrollbar-corner { background: var(--bg-deep, #0A0E13); }
`.trim();

const STYLE_MARKER = 'data-parse-ws-scrollbar';

/**
 * Inject themed scrollbar CSS into a wavesurfer wrapper's shadow root.
 * Returns the injected <style> element, or null if no injection happened
 * (no shadowRoot, or rule already present).
 *
 * Safe to call multiple times — idempotent via the marker attribute.
 */
export function injectWavesurferScrollbarStyles(
  wrapper: HTMLElement | null | undefined,
): HTMLStyleElement | null {
  if (!wrapper) return null;
  const root = wrapper.shadowRoot;
  if (!root) return null;
  if (root.querySelector(`style[${STYLE_MARKER}]`)) return null;

  const style = document.createElement('style');
  style.setAttribute(STYLE_MARKER, 'true');
  style.textContent = WAVESURFER_SCROLLBAR_CSS;
  root.appendChild(style);
  return style;
}
