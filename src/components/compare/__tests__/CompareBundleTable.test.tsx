// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CompareBundle } from '../../../api/types';
import { CompareBundleTable } from '../CompareBundleTable';

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

function bigBundle(overrides: Partial<CompareBundle> = {}): CompareBundle {
  return {
    bundle_id: 'big',
    label: 'big',
    row_ids: ['53', '619', '150'],
    buckets: [
      {
        bucket_key: 'klq\u00004.1',
        survey_id: 'klq',
        source_item: '4.1',
        variants: [
          { csv_row_id: '53', concept_en: 'big (A)', variant_label: 'A' },
          { csv_row_id: '619', concept_en: 'big (B)', variant_label: 'B' },
        ],
      },
      {
        bucket_key: 'jbil\u0000169',
        survey_id: 'jbil',
        source_item: '169',
        variants: [{ csv_row_id: '150', concept_en: 'big (A)', variant_label: 'A' }],
      },
    ],
    candidates: {
      Fail01: {
        '53': { csv_row_id: '53', ipa: 'gæwra', ortho: 'gewre', start_sec: 1, end_sec: 2, source_wav: 'audio/working/Fail01.wav', realization_index: 0 },
        '619': { csv_row_id: '619', ipa: 'mezin', ortho: 'mezin', start_sec: 3, end_sec: 4, source_wav: 'audio/working/Fail01.wav', realization_index: 1 },
        '150': null,
      },
      Saha01: {
        '53': null,
        '619': null,
        '150': { csv_row_id: '150', ipa: 'gawra', ortho: 'gawra', start_sec: 5, end_sec: 6, source_wav: 'audio/working/Saha01.wav', realization_index: 0 },
      },
    },
    canonical: {
      Fail01: null,
      Saha01: { csv_row_id: '150', survey_id: 'jbil', source_item: '169', bucket_key: 'jbil\u0000169', source: 'migration:canonical_realizations', selected_at: '', realization_index: 0 },
    },
    ...overrides,
  };
}

beforeEach(() => {
  mocks.putCanonicalLexeme.mockReset();
  mocks.deleteCanonicalLexeme.mockReset();
  mocks.patchCanonicalLexeme.mockReset();
});

afterEach(() => cleanup());

describe('CompareBundleTable', () => {
  it('renders bundle buckets, variants, and speaker canonical cells', () => {
    render(<CompareBundleTable bundle={bigBundle()} speakers={['Fail01', 'Saha01']} />);

    expect(screen.getByTestId('compare-bundle-table').textContent).toContain('big');
    expect(screen.getByTestId('compare-bucket-klq\u00004.1').textContent).toContain('KLQ');
    expect(screen.getByTestId('compare-bucket-jbil\u0000169').textContent).toContain('JBIL');
    expect(screen.getByTestId('compare-variant-53').textContent).toContain('big (A)');
    expect(screen.getByTestId('compare-variant-619').textContent).toContain('big (B)');
    expect(screen.getByTestId('canonical-cell-Fail01-big').textContent).toContain('no canonical chosen');
    expect(screen.getByTestId('canonical-cell-Saha01-big').textContent).toContain('migrated');
  });

  it('opens the picker and saves the chosen csv row through the canonical endpoint', async () => {
    const bundle = bigBundle();
    mocks.putCanonicalLexeme.mockResolvedValue({
      bundle: {
        ...bundle,
        canonical: {
          ...bundle.canonical,
          Fail01: { csv_row_id: '619', survey_id: 'klq', source_item: '4.1', bucket_key: 'klq\u00004.1', source: 'manual', selected_at: '' },
        },
      },
    });
    const onBundleUpdated = vi.fn();
    render(<CompareBundleTable bundle={bundle} speakers={['Fail01']} onBundleUpdated={onBundleUpdated} />);

    fireEvent.click(screen.getByRole('button', { name: 'Choose canonical lexeme for Fail01' }));
    fireEvent.click(screen.getByTestId('canonical-option-Fail01-619').querySelector('input') as HTMLInputElement);
    fireEvent.click(within(screen.getByTestId('canonical-picker-Fail01')).getByText('Save'));

    await waitFor(() => expect(mocks.putCanonicalLexeme).toHaveBeenCalledWith('big', 'Fail01', { csv_row_id: '619', realization_index: 1 }));
    expect(mocks.patchCanonicalLexeme).toHaveBeenCalledWith('big', 'Fail01', expect.objectContaining({ csv_row_id: '619', source: 'manual' }));
    expect(onBundleUpdated).toHaveBeenCalled();
  });

  it('promotes a migrated selection to manual when saved without changes', async () => {
    const bundle = bigBundle();
    mocks.putCanonicalLexeme.mockResolvedValue({ bundle });
    render(<CompareBundleTable bundle={bundle} speakers={['Saha01']} />);

    fireEvent.click(screen.getByRole('button', { name: 'Choose canonical lexeme for Saha01' }));
    expect(screen.getByTestId('canonical-migration-hint-Saha01').textContent).toContain('Migrated legacy choice');
    fireEvent.click(within(screen.getByTestId('canonical-picker-Saha01')).getByText('Save'));

    await waitFor(() => expect(mocks.putCanonicalLexeme).toHaveBeenCalledWith('big', 'Saha01', { csv_row_id: '150', realization_index: 0 }));
  });

  it('renders 409 repair hints inline and keeps the picker open', async () => {
    mocks.putCanonicalLexeme.mockRejectedValue(new Error('409 Conflict {"repair_hint":"choose a row from this bundle"}'));
    render(<CompareBundleTable bundle={bigBundle()} speakers={['Fail01']} />);

    fireEvent.click(screen.getByRole('button', { name: 'Choose canonical lexeme for Fail01' }));
    fireEvent.click(screen.getByTestId('canonical-option-Fail01-53').querySelector('input') as HTMLInputElement);
    fireEvent.click(within(screen.getByTestId('canonical-picker-Fail01')).getByText('Save'));

    await waitFor(() => expect(screen.getByTestId('canonical-error-Fail01').textContent).toContain('choose a row from this bundle'));
    expect(screen.getByTestId('canonical-picker-Fail01')).toBeTruthy();
  });

  it('clears canonical choices through the delete endpoint', async () => {
    const bundle = bigBundle();
    mocks.deleteCanonicalLexeme.mockResolvedValue({ bundle: { ...bundle, canonical: { ...bundle.canonical, Saha01: null } } });
    render(<CompareBundleTable bundle={bundle} speakers={['Saha01']} />);

    fireEvent.click(screen.getByRole('button', { name: 'Choose canonical lexeme for Saha01' }));
    fireEvent.click(within(screen.getByTestId('canonical-picker-Saha01')).getByText('Clear'));

    await waitFor(() => expect(mocks.deleteCanonicalLexeme).toHaveBeenCalledWith('big', 'Saha01'));
    expect(mocks.patchCanonicalLexeme).toHaveBeenCalledWith('big', 'Saha01', null);
  });
});
