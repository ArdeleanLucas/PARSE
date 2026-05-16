// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SpeakerHeader } from './SpeakerHeader';

const baseConcept = { id: 7, key: 'rain', name: 'rain' };

afterEach(() => {
  cleanup();
});

describe('SpeakerHeader survey chips', () => {
  it('renders rich survey chips with source items instead of the plain survey line for multi-survey concepts', () => {
    render(
      <SpeakerHeader
        annotated={false}
        complete={false}
        concept={baseConcept}
        speaker="Fail01"
        totalConcepts={12}
        surveyLabel="Jbil Modal"
        surveySourceItem="JBIL_100"
        surveyChoices={['jbil', 'klq']}
        resolvedSurveyId="jbil"
        availableSurveys={{ jbil: 'JBIL_100', klq: 'KLQ_1.10' }}
        surveySettings={{
          jbil: { display_label: 'Jbil Modal', display_color: 'slate' },
          klq: { display_label: 'Kurdish List', display_color: 'slate' },
        }}
        surveyColorCodingEnabled
        activeSpeaker="Fail01"
        conceptSurveyKey="rain"
        onSurveyChoiceChange={vi.fn()}
        onPrev={vi.fn()}
        onNext={vi.fn()}
      />,
    );

    const chipRow = screen.getByTestId('annotate-survey-chip-row');
    expect(within(chipRow).getByText('Survey')).toBeTruthy();
    const current = screen.getByRole('button', { name: 'Current survey Jbil Modal JBIL_100' });
    const alternate = screen.getByRole('button', { name: 'Switch rain to Kurdish List KLQ_1.10' });
    expect(current.textContent).toContain('Jbil Modal');
    expect(current.textContent).toContain('JBIL_100');
    expect(alternate.textContent).toContain('Kurdish List');
    expect(alternate.textContent).toContain('KLQ_1.10');
    expect(screen.queryByText('Jbil Modal', { selector: 'span.text-slate-600' })).toBeNull();
  });

  it('clicking a non-selected chip fires onSurveyChoiceChange with speaker, concept key, and survey id', () => {
    const onSurveyChoiceChange = vi.fn();
    render(
      <SpeakerHeader
        annotated={false}
        complete={false}
        concept={baseConcept}
        speaker="Fail01"
        totalConcepts={12}
        surveyLabel="Jbil Modal"
        surveySourceItem="JBIL_100"
        surveyChoices={['jbil', 'klq']}
        resolvedSurveyId="jbil"
        availableSurveys={{ jbil: 'JBIL_100', klq: 'KLQ_1.10' }}
        surveySettings={{
          jbil: { display_label: 'Jbil Modal', display_color: 'slate' },
          klq: { display_label: 'Kurdish List', display_color: 'slate' },
        }}
        surveyColorCodingEnabled
        activeSpeaker="Fail01"
        conceptSurveyKey="rain"
        onSurveyChoiceChange={onSurveyChoiceChange}
        onPrev={vi.fn()}
        onNext={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Switch rain to Kurdish List KLQ_1.10' }));

    expect(onSurveyChoiceChange).toHaveBeenCalledWith('Fail01', 'rain', 'klq');
  });

  it('keeps a single-survey concept to the plain survey line without chip buttons', () => {
    render(
      <SpeakerHeader
        annotated={false}
        complete={false}
        concept={{ id: 8, key: 'snow', name: 'snow' }}
        speaker="Fail01"
        totalConcepts={12}
        surveyLabel="Kurdish List"
        surveySourceItem="KLQ_1.11"
        surveyChoices={['klq']}
        resolvedSurveyId="klq"
        availableSurveys={{ klq: 'KLQ_1.11' }}
        surveySettings={{ klq: { display_label: 'Kurdish List', display_color: 'slate' } }}
        surveyColorCodingEnabled
        activeSpeaker="Fail01"
        conceptSurveyKey="snow"
        onSurveyChoiceChange={vi.fn()}
        onPrev={vi.fn()}
        onNext={vi.fn()}
      />,
    );

    expect(screen.getByText('Survey').parentElement?.textContent).toContain('Kurdish ListKLQ_1.11');
    expect(screen.queryByRole('button', { name: /Switch snow to/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Current survey/i })).toBeNull();
  });
});
