/** @vitest-environment jsdom */
import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { COGNATE_COLORS, CognateCell, SimBar } from './CognateCell';

afterEach(() => {
  vi.useRealTimers();
});

describe('SimBar', () => {
  it('renders placeholder when similarity is missing', () => {
    render(<SimBar value={null} />);

    expect(screen.getByText('—')).toBeTruthy();
    expect(screen.getByTitle(/No similarity score yet/i)).toBeTruthy();
  });

  it('renders formatted score and high-similarity fill', () => {
    const { container } = render(<SimBar value={0.91} />);

    expect(screen.getByText('0.91')).toBeTruthy();
    expect(container.querySelector('.bg-emerald-500')).toBeTruthy();
  });

  it('renders low-similarity styling for smaller scores', () => {
    const { container } = render(<SimBar value={0.3} />);

    expect(screen.getByText('0.30')).toBeTruthy();
    expect(container.querySelector('.bg-slate-300')).toBeTruthy();
  });
});

describe('CognateCell', () => {
  it('uses configured cognate color mapping for letter groups', () => {
    const { getByTestId } = render(
      <CognateCell speaker="s1" group="B" onCycle={() => {}} onReset={() => {}} />,
    );

    expect(COGNATE_COLORS.B).toContain('bg-violet-100');
    expect(getByTestId('cognate-cycle-s1').className).toContain('bg-violet-100');
  });

  it('dispatches cycle handler on click', () => {
    const onCycle = vi.fn();
    const onReset = vi.fn();
    render(<CognateCell speaker="s2" group="A" onCycle={onCycle} onReset={onReset} />);

    fireEvent.click(screen.getByTestId('cognate-cycle-s2'));

    expect(onCycle).toHaveBeenCalledTimes(1);
    expect(onReset).not.toHaveBeenCalled();
  });

  it('dispatches reset on long press and suppresses the follow-up cycle', () => {
    vi.useFakeTimers();
    const onCycle = vi.fn();
    const onReset = vi.fn();
    render(<CognateCell speaker="s3" group="C" onCycle={onCycle} onReset={onReset} />);

    const button = screen.getByTestId('cognate-cycle-s3');
    fireEvent.pointerDown(button);
    vi.advanceTimersByTime(500);
    fireEvent.pointerUp(button);
    fireEvent.click(button);

    expect(onReset).toHaveBeenCalledTimes(1);
    expect(onCycle).not.toHaveBeenCalled();
  });
});
