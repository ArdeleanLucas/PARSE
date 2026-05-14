// @vitest-environment jsdom
import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Modal } from './Modal';

afterEach(() => {
  cleanup();
});

describe('Modal', () => {
  it('uses theme-overridable Tailwind classes instead of hardcoded white inline styles', () => {
    render(
      <Modal open onClose={vi.fn()} title="Run IPA Transcription">
        <p>Modal body</p>
      </Modal>,
    );

    const title = screen.getByText('Run IPA Transcription');
    expect(title.className).toContain('text-slate-900');
    expect(title.getAttribute('style')).toBeNull();

    const panel = title.parentElement;
    expect(panel?.className).toContain('bg-white');
    expect(panel?.className).toContain('text-slate-900');
    expect(panel?.className).toContain('ring-slate-200');
    expect(panel?.getAttribute('style')).toBeNull();

    const backdrop = panel?.parentElement;
    expect(backdrop?.className).toContain('bg-slate-900/50');
    expect(backdrop?.className).toContain('z-[1000]');
    expect(backdrop?.getAttribute('style')).toBeNull();
  });

  it('preserves dismissible backdrop behavior after class conversion', () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Import Speaker">
        <button type="button">Inner action</button>
      </Modal>,
    );

    fireEvent.click(screen.getByRole('button', { name: /Inner action/i }));
    expect(onClose).not.toHaveBeenCalled();

    const backdrop = screen.getByText('Import Speaker').parentElement?.parentElement;
    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
