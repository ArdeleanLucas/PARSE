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

describe('SurveyValuesSection cross-survey reconciliation', () => {
  it('dry-runs, confirms proposed merges, applies accepted groups, and refreshes', async () => {
    const onRelinkApplied = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
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
      });

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

    fireEvent.click(screen.getByRole('button', { name: /Reconcile concepts across surveys/i }));

    await waitFor(() => expect(relinkConceptsByGloss).toHaveBeenNthCalledWith(1));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('nose: keep 527; merge 991'));
    await waitFor(() => expect(relinkConceptsByGloss).toHaveBeenNthCalledWith(2, {
      apply: true,
      accepted_groups: [{ keep_concept_id: '527', merge_concept_ids: ['991'] }],
    }));
    await waitFor(() => expect(onRelinkApplied).toHaveBeenCalled());
    expect(screen.getByText('Concept reconciliation applied.')).toBeTruthy();
  });
});
