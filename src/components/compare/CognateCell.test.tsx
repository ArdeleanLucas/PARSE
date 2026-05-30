/** @vitest-environment jsdom */
import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { COGNATE_COLORS, CognateCell, nextCognateGroup, SimBar } from './CognateCell';

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

describe('nextCognateGroup', () => {
  it('cycles through the manual A-J domain and clears after J', () => {
    expect(nextCognateGroup('—')).toBe('A');
    expect(nextCognateGroup('A')).toBe('B');
    expect(nextCognateGroup('I')).toBe('J');
    expect(nextCognateGroup('J')).toBeNull();
  });

  it('funnels invalid or auto-computed groups past J back to A', () => {
    expect(nextCognateGroup('K')).toBe('A');
    expect(nextCognateGroup('M')).toBe('A');
    expect(nextCognateGroup('Z')).toBe('A');
    expect(nextCognateGroup('')).toBe('A');
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

  it('shows the full manual A-J loop in the next-cycle title', () => {
    const expectedNextByGroup: Array<[string, string]> = [
      ['—', 'A'],
      ['A', 'B'],
      ['B', 'C'],
      ['C', 'D'],
      ['D', 'E'],
      ['E', 'F'],
      ['F', 'G'],
      ['G', 'H'],
      ['H', 'I'],
      ['I', 'J'],
      ['J', '—'],
    ];

    const { rerender } = render(<CognateCell speaker="s4" group="—" onCycle={() => {}} onReset={() => {}} />);

    for (const [group, next] of expectedNextByGroup) {
      rerender(<CognateCell speaker="s4" group={group} onCycle={() => {}} onReset={() => {}} />);
      expect(screen.getByTestId('cognate-cycle-s4').getAttribute('title')).toContain(`Click cycles → ${next}`);
    }
  });

  it('shows auto-computed groups past J but funnels their next click back to A', () => {
    render(<CognateCell speaker="s5" group="M" onCycle={() => {}} onReset={() => {}} />);

    const button = screen.getByTestId('cognate-cycle-s5');
    expect(button.textContent).toBe('M');
    expect(button.className).toContain('bg-indigo-200');
    expect(button.getAttribute('title')).toContain('Click cycles → A');
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
