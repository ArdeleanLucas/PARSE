// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SurveyBadge } from '../SurveyBadge';
import type { SurveySettingsMap } from '../../../api/types';

const surveySettings: SurveySettingsMap = {
  ext: { display_label: 'EXT', display_color: 'emerald' },
  klq: { display_label: 'KLQ', display_color: 'indigo' },
  jbil: { display_label: 'JBIL', display_color: 'rose' },
};

const baseProps = {
  conceptId: '527',
  conceptKey: 'conceptKey',
  conceptName: 'head',
  resolvedSurveyId: 'klq',
  resolvedSourceItem: '1.1',
  resolvedDisplayColor: 'indigo',
  availableSurveys: { klq: '1.1' },
  surveySettings,
  surveyColorCodingEnabled: true,
  activeSpeaker: 'Saha01',
  parentActive: false,
};

afterEach(() => cleanup());

describe('SurveyBadge', () => {
  it('renders one available survey as a static span', () => {
    const { container } = render(<SurveyBadge {...baseProps} />);

    expect(screen.queryByRole('button')).toBeNull();
    const badge = container.querySelector('span');
    expect(badge?.textContent).toBe('KLQ 1.1');
    expect(badge?.className).toContain('mr-2 px-1 py-0.5');
    expect(badge?.className).toContain('text-indigo-500');
  });

  it('opens a menu for three available surveys', () => {
    render(
      <SurveyBadge
        {...baseProps}
        availableSurveys={{ klq: '1.1', jbil: '31', ext: 'EXT-7' }}
        onCycle={vi.fn()}
      />,
    );

    const badge = screen.getByRole('button', {
      name: 'Choose survey for head from 3 linked surveys',
    });
    expect(badge.getAttribute('aria-haspopup')).toBe('menu');
    expect(badge.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(badge);
    expect(badge.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('menu')).toBeTruthy();
    expect(screen.getAllByRole('menuitem')).toHaveLength(3);
  });

  it('selects a menu survey with the cycle handler and closes the menu', () => {
    const onCycle = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        availableSurveys={{ klq: '1.1', jbil: '31', ext: 'EXT-7' }}
        onCycle={onCycle}
      />,
    );

    fireEvent.click(screen.getByRole('button', {
      name: 'Choose survey for head from 3 linked surveys',
    }));
    fireEvent.click(screen.getByRole('menuitem', { name: /EXT EXT-7/ }));

    expect(onCycle).toHaveBeenCalledWith({ surveyId: 'ext', sourceItem: 'EXT-7' });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('closes the menu on Escape without firing the cycle handler', () => {
    const onCycle = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        availableSurveys={{ klq: '1.1', jbil: '31', ext: 'EXT-7' }}
        onCycle={onCycle}
      />,
    );

    fireEvent.click(screen.getByRole('button', {
      name: 'Choose survey for head from 3 linked surveys',
    }));
    fireEvent.keyDown(screen.getByRole('button', {
      name: 'Choose survey for head from 3 linked surveys',
    }), { key: 'Escape' });

    expect(onCycle).not.toHaveBeenCalled();
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('closes the menu on outside click', () => {
    render(
      <div>
        <button type="button">Outside target</button>
        <SurveyBadge
          {...baseProps}
          availableSurveys={{ klq: '1.1', jbil: '31', ext: 'EXT-7' }}
          onCycle={vi.fn()}
        />
      </div>,
    );

    fireEvent.click(screen.getByRole('button', {
      name: 'Choose survey for head from 3 linked surveys',
    }));
    expect(screen.getByRole('menu')).toBeTruthy();

    fireEvent.mouseDown(screen.getByRole('button', { name: 'Outside target' }));
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('supports ArrowDown and Enter keyboard selection in the menu', () => {
    const onCycle = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        availableSurveys={{ klq: '1.1', jbil: '31', ext: 'EXT-7' }}
        onCycle={onCycle}
      />,
    );

    const badge = screen.getByRole('button', {
      name: 'Choose survey for head from 3 linked surveys',
    });
    fireEvent.click(badge);
    fireEvent.keyDown(badge, { key: 'ArrowDown' });
    fireEvent.keyDown(badge, { key: 'Enter' });

    expect(onCycle).toHaveBeenCalledWith({ surveyId: 'ext', sourceItem: 'EXT-7' });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('cycles to the next sorted survey when exactly two surveys are clickable', () => {
    const onCycle = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        availableSurveys={{ klq: '1.1', jbil: '31' }}
        onCycle={onCycle}
      />,
    );

    const badge = screen.getByRole('button', {
      name: 'Switch survey for head from KLQ 1.1 to JBIL 31',
    });
    expect(badge.getAttribute('aria-haspopup')).toBeNull();
    expect(badge.textContent).toBe('KLQ 1.1');
    expect(badge.className).toContain('hover:underline');

    fireEvent.click(badge);
    expect(onCycle).toHaveBeenCalledWith({ surveyId: 'jbil', sourceItem: '31' });
  });

  it('promotes to the next sorted survey without an active speaker', () => {
    const onPromote = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        activeSpeaker={null}
        availableSurveys={{ klq: '1.1', jbil: '31' }}
        onPromote={onPromote}
      />,
    );

    const badge = screen.getByRole('button', {
      name: 'Promote survey for head from KLQ 1.1 to JBIL 31',
    });
    fireEvent.click(badge);

    expect(onPromote).toHaveBeenCalledWith({ surveyId: 'jbil', sourceItem: '31' });
  });

  it('promotes via the popover when 3+ surveys are linked and no speaker is active', () => {
    const onPromote = vi.fn();
    const onCycle = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        activeSpeaker={null}
        availableSurveys={{ klq: '1.1', jbil: '31', ext: 'EXT-7' }}
        onCycle={onCycle}
        onPromote={onPromote}
      />,
    );

    const badge = screen.getByRole('button', {
      name: /Choose primary survey for head from 3 linked surveys/,
    });
    fireEvent.click(badge);
    fireEvent.click(screen.getByRole('menuitem', { name: /EXT EXT-7/ }));

    expect(onPromote).toHaveBeenCalledWith({ surveyId: 'ext', sourceItem: 'EXT-7' });
    expect(onCycle).not.toHaveBeenCalled();
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('keeps multi-survey badges static without an active speaker or promote handler', () => {
    const onCycle = vi.fn();
    const { container } = render(
      <SurveyBadge
        {...baseProps}
        activeSpeaker={null}
        availableSurveys={{ klq: '1.1', jbil: '31' }}
        onCycle={onCycle}
      />,
    );

    expect(screen.queryByRole('button')).toBeNull();
    expect(container.querySelector('span')?.textContent).toBe('KLQ 1.1');
  });

  it('falls back to slate classes when color coding is off', () => {
    const { container } = render(
      <SurveyBadge
        {...baseProps}
        surveyColorCodingEnabled={false}
        parentActive={false}
      />,
    );

    expect(container.querySelector('span')?.className).toContain('text-slate-300');
  });

  it('renders the precomposed source item verbatim when surveyId is empty', () => {
    const { container } = render(
      <SurveyBadge
        {...baseProps}
        resolvedSurveyId=""
        resolvedSourceItem="JBIL 34"
        availableSurveys={{}}
      />,
    );

    expect(screen.queryByRole('button')).toBeNull();
    expect(container.querySelector('span')?.textContent).toBe('JBIL 34');
  });

  it('matches the existing aria-label format', () => {
    render(
      <SurveyBadge
        {...baseProps}
        availableSurveys={{ klq: '1.1', jbil: '31' }}
        onCycle={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', {
      name: /^Switch survey for head from KLQ 1\.1 to JBIL 31$/,
    })).toBeTruthy();
  });
});
