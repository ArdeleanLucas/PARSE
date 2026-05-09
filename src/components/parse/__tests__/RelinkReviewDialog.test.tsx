// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { RelinkReviewDialog } from '../right-panel/RelinkReviewDialog';
import type { RelinkByGlossResponse } from '../../../api/types';

const reviewResponse: RelinkByGlossResponse = {
  ok: true,
  applied: false,
  algorithm: 'canonical_survey_gloss:v1-strict',
  groups: [
    {
      canonical_gloss: 'nose',
      keep_concept_id: '527',
      merge_concept_ids: ['991'],
      labels: { '527': 'nose', '991': 'nose (Audition)' },
      links_by_survey: { klq: '1.5', jbil: '34' },
      keep_reason: 'lowest_numeric_id',
      source_rows: [],
    },
    {
      canonical_gloss: 'leaf',
      keep_concept_id: '322',
      merge_concept_ids: ['998', '999'],
      labels: { '322': 'leaf', '998': 'leaf (A)', '999': 'leaf (B)' },
      links_by_survey: { jbil: '322', ext: '8.2' },
      keep_reason: 'metadata_rich_over_lowest_empty',
      source_rows: [],
    },
  ],
  fuzzy_candidates: [
    {
      incoming_label: 'root (plant)',
      candidate_label: 'root',
      candidate_concept_id: '323',
      reason: 'parenthetical_stripped_match',
    },
  ],
};

afterEach(() => cleanup());

describe('RelinkReviewDialog', () => {
  it('lists strict groups, humanized keep reasons, survey links, and fuzzy candidates', () => {
    render(<RelinkReviewDialog response={reviewResponse} onApply={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByRole('dialog', { name: /Review cross-survey concept merges/i })).toBeTruthy();
    expect(screen.getByText('2 strict groups')).toBeTruthy();
    expect(screen.getByText('1 fuzzy candidate')).toBeTruthy();
    expect(screen.getByText('canonical_survey_gloss:v1-strict')).toBeTruthy();

    const noseRow = screen.getByTestId('relink-group-527');
    expect(within(noseRow).getByRole('checkbox', { name: /Include nose/i })).toBeTruthy();
    expect((within(noseRow).getByRole('checkbox', { name: /Include nose/i }) as HTMLInputElement).checked).toBe(true);
    expect(within(noseRow).getByText('lowest id')).toBeTruthy();
    expect(within(noseRow).getByText('klq 1.5')).toBeTruthy();
    expect(within(noseRow).getByText('jbil 34')).toBeTruthy();

    const leafRow = screen.getByTestId('relink-group-322');
    expect((within(leafRow).getByRole('checkbox', { name: /Include leaf/i }) as HTMLInputElement).checked).toBe(true);
    expect(within(leafRow).getByText('metadata-rich')).toBeTruthy();
    expect(leafRow.textContent).toContain('merge 998 leaf (A), 999 leaf (B)');

    const fuzzyRow = screen.getByTestId('relink-fuzzy-0');
    expect(within(fuzzyRow).getByText('root (plant)')).toBeTruthy();
    expect(within(fuzzyRow).getByText('root')).toBeTruthy();
    expect(within(fuzzyRow).getByText('parenthetical stripped match')).toBeTruthy();
    expect(within(fuzzyRow).getByText(/Requires manual relabel/i)).toBeTruthy();
    expect(within(fuzzyRow).queryByRole('checkbox')).toBeNull();
  });

  it('applies only checked strict groups and cancel does not apply', () => {
    const onApply = vi.fn();
    const onCancel = vi.fn();
    render(<RelinkReviewDialog response={reviewResponse} onApply={onApply} onCancel={onCancel} />);

    fireEvent.click(screen.getByRole('checkbox', { name: /Include nose/i }));
    fireEvent.click(screen.getByRole('button', { name: /Apply selected \(1\)/i }));

    expect(onApply).toHaveBeenCalledWith([
      { keep_concept_id: '322', merge_concept_ids: ['998', '999'] },
    ]);

    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('renders fuzzy-only dry runs as informational with no apply button', () => {
    const fuzzyOnly: RelinkByGlossResponse = {
      ...reviewResponse,
      groups: [],
      fuzzy_candidates: reviewResponse.fuzzy_candidates,
    };

    render(<RelinkReviewDialog response={fuzzyOnly} onApply={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText('0 strict groups')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Apply selected/i })).toBeNull();
    expect(screen.getByText(/No strict merge groups were proposed/i)).toBeTruthy();
  });
});
