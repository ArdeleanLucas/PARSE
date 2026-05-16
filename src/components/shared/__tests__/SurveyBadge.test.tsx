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
  it('renders one available survey as a static testable pill', () => {
    render(<SurveyBadge {...baseProps} />);

    expect(screen.queryByRole('button')).toBeNull();
    const badge = screen.getByTestId('survey-badge-conceptKey');
    const pill = screen.getByTestId('survey-badge-pill-conceptKey-klq');
    expect(badge.textContent).toBe('KLQ 1.1');
    expect(pill.className).toContain('px-1 py-0.5');
    expect(pill.className).toContain('text-violet-500');
  });

  it('renders every linked survey as side-by-side pills in editor variant', () => {
    render(
      <SurveyBadge
        {...baseProps}
        variant="editor"
        availableSurveys={{ klq: '1.1', jbil: '31', ext: 'EXT-7' }}
        onCycle={vi.fn()}
      />,
    );

    const pills = screen.getAllByTestId(/^survey-badge-pill-conceptKey-/);
    expect(pills.map((pill) => pill.textContent)).toEqual(['EXT EXT-7', 'JBIL 31', 'KLQ 1.1']);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('selects a linked survey with the cycle handler', () => {
    const onCycle = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        availableSurveys={{ klq: '1.1', jbil: '31', ext: 'EXT-7' }}
        onCycle={onCycle}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Switch survey for head from KLQ 1.1 to EXT EXT-7' }));

    expect(onCycle).toHaveBeenCalledWith({ surveyId: 'ext', sourceItem: 'EXT-7' });
  });

  it('cycles to the other sorted survey when exactly two surveys are clickable', () => {
    const onCycle = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        availableSurveys={{ klq: '1.1', jbil: '31' }}
        onCycle={onCycle}
      />,
    );

    const badge = screen.getByRole('button', { name: 'Switch survey for head from KLQ 1.1 to JBIL 31' });
    expect(badge.textContent).toBe('KLQ 1.1');
    expect(badge.className).toContain('hover:underline');

    fireEvent.click(badge);
    expect(onCycle).toHaveBeenCalledWith({ surveyId: 'jbil', sourceItem: '31' });
  });

  it('promotes a clicked survey without an active speaker', () => {
    const onPromote = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        activeSpeaker={null}
        availableSurveys={{ klq: '1.1', jbil: '31' }}
        onPromote={onPromote}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Promote survey for head from KLQ 1.1 to JBIL 31' }));

    expect(onPromote).toHaveBeenCalledWith({ surveyId: 'jbil', sourceItem: '31' });
  });

  it('keeps multi-survey badges static without an active speaker or promote handler', () => {
    const onCycle = vi.fn();
    render(
      <SurveyBadge
        {...baseProps}
        activeSpeaker={null}
        availableSurveys={{ klq: '1.1', jbil: '31' }}
        onCycle={onCycle}
      />,
    );

    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByTestId('survey-badge-pill-conceptKey-klq').textContent).toBe('KLQ 1.1');
  });

  it('fires onEdit on pill context menu', () => {
    const onEdit = vi.fn();
    render(<SurveyBadge {...baseProps} onEdit={onEdit} />);

    fireEvent.contextMenu(screen.getByTestId('survey-badge-pill-conceptKey-klq'));

    expect(onEdit).toHaveBeenCalledWith({ surveyId: 'klq', sourceItem: '1.1' });
  });

  it('falls back to slate classes when color coding is off', () => {
    render(
      <SurveyBadge
        {...baseProps}
        surveyColorCodingEnabled={false}
        parentActive={false}
      />,
    );

    expect(screen.getByTestId('survey-badge-pill-conceptKey-klq').className).toContain('text-slate-300');
  });

  it('renders the precomposed source item verbatim when surveyId is empty', () => {
    render(
      <SurveyBadge
        {...baseProps}
        resolvedSurveyId=""
        resolvedSourceItem="JBIL 34"
        availableSurveys={{}}
      />,
    );

    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByTestId('survey-badge-pill-conceptKey-fallback').textContent).toBe('JBIL 34');
  });
});
