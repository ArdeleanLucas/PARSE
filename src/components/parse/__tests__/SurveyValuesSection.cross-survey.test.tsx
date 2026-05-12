// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { SurveyValuesSection } from '../right-panel/SurveyValuesSection';
import { relinkConceptsByGloss } from '../../../api/client';

vi.mock('../../../api/client', () => ({
  relinkConceptsByGloss: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.mocked(relinkConceptsByGloss).mockReset();
});

function renderSection(onRelinkApplied = vi.fn()) {
  render(
    <SurveyValuesSection
      activeConcept={{ id: 527, key: '527', name: 'nose', tag: 'untagged' as never, surveys: { klq: '1.5', jbil: '34' } }}
      activeSpeaker="Fail01"
      workspaceConcepts={[]}
      conceptSurveyLinks={{}}
      surveyColorCodingEnabled={false}
      surveySettings={{ klq: { display_label: 'KLQ', display_color: 'slate' }, jbil: { display_label: 'JBIL', display_color: 'slate' } }}
      speakerSurveyChoices={{}}
      onSurveyOverlapUpdate={vi.fn()}
      onRelinkApplied={onRelinkApplied}
    />,
  );
}

describe('SurveyValuesSection cross-survey reconciliation', () => {
  it('dry-runs, opens review dialog, applies selected groups, and refreshes with rewrite summary', async () => {
    const onRelinkApplied = vi.fn();
    vi.mocked(relinkConceptsByGloss)
      .mockResolvedValueOnce({
        ok: true,
        applied: false,
        algorithm: 'canonical_survey_gloss:v1-strict',
        groups: [{
          canonical_gloss: 'nose',
          keep_concept_id: '527',
          merge_concept_ids: ['991'],
          labels: { '527': 'nose', '991': 'nose' },
          links_by_survey: { klq: '1.5', jbil: '34' },
          keep_reason: 'lowest_numeric_id',
          source_rows: [],
        }],
        fuzzy_candidates: [],
      })
      .mockResolvedValueOnce({
        ok: true,
        applied: true,
        algorithm: 'canonical_survey_gloss:v1-strict',
        groups: [],
        fuzzy_candidates: [],
        backup_paths: ['backups/relink-by-gloss-1'],
        annotation_rewrites: { 'annotations/Fail01.parse.json': 4, 'annotations/Saha01.parse.json': 2 },
      });

    renderSection(onRelinkApplied);

    fireEvent.click(screen.getByRole('button', { name: /Reconcile concepts across surveys/i }));

    await waitFor(() => expect(relinkConceptsByGloss).toHaveBeenNthCalledWith(1));
    expect(await screen.findByRole('dialog', { name: /Review cross-survey concept merges/i })).toBeTruthy();
    expect(screen.getByText('nose')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Apply selected \(1\)/i }));

    await waitFor(() => expect(relinkConceptsByGloss).toHaveBeenNthCalledWith(2, {
      apply: true,
      accepted_groups: [{ keep_concept_id: '527', merge_concept_ids: ['991'] }],
    }));
    await waitFor(() => expect(onRelinkApplied).toHaveBeenCalled());
    expect(screen.queryByRole('dialog', { name: /Review cross-survey concept merges/i })).toBeNull();
    expect(screen.getByText('Reconciled 1 concepts; rewrote 6 annotation occurrences across 2 files.')).toBeTruthy();
  });

  it('renders the per-speaker survey override for the active speaker instead of the global concept survey', () => {
    render(
      <SurveyValuesSection
        activeConcept={{ id: 1, key: '1', name: 'hair (A)', tag: 'untagged' as never, sourceSurvey: 'klq', sourceItem: '1.1', surveys: { klq: '1.1' } }}
        activeSpeaker="Saha01"
        workspaceConcepts={[]}
        conceptSurveyLinks={{}}
        speakerConceptSurveyLinks={{ Saha01: { '1': { jbil: '32' } } }}
        surveyColorCodingEnabled={false}
        surveySettings={{ klq: { display_label: 'KLQ', display_color: 'emerald' }, jbil: { display_label: 'JBIL', display_color: 'indigo' } }}
        speakerSurveyChoices={{}}
        onSurveyOverlapUpdate={vi.fn()}
      />,
    );
    const summary = screen.getByTestId('survey-current-summary');
    expect(summary.textContent).toContain('JBIL');
    expect(summary.textContent).toContain('32');
    expect(summary.textContent).not.toContain('KLQ 1.1');
    expect(screen.getByRole('button', { name: /Current survey JBIL 32/i })).toBeTruthy();
  });

  it('keeps a different active speaker on the global concept survey when another speaker has an override', () => {
    render(
      <SurveyValuesSection
        activeConcept={{ id: 1, key: '1', name: 'hair (A)', tag: 'untagged' as never, sourceSurvey: 'klq', sourceItem: '1.1', surveys: { klq: '1.1' } }}
        activeSpeaker="Other01"
        workspaceConcepts={[]}
        conceptSurveyLinks={{}}
        speakerConceptSurveyLinks={{ Saha01: { '1': { jbil: '32' } } }}
        surveyColorCodingEnabled={false}
        surveySettings={{ klq: { display_label: 'KLQ', display_color: 'emerald' }, jbil: { display_label: 'JBIL', display_color: 'indigo' } }}
        speakerSurveyChoices={{}}
        onSurveyOverlapUpdate={vi.fn()}
      />,
    );
    const summary = screen.getByTestId('survey-current-summary');
    expect(summary.textContent).toContain('KLQ');
    expect(summary.textContent).toContain('1.1');
    expect(summary.textContent).not.toContain('JBIL');
    expect(summary.textContent).not.toContain('32');
    expect(screen.queryByRole('button', { name: /Current survey JBIL 32/i })).toBeNull();
  });

  it('opens an informational dialog for fuzzy-only dry runs without apply', async () => {
    vi.mocked(relinkConceptsByGloss).mockResolvedValueOnce({
      ok: true,
      applied: false,
      algorithm: 'canonical_survey_gloss:v1-strict',
      groups: [],
      fuzzy_candidates: [{
        incoming_label: 'root (plant)',
        candidate_label: 'root',
        candidate_concept_id: '323',
        reason: 'parenthetical_stripped_match',
      }],
    });

    renderSection();

    fireEvent.click(screen.getByRole('button', { name: /Reconcile concepts across surveys/i }));

    expect(await screen.findByRole('dialog', { name: /Review cross-survey concept merges/i })).toBeTruthy();
    expect(screen.getByText('root (plant)')).toBeTruthy();
    expect(screen.getByText('root')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Apply selected/i })).toBeNull();
    expect(relinkConceptsByGloss).toHaveBeenCalledTimes(1);
  });
});
