// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CompareBundle } from '../../../api/types';
import { CanonicalLexemeCell } from '../CanonicalLexemeCell';

const mocks = vi.hoisted(() => ({
  putCanonicalLexeme: vi.fn(),
  deleteCanonicalLexeme: vi.fn(),
  patchCanonicalLexeme: vi.fn(),
}));

vi.mock('../../../api/client', () => ({
  putCanonicalLexeme: (...args: unknown[]) => mocks.putCanonicalLexeme(...args),
  deleteCanonicalLexeme: (...args: unknown[]) => mocks.deleteCanonicalLexeme(...args),
}));

vi.mock('../../../stores/enrichmentStore', () => ({
  useEnrichmentStore: {
    getState: () => ({ patchCanonicalLexeme: mocks.patchCanonicalLexeme }),
  },
}));

function bundle(overrides: Partial<CompareBundle> = {}): CompareBundle {
  return {
    bundle_id: 'big',
    label: 'big',
    row_ids: ['53', '619'],
    buckets: [{
      bucket_key: 'klq\u00004.1',
      survey_id: 'klq',
      source_item: '4.1',
      variants: [
        { csv_row_id: '53', concept_en: 'big (A)', variant_label: 'A' },
        { csv_row_id: '619', concept_en: 'big (B)', variant_label: 'B' },
      ],
    }],
    candidates: {
      Fail01: {
        '53': { csv_row_id: '53', ipa: 'gæwra', ortho: 'gewre', realization_index: 0 },
        '619': null,
      },
    },
    canonical: { Fail01: { csv_row_id: '53', survey_id: 'klq', source_item: '4.1', bucket_key: 'klq\u00004.1', source: 'manual', selected_at: '', realization_index: 0 } },
    ...overrides,
  };
}

beforeEach(() => {
  mocks.putCanonicalLexeme.mockReset();
  mocks.deleteCanonicalLexeme.mockReset();
  mocks.patchCanonicalLexeme.mockReset();
});

afterEach(() => cleanup());

describe('CanonicalLexemeCell', () => {
  it('renders faded selectable rows for variants with no recorded form', () => {
    render(<CanonicalLexemeCell bundle={bundle()} speaker="Fail01" />);

    fireEvent.click(screen.getByRole('button', { name: 'Choose canonical lexeme for Fail01' }));
    const row = screen.getByTestId('canonical-option-Fail01-619');
    expect(row.textContent).toContain('no form');
    expect(row.getAttribute('title')).toContain('selected canonical for Fail01 has no recorded form');
  });

  it('saves manual choices optimistically', async () => {
    const source = bundle();
    const responseBundle = {
      ...source,
      canonical: { Fail01: { csv_row_id: '619', survey_id: 'klq', source_item: '4.1', bucket_key: 'klq\u00004.1', source: 'manual' as const, selected_at: '' } },
    };
    mocks.putCanonicalLexeme.mockResolvedValue({ bundle: responseBundle });
    const onBundleUpdated = vi.fn();
    render(<CanonicalLexemeCell bundle={source} speaker="Fail01" onBundleUpdated={onBundleUpdated} />);

    fireEvent.click(screen.getByRole('button', { name: 'Choose canonical lexeme for Fail01' }));
    fireEvent.click(screen.getByTestId('canonical-option-Fail01-619').querySelector('input') as HTMLInputElement);
    fireEvent.click(within(screen.getByTestId('canonical-picker-Fail01')).getByText('Save'));

    await waitFor(() => expect(mocks.putCanonicalLexeme).toHaveBeenCalledWith('big', 'Fail01', { csv_row_id: '619', realization_index: undefined }));
    expect(mocks.patchCanonicalLexeme).toHaveBeenCalledWith('big', 'Fail01', expect.objectContaining({ csv_row_id: '619' }));
    expect(onBundleUpdated).toHaveBeenCalledWith(responseBundle);
  });

  it('renders 409 repair hints inline', async () => {
    mocks.putCanonicalLexeme.mockRejectedValue(new Error('409 {"repair_hint":"row belongs to another bundle"}'));
    render(<CanonicalLexemeCell bundle={bundle()} speaker="Fail01" />);

    fireEvent.click(screen.getByRole('button', { name: 'Choose canonical lexeme for Fail01' }));
    fireEvent.click(screen.getByTestId('canonical-option-Fail01-53').querySelector('input') as HTMLInputElement);
    fireEvent.click(within(screen.getByTestId('canonical-picker-Fail01')).getByText('Save'));

    await waitFor(() => expect(screen.getByTestId('canonical-error-Fail01').textContent).toContain('row belongs to another bundle'));
  });

  it('clears canonical choices optimistically', async () => {
    const source = bundle();
    const responseBundle = { ...source, canonical: { Fail01: null } };
    mocks.deleteCanonicalLexeme.mockResolvedValue({ bundle: responseBundle });
    const onBundleUpdated = vi.fn();
    render(<CanonicalLexemeCell bundle={source} speaker="Fail01" onBundleUpdated={onBundleUpdated} />);

    fireEvent.click(screen.getByRole('button', { name: 'Choose canonical lexeme for Fail01' }));
    fireEvent.click(within(screen.getByTestId('canonical-picker-Fail01')).getByText('Clear'));

    await waitFor(() => expect(mocks.deleteCanonicalLexeme).toHaveBeenCalledWith('big', 'Fail01'));
    expect(mocks.patchCanonicalLexeme).toHaveBeenCalledWith('big', 'Fail01', null);
    expect(onBundleUpdated).toHaveBeenCalledWith(responseBundle);
  });
});
