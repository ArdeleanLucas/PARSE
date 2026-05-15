// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SurveyBadge } from '../SurveyBadge';
import type { SurveySettingsMap } from '../../../api/types';

const surveySettings: SurveySettingsMap = {
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

  it('cycles to the next sorted survey when clickable', () => {
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
    expect(badge.textContent).toBe('KLQ 1.1');
    expect(badge.className).toContain('hover:underline');

    fireEvent.click(badge);
    expect(onCycle).toHaveBeenCalledWith({ surveyId: 'jbil', sourceItem: '31' });
  });

  it('keeps multi-survey badges static without an active speaker', () => {
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
