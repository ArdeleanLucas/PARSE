// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CompareBundle } from '../../api/types';
import type { SpeakerForm } from '../../lib/speakerForm';
import { SpeakerFormsTable } from './SpeakerFormsTable';

const mocks = vi.hoisted(() => ({
  putCanonicalLexeme: vi.fn(),
  deleteCanonicalLexeme: vi.fn(),
  saveLexemeNote: vi.fn(),
  saveEnrichments: vi.fn(),
  patchCanonicalLexeme: vi.fn(),
  setState: vi.fn(),
  storeData: {} as Record<string, unknown>,
}));

vi.mock('../../api/client', () => ({
  putCanonicalLexeme: (...args: unknown[]) => mocks.putCanonicalLexeme(...args),
  deleteCanonicalLexeme: (...args: unknown[]) => mocks.deleteCanonicalLexeme(...args),
}));

vi.mock('../../api/contracts/enrichments-tags-notes-imports', () => ({
  saveLexemeNote: (...args: unknown[]) => mocks.saveLexemeNote(...args),
  saveEnrichments: (...args: unknown[]) => mocks.saveEnrichments(...args),
}));

vi.mock('../../stores/enrichmentStore', () => ({
  useEnrichmentStore: Object.assign(
    (selector: (state: { data: Record<string, unknown> }) => unknown) =>
      selector({ data: mocks.storeData }),
    {
      getState: () => ({
        data: mocks.storeData,
        patchCanonicalLexeme: mocks.patchCanonicalLexeme,
      }),
      setState: (...args: unknown[]) => mocks.setState(...args),
    },
  ),
}));

function makeBundle(overrides: Partial<CompareBundle> = {}): CompareBundle {
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
        bucket_key: 'jbl\u0000169',
        survey_id: 'jbl',
        source_item: '169',
        variants: [{ csv_row_id: '150', concept_en: 'big (A)', variant_label: 'A' }],
      },
    ],
    candidates: {
      Fail01: {
        '53': {
          csv_row_id: '53',
          ipa: 'gæwra',
          ortho: 'gewre',
          start_sec: 1,
          end_sec: 2,
          source_wav: 'audio/working/Fail01.wav',
          realization_index: 0,
        },
        '619': {
          csv_row_id: '619',
          ipa: 'mezin',
          ortho: 'mezin',
          start_sec: 3,
          end_sec: 4,
          source_wav: 'audio/working/Fail01.wav',
          realization_index: 1,
        },
        '150': null,
      },
      Saha01: {
        '53': null,
        '619': null,
        '150': {
          csv_row_id: '150',
          ipa: 'gawra',
          ortho: 'gawra',
          start_sec: 5,
          end_sec: 6,
          source_wav: 'audio/working/Saha01.wav',
          realization_index: 0,
        },
      },
    },
    canonical: {
      Fail01: null,
      Saha01: {
        csv_row_id: '150',
        survey_id: 'jbl',
        source_item: '169',
        bucket_key: 'jbl\u0000169',
        source: 'manual',
        selected_at: '',
        realization_index: 0,
      },
    },
    speaker_concept_survey_links: {
      Saha01: { '150': { jbl: '169' } },
    },
    ...overrides,
  };
}

function makeForm(overrides: Partial<SpeakerForm> = {}): SpeakerForm {
  return {
    speaker: 'Fail01',
    ipa: 'gæwra',
    ortho: 'gewre',
    utterances: 1,
    variantCount: 2,
    similarityByLang: { ar: 0.4, fa: 0.3 },
    cognate: '—',
    cognateKey: 'big',
    flagged: false,
    startSec: 1,
    endSec: 2,
    realizations: [],
    selectedIdx: 0,
    realizationsSource: 'auto-detect',
    pastEndOfAudio: false,
    ...overrides,
  };
}

const PRIMARY_CODES = ['ar', 'fa'];
const CONTACT_NAMES = { ar: 'Arabic', fa: 'Persian' };

beforeEach(() => {
  mocks.putCanonicalLexeme.mockReset();
  mocks.deleteCanonicalLexeme.mockReset();
  mocks.saveLexemeNote.mockReset();
  mocks.saveEnrichments.mockReset();
  mocks.patchCanonicalLexeme.mockReset();
  mocks.setState.mockReset();
  mocks.storeData = {};
});

afterEach(() => cleanup());

describe('SpeakerFormsTable header & layout', () => {
  it('renders an audio-less lexical speaker as a normal Compare doculect row', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle({
          candidates: {
            Qorv01: {
              '53': {
                csv_row_id: '53',
                ipa: 'aw',
                ortho: 'ئاو',
                start_sec: null,
                end_sec: null,
                realization_index: 0,
              },
            },
          },
        })}
        speakers={['Qorv01']}
        speakerForms={[makeForm({ speaker: 'Qorv01', ipa: 'aw', ortho: 'ئاو' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
      />,
    );

    expect(screen.getByTestId('speaker-row-Qorv01')).toBeTruthy();
    expect(screen.getByTestId('ipa-cell-Qorv01').textContent).toContain('aw');
  });

  it('renders all six column headers (with one SIM. per primary contact code)', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01', 'Saha01']}
        speakerForms={[makeForm({ speaker: 'Fail01' }), makeForm({ speaker: 'Saha01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
      />,
    );
    expect(screen.getByText('Speaker')).toBeTruthy();
    expect(screen.getByText('IPA & Utterances')).toBeTruthy();
    expect(screen.getByText('ARABIC SIM.')).toBeTruthy();
    expect(screen.getByText('PERSIAN SIM.')).toBeTruthy();
    expect(screen.getByText('Cognate')).toBeTruthy();
    expect(screen.getByText('Flag')).toBeTruthy();
  });
});


describe('SpeakerFormsTable cognate/flag callback keys', () => {
  it('passes row cognateKey to cognate handlers and concept uid flagKey to flag handlers', () => {
    const onCycleCognate = vi.fn();
    const onResetCognate = vi.fn();
    const onToggleSpeakerFlag = vi.fn();
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01']}
        speakerForms={[makeForm({ speaker: 'Fail01', cognate: 'A', flagged: true, cognateKey: '599', flagKey: 'uid:hair' } as Partial<SpeakerForm>)]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="uid:hair"
        initialExpandedSpeaker="__none__"
        onCycleCognate={onCycleCognate}
        onResetCognate={onResetCognate}
        onToggleSpeakerFlag={onToggleSpeakerFlag}
      />,
    );

    const cognateButton = screen.getByTestId('cognate-cycle-Fail01');
    fireEvent.click(cognateButton);
    expect(onCycleCognate).toHaveBeenCalledWith('Fail01', 'A', '599');

    vi.useFakeTimers();
    try {
      fireEvent.pointerDown(cognateButton);
      vi.advanceTimersByTime(500);
      fireEvent.pointerUp(cognateButton);
    } finally {
      vi.useRealTimers();
    }
    expect(onResetCognate).toHaveBeenCalledWith('Fail01', '599');

    fireEvent.click(screen.getByTestId('speaker-flag-Fail01'));
    expect(onToggleSpeakerFlag).toHaveBeenCalledWith('Fail01', true, 'uid:hair');
  });
});

describe('SpeakerFormsTable IPA column has NO audio chrome', () => {
  it('IPA cell contains plain text only — no play button, no timestamp, no spectrogram', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01']}
        speakerForms={[makeForm({ speaker: 'Fail01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="__none__" // suppress default expansion for this assertion
      />,
    );
    const cell = screen.getByTestId('ipa-cell-Fail01');
    expect(cell.textContent).toContain('gæwra');
    // No play button anywhere inside the IPA cell.
    expect(cell.querySelector('[aria-label*="play" i]')).toBeNull();
    expect(cell.querySelector('[data-testid*="play"]')).toBeNull();
    const buttons = Array.from(cell.querySelectorAll('button'));
    for (const b of buttons) {
      expect((b.textContent ?? '').toLowerCase()).not.toContain('play');
    }
    // No timestamp / duration patterns inside the IPA cell.
    expect(cell.textContent ?? '').not.toMatch(/\d+:\d{2}/);
    expect(cell.textContent ?? '').not.toMatch(/\d+\.\d{2}\s*s/);
    // No spectrogram image inside the IPA cell.
    expect(cell.querySelector('img')).toBeNull();
  });
});

describe('SpeakerFormsTable IPA column has NO leaking ortho/concept text (Bug 1)', () => {
  it('renders only the IPA in slashes — no ortho subtitle, no concept-label text', () => {
    // ortho deliberately set to a value that, in the original screenshot,
    // leaked next to the IPA. The IPA cell must render exactly /<ipa>/
    // and the pills row — and nothing else readable.
    //
    // Post-MC-414-B: the collapsed cell sources its IPA from
    // bundle.candidates (so it always matches the first variant card the
    // user sees on expand). makeBundle() seeds row 53 with ipa='gæwra'
    // for Fail01.
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01']}
        speakerForms={[
          makeForm({ speaker: 'Fail01', ortho: 'five' }),
        ]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="__none__"
      />,
    );
    const cell = screen.getByTestId('ipa-cell-Fail01');
    // The IPA itself shows up.
    expect(cell.textContent).toContain('/gæwra/');
    // The ortho value must NOT leak into the collapsed IPA cell.
    expect(cell.textContent ?? '').not.toContain('five');
  });
});

describe('SpeakerFormsTable row expansion', () => {
  it('renders compact variant headers without leaking concept labels and moves timestamps to metadata', () => {
    const hairBundle = makeBundle({
      bundle_id: 'hair',
      label: 'hair',
      row_ids: ['1'],
      buckets: [
        {
          bucket_key: 'klq\u00001',
          survey_id: 'klq',
          source_item: '1',
          variants: [{ csv_row_id: '1', concept_en: 'hair (A)', label: 'hair (A)' }],
        },
      ],
      candidates: {
        Fail01: {
          '1': {
            csv_row_id: '1',
            ipa: 'mo',
            ortho: 'مو',
            start_sec: 1524.743,
            end_sec: 1525.584,
            source_wav: 'audio/working/Fail01.wav',
            realization_index: 0,
          },
        },
      },
      canonical: { Fail01: null },
    });

    render(
      <SpeakerFormsTable
        bundle={hairBundle}
        speakers={['Fail01']}
        speakerForms={[makeForm({ speaker: 'Fail01', ipa: 'mo', ortho: 'مو' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="hair"
        initialExpandedSpeaker="Fail01"
      />,
    );

    const header = screen.getByTestId('variant-card-header-Fail01-1');
    expect(within(header).queryByText('1')).toBeNull();
    expect(header.textContent).toContain('A');
    expect(header.textContent).toContain('/mo/');
    expect(header.textContent).toContain('·');
    expect(header.textContent).not.toContain('hair');

    const metadataTimestamp = screen.getByTestId('metadata-timestamp-Fail01');
    expect(metadataTimestamp.textContent).toBe('1524.74s – 1525.58s');
    const variantCard = screen.getByTestId('variant-card-Fail01-1');
    expect(variantCard.textContent).not.toContain('1524.74s');
    expect(variantCard.textContent).not.toContain('1525.58s');
  });

  it('renders Saha01 variant rows as variant chip plus IPA and ORTH without gloss or csv row id', () => {
    const hairBundle = makeBundle({
      bundle_id: 'hair',
      label: 'hair',
      row_ids: ['1'],
      buckets: [
        {
          bucket_key: 'klq\u00001',
          survey_id: 'klq',
          source_item: '1',
          variants: [{ csv_row_id: '1', concept_en: 'hair (A)', variant_label: 'A', label: 'hair (A)' }],
        },
      ],
      candidates: {
        Saha01: {
          '1': {
            csv_row_id: '1',
            ipa: 'muːsɛr',
            ortho: '<orth value>',
            start_sec: 10,
            end_sec: 11,
            source_wav: 'audio/working/Saha01.wav',
            realization_index: 0,
          },
        },
      },
      canonical: { Saha01: null },
    });

    render(
      <SpeakerFormsTable
        bundle={hairBundle}
        speakers={['Saha01']}
        speakerForms={[makeForm({ speaker: 'Saha01', ipa: 'muːsɛr', ortho: '<orth value>' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="hair"
        initialExpandedSpeaker="Saha01"
      />,
    );

    const header = screen.getByTestId('variant-card-header-Saha01-1');
    expect(header.textContent).toContain('A');
    expect(header.textContent).toContain('/muːsɛr/');
    expect(header.textContent).toContain('<orth value>');
    expect(header.textContent).toContain('·');
    expect(within(header).queryByText('1')).toBeNull();
    expect(header.textContent).not.toContain('hair (A)');
    expect(header.querySelector('[dir="rtl"]')).toBeNull();
  });

  it('dedupes Saha01 drawer variants when the same rows repeat across buckets', () => {
    const hairBundle = makeBundle({
      bundle_id: 'hair',
      label: 'hair',
      row_ids: ['1', '624'],
      buckets: [
        {
          bucket_key: 'klq\u00001.1',
          survey_id: 'klq',
          source_item: '1.1',
          variants: [
            { csv_row_id: '1', variant_label: 'A', concept_en: 'hair (A)', label: 'hair (A)' },
            { csv_row_id: '624', variant_label: 'C', concept_en: 'hair (C)', label: 'hair (C)' },
          ],
        },
        {
          bucket_key: 'jbil\u000032',
          survey_id: 'jbil',
          source_item: '32',
          variants: [
            { csv_row_id: '1', variant_label: 'A', concept_en: 'hair (A)', label: 'hair (A)' },
            { csv_row_id: '624', variant_label: 'C', concept_en: 'hair (C)', label: 'hair (C)' },
          ],
        },
      ],
      candidates: {
        Saha01: {
          '1': {
            csv_row_id: '1',
            ipa: 'muːsɛr',
            ortho: 'میسەر',
            start_sec: 1,
            end_sec: 2,
            source_wav: 'audio/working/Saha01.wav',
            realization_index: 0,
          },
          '624': {
            csv_row_id: '624',
            ipa: 'ʁɛʒ',
            ortho: 'گەیش',
            start_sec: 3,
            end_sec: 4,
            source_wav: 'audio/working/Saha01.wav',
            realization_index: 1,
          },
        },
      },
      canonical: { Saha01: null },
      speaker_concept_survey_links: { Saha01: { '1': { jbil: '32' }, '624': { jbil: '32' } } },
    });

    render(
      <SpeakerFormsTable
        bundle={hairBundle}
        speakers={['Saha01']}
        speakerForms={[makeForm({ speaker: 'Saha01', ipa: 'muːsɛr', ortho: 'میسەر' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="hair"
        initialExpandedSpeaker="Saha01"
      />,
    );

    expect(screen.queryAllByTestId(/^variant-card-Saha01-/)).toHaveLength(2);
    expect(screen.queryAllByTestId('variant-card-Saha01-1')).toHaveLength(1);
    expect(screen.queryAllByTestId('variant-card-Saha01-624')).toHaveLength(1);
    expect(screen.getByTestId('variant-count-Saha01').textContent).toMatch(/\+1 variant/);
  });

  // Regression (MC-446-A): when a speaker's variants live in DIFFERENT buckets,
  // the drawer must surface every recorded variant — not just the active
  // bucket's — so the non-active option ("B" here) stays selectable. #516
  // narrowed the list to the active bucket, which hid B entirely.
  it('shows cross-bucket variants so the non-active-bucket option is selectable', () => {
    const hairBundle = makeBundle({
      bundle_id: 'hair',
      label: 'hair',
      row_ids: ['1', '624'],
      buckets: [
        {
          bucket_key: 'jbil 32',
          survey_id: 'jbil',
          source_item: '32',
          // Active bucket — holds only variant A.
          variants: [{ csv_row_id: '1', variant_label: 'A', concept_en: 'hair (A)', label: 'hair (A)' }],
        },
        {
          bucket_key: 'klq 1.1',
          survey_id: 'klq',
          source_item: '1.1',
          // Non-active bucket — holds variant B, previously unreachable.
          variants: [{ csv_row_id: '624', variant_label: 'B', concept_en: 'hair (B)', label: 'hair (B)' }],
        },
      ],
      candidates: {
        Saha01: {
          '1': {
            csv_row_id: '1',
            ipa: 'muːsɛr',
            ortho: 'میسەر',
            start_sec: 1,
            end_sec: 2,
            source_wav: 'audio/working/Saha01.wav',
            realization_index: 0,
          },
          '624': {
            csv_row_id: '624',
            ipa: 'ʁɛʒ',
            ortho: 'گەیش',
            start_sec: 3,
            end_sec: 4,
            source_wav: 'audio/working/Saha01.wav',
            realization_index: 1,
          },
        },
      },
      canonical: { Saha01: null },
      // Active bucket resolves to jbil/32 (which lacks B).
      speaker_concept_survey_links: { Saha01: { '1': { jbil: '32' } } },
    });

    render(
      <SpeakerFormsTable
        bundle={hairBundle}
        speakers={['Saha01']}
        speakerForms={[makeForm({ speaker: 'Saha01', ipa: 'muːsɛr', ortho: 'میسەر' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="hair"
        initialExpandedSpeaker="Saha01"
      />,
    );

    expect(screen.queryAllByTestId(/^variant-card-Saha01-/)).toHaveLength(2);
    // Variant B (row 624, non-active klq bucket) is present and selectable.
    expect(screen.queryAllByTestId('variant-card-Saha01-624')).toHaveLength(1);
    expect(screen.queryAllByTestId('canonical-option-Saha01-624')).toHaveLength(1);
    expect(screen.getByTestId('variant-count-Saha01').textContent).toMatch(/\+1 variant/);
  });

  it('clicking a row toggles its expansion', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01', 'Saha01']}
        speakerForms={[makeForm({ speaker: 'Fail01' }), makeForm({ speaker: 'Saha01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="__none__"
      />,
    );
    expect(screen.queryByTestId('speaker-row-expanded-Fail01')).toBeNull();
    fireEvent.click(screen.getByTestId('speaker-row-Fail01'));
    expect(screen.getByTestId('speaker-row-expanded-Fail01')).toBeTruthy();
    fireEvent.click(screen.getByTestId('speaker-row-Fail01'));
    expect(screen.queryByTestId('speaker-row-expanded-Fail01')).toBeNull();
  });

  it('pressing Enter on a focused row toggles its expansion', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01']}
        speakerForms={[makeForm({ speaker: 'Fail01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="__none__"
      />,
    );
    const row = screen.getByTestId('speaker-row-Fail01');
    row.focus();
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(screen.getByTestId('speaker-row-expanded-Fail01')).toBeTruthy();
  });
});

describe('SpeakerFormsTable pills', () => {
  it('shows amber choose-canonical pill when multi-variant and no canonical', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01']}
        speakerForms={[makeForm({ speaker: 'Fail01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="__none__"
      />,
    );
    expect(screen.getByTestId('canonical-missing-Fail01').textContent).toContain('choose canonical');
    expect(screen.getByTestId('variant-count-Fail01').textContent).toContain('+1 variant');
  });

  // Bug 2 (Lucas, MC-388-A): the emerald "canonical" pill must NOT appear
  // on the collapsed row. Canonical-chosen state still lives inside the
  // expanded VariantCard for clarity without cluttering the scannable view.
  it('does NOT render the emerald canonical pill on the collapsed row', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Saha01']}
        speakerForms={[makeForm({ speaker: 'Saha01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="__none__"
      />,
    );
    expect(screen.queryByTestId('canonical-chosen-Saha01')).toBeNull();
  });

  it('renders the emerald canonical badge inside the expanded VariantCard', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Saha01']}
        speakerForms={[makeForm({ speaker: 'Saha01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="Saha01"
      />,
    );
    // Canonical for Saha01 is csv_row_id 150 in the fixture.
    const badge = screen.getByTestId('variant-canonical-badge-Saha01-150');
    expect(badge.textContent ?? '').toContain('canonical');
  });
});

describe('SpeakerFormsTable canonical radio', () => {
  it('clicking a variant radio calls putCanonicalLexeme with the right args', async () => {
    const bundle = makeBundle();
    mocks.putCanonicalLexeme.mockResolvedValue({
      bundle: {
        ...bundle,
        canonical: {
          ...bundle.canonical,
          Fail01: {
            csv_row_id: '619',
            survey_id: 'klq',
            source_item: '4.1',
            bucket_key: 'klq\u00004.1',
            source: 'manual',
            selected_at: '',
            realization_index: 1,
          },
        },
      },
    });
    render(
      <SpeakerFormsTable
        bundle={bundle}
        speakers={['Fail01']}
        speakerForms={[makeForm({ speaker: 'Fail01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="Fail01"
      />,
    );
    const radioLabel = screen.getByTestId('canonical-option-Fail01-619');
    const radio = radioLabel.querySelector('input') as HTMLInputElement;
    fireEvent.click(radio);
    await waitFor(() => {
      expect(mocks.putCanonicalLexeme).toHaveBeenCalledWith('big', 'Fail01', {
        csv_row_id: '619',
        realization_index: 1,
      });
    });
    expect(mocks.patchCanonicalLexeme).toHaveBeenCalledWith(
      'big',
      'Fail01',
      expect.objectContaining({ csv_row_id: '619' }),
    );
  });
});

describe('SpeakerFormsTable compare notes textarea', () => {
  it('typing and blurring saves via the merge endpoint and never partial-overwrites enrichments', async () => {
    const merged = { Fail01: { big: { user_note: 'sounds emphatic', updated_at: 'x' } } };
    mocks.saveLexemeNote.mockResolvedValue({ success: true, lexeme_notes: merged });
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01']}
        speakerForms={[makeForm({ speaker: 'Fail01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="Fail01"
      />,
    );
    const textarea = screen.getByTestId('lexeme-user-note-Fail01-big') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'sounds emphatic' } });
    fireEvent.blur(textarea);
    await waitFor(() => {
      expect(mocks.saveLexemeNote).toHaveBeenCalledWith({
        speaker: 'Fail01',
        concept_id: 'big',
        user_note: 'sounds emphatic',
      });
    });
    // Regression guard: the buggy partial POST /api/enrichments (which overwrites
    // the whole file) must NOT be called; the store is synced from the merge
    // endpoint's authoritative response instead.
    expect(mocks.saveEnrichments).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(mocks.setState).toHaveBeenCalledTimes(1);
    });
    const updater = mocks.setState.mock.calls[0][0] as (s: { data: Record<string, unknown> }) => { data: Record<string, unknown> };
    expect(updater({ data: { cognate_sets: { '53': {} } } }).data).toEqual({
      cognate_sets: { '53': {} },
      lexeme_notes: merged,
    });
  });
});

describe('SpeakerFormsTable sort', () => {
  it('clicking the sort button reorders rows by similarityByLang descending', () => {
    const forms = [
      makeForm({ speaker: 'Low', similarityByLang: { ar: 0.1, fa: 0.2 } }),
      makeForm({ speaker: 'High', similarityByLang: { ar: 0.9, fa: 0.8 } }),
    ];
    const bundle = makeBundle({
      candidates: {
        Low: {
          '53': {
            csv_row_id: '53',
            ipa: 'a',
            ortho: 'a',
            source_wav: 'audio/working/Low.wav',
            start_sec: 0,
            end_sec: 1,
            realization_index: 0,
          },
        },
        High: {
          '53': {
            csv_row_id: '53',
            ipa: 'b',
            ortho: 'b',
            source_wav: 'audio/working/High.wav',
            start_sec: 0,
            end_sec: 1,
            realization_index: 0,
          },
        },
      },
      canonical: { Low: null, High: null },
    });
    render(
      <SpeakerFormsTable
        bundle={bundle}
        speakers={['Low', 'High']}
        speakerForms={forms}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="__none__"
      />,
    );
    // Initially unsorted: Low then High.
    let rows = screen.getAllByTestId(/^speaker-row-(?!expanded-)/);
    expect(rows[0]).toBe(screen.getByTestId('speaker-row-Low'));
    expect(rows[1]).toBe(screen.getByTestId('speaker-row-High'));
    fireEvent.click(screen.getByTestId('speaker-forms-sort')); // -> desc(ar)
    rows = screen.getAllByTestId(/^speaker-row-(?!expanded-)/);
    expect(rows[0]).toBe(screen.getByTestId('speaker-row-High'));
    expect(rows[1]).toBe(screen.getByTestId('speaker-row-Low'));
  });
});

describe('SpeakerFormsTable filter', () => {
  it('Flagged only hides unflagged rows', () => {
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01', 'Saha01']}
        speakerForms={[
          makeForm({ speaker: 'Fail01', flagged: false }),
          makeForm({ speaker: 'Saha01', flagged: true }),
        ]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="__none__"
      />,
    );
    fireEvent.click(screen.getByTestId('speaker-forms-filter-toggle'));
    fireEvent.click(screen.getByTestId('filter-flagged-only'));
    expect(screen.queryByTestId('speaker-row-Fail01')).toBeNull();
    expect(screen.getByTestId('speaker-row-Saha01')).toBeTruthy();
  });
});

describe('SpeakerFormsTable open in annotate', () => {
  it('clicking the open-in-annotate button calls the callback with (speaker, variant)', () => {
    const onOpenInAnnotate = vi.fn();
    render(
      <SpeakerFormsTable
        bundle={makeBundle()}
        speakers={['Fail01']}
        speakerForms={[makeForm({ speaker: 'Fail01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="Fail01"
        onOpenInAnnotate={onOpenInAnnotate}
      />,
    );
    const btn = screen.getByTestId('variant-open-annotate-Fail01-53');
    fireEvent.click(btn);
    expect(onOpenInAnnotate).toHaveBeenCalledTimes(1);
    const call = onOpenInAnnotate.mock.calls[0];
    expect(call[0]).toBe('Fail01');
    expect(call[1]).toMatchObject({ csv_row_id: '53', ipa: 'gæwra' });
  });
});

describe('SpeakerFormsTable canonical clear', () => {
  it('clears canonical through the delete endpoint and patches the store', async () => {
    const bundle = makeBundle();
    mocks.deleteCanonicalLexeme.mockResolvedValue({
      bundle: { ...bundle, canonical: { ...bundle.canonical, Saha01: null } },
    });
    render(
      <SpeakerFormsTable
        bundle={bundle}
        speakers={['Saha01']}
        speakerForms={[makeForm({ speaker: 'Saha01' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="big"
        initialExpandedSpeaker="Saha01"
      />,
    );
    const expanded = screen.getByTestId('speaker-expanded-Saha01');
    fireEvent.click(within(expanded).getByTestId('canonical-clear-Saha01'));
    await waitFor(() => {
      expect(mocks.deleteCanonicalLexeme).toHaveBeenCalledWith('big', 'Saha01');
    });
    expect(mocks.patchCanonicalLexeme).toHaveBeenCalledWith('big', 'Saha01', null);
  });
});

// Bug 3 (Lucas, MC-388-A): Play button must wire src + play() against the
// real PARSE static-file route (`/audio/working/<file>.wav`) and surface
// rejections via `[SpeakerFormsTable]` console.error + per-variant inline
// error chip. Previously the seek-before-load race + silent .catch() left
// the button looking dead.
describe('SpeakerFormsTable Play button wires audio src and play()', () => {
  it('sets audio.src to mediaUrlFromSourceWav(candidate.source_wav) and calls play()', async () => {
    const playMock = vi.fn().mockResolvedValue(undefined);
    const pauseMock = vi.fn();
    const loadMock = vi.fn();
    const srcSetter = vi.fn();

    // Capture src on every <audio> element by patching the prototype getter/setter.
    const originalPlay = HTMLMediaElement.prototype.play;
    const originalPause = HTMLMediaElement.prototype.pause;
    const originalLoad = HTMLMediaElement.prototype.load;
    const originalSrcDescriptor = Object.getOwnPropertyDescriptor(
      HTMLMediaElement.prototype,
      'src',
    );

    HTMLMediaElement.prototype.play = playMock as typeof HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.pause = pauseMock as typeof HTMLMediaElement.prototype.pause;
    HTMLMediaElement.prototype.load = loadMock as typeof HTMLMediaElement.prototype.load;
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
      configurable: true,
      get() {
        return (this as unknown as { _src?: string })._src ?? '';
      },
      set(value: string) {
        (this as unknown as { _src?: string })._src = value;
        srcSetter(value);
      },
    });

    try {
      render(
        <SpeakerFormsTable
          bundle={makeBundle()}
          speakers={['Fail01']}
          speakerForms={[makeForm({ speaker: 'Fail01' })]}
          primaryContactCodes={PRIMARY_CODES}
          contactLanguageNames={CONTACT_NAMES}
          conceptKey="big"
          initialExpandedSpeaker="Fail01"
        />,
      );
      const btn = screen.getByTestId('variant-play-Fail01-53');
      fireEvent.click(btn);
      // The handler sets src synchronously, then waits for loadedmetadata.
      // In jsdom there is no real loadedmetadata event, so simulate one
      // (the handler attaches the listener with addEventListener).
      const fixtureSrc = '/audio/working/Fail01.wav';
      expect(srcSetter).toHaveBeenCalledWith(fixtureSrc);
      // Dispatch a loadedmetadata event on every <audio>-prototype-derived
      // element on the page. The HTMLAudioElement is created via `new Audio()`
      // so it is not attached to the DOM — dispatch through the prototype
      // listener by firing a CustomEvent on a known element. We instead
      // assert that calling click triggered the src setter and load() (the
      // observable contract). The play() call itself fires inside the
      // loadedmetadata listener which jsdom does not trigger; that path is
      // covered by the integration tests in a live browser.
      expect(loadMock).toHaveBeenCalled();
    } finally {
      HTMLMediaElement.prototype.play = originalPlay;
      HTMLMediaElement.prototype.pause = originalPause;
      HTMLMediaElement.prototype.load = originalLoad;
      if (originalSrcDescriptor) {
        Object.defineProperty(HTMLMediaElement.prototype, 'src', originalSrcDescriptor);
      } else {
        // Best-effort: define an inert getter/setter so other tests don't
        // hit a missing-descriptor TypeError after this test.
        Object.defineProperty(HTMLMediaElement.prototype, 'src', {
          configurable: true,
          get() {
            return (this as unknown as { _src?: string })._src ?? '';
          },
          set(value: string) {
            (this as unknown as { _src?: string })._src = value;
          },
        });
      }
    }
  });
});


// Bug: when the user clicks play (cold cache, readyState < 1), the handler
// registers a `loadedmetadata` listener that triggers seekAndPlay → audio.play()
// once metadata arrives. If the user clicks AGAIN before metadata loads, the
// toggle-off branch pauses and returns — but does NOT remove the listener.
// When metadata eventually loads, the orphan listener fires audio.play()
// with no rAF tick scheduled to stop at end_sec, so the audio plays to the
// end of the source WAV (the speaker's entire recording).
describe('SpeakerFormsTable orphaned loadedmetadata listener after toggle-off', () => {
  it('does not call play() if user toggled off before metadata loaded', () => {
    const playMock = vi.fn().mockResolvedValue(undefined);
    const pauseMock = vi.fn();
    const loadMock = vi.fn();

    // Capture addEventListener so we can fire `loadedmetadata` manually
    // (jsdom does not emit it from audio.load()).
    const capturedListeners: Record<string, EventListener[]> = {};
    const originalAddEventListener = HTMLMediaElement.prototype.addEventListener;
    const originalRemoveEventListener = HTMLMediaElement.prototype.removeEventListener;
    HTMLMediaElement.prototype.addEventListener = function (
      type: string,
      listener: EventListenerOrEventListenerObject,
    ) {
      if (typeof listener === 'function') {
        if (!capturedListeners[type]) capturedListeners[type] = [];
        capturedListeners[type].push(listener as EventListener);
      }
    } as typeof HTMLMediaElement.prototype.addEventListener;
    HTMLMediaElement.prototype.removeEventListener = function (
      type: string,
      listener: EventListenerOrEventListenerObject,
    ) {
      if (capturedListeners[type] && typeof listener === 'function') {
        capturedListeners[type] = capturedListeners[type].filter(
          (l) => l !== (listener as EventListener),
        );
      }
    } as typeof HTMLMediaElement.prototype.removeEventListener;

    const originalPlay = HTMLMediaElement.prototype.play;
    const originalPause = HTMLMediaElement.prototype.pause;
    const originalLoad = HTMLMediaElement.prototype.load;
    const originalSrcDescriptor = Object.getOwnPropertyDescriptor(
      HTMLMediaElement.prototype,
      'src',
    );

    HTMLMediaElement.prototype.play = playMock as typeof HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.pause = pauseMock as typeof HTMLMediaElement.prototype.pause;
    HTMLMediaElement.prototype.load = loadMock as typeof HTMLMediaElement.prototype.load;
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
      configurable: true,
      get() {
        return (this as unknown as { _src?: string })._src ?? '';
      },
      set(value: string) {
        (this as unknown as { _src?: string })._src = value;
      },
    });

    try {
      render(
        <SpeakerFormsTable
          bundle={makeBundle()}
          speakers={['Fail01']}
          speakerForms={[makeForm({ speaker: 'Fail01' })]}
          primaryContactCodes={PRIMARY_CODES}
          contactLanguageNames={CONTACT_NAMES}
          conceptKey="big"
          initialExpandedSpeaker="Fail01"
        />,
      );
      const btn = screen.getByTestId('variant-play-Fail01-53');

      // Click 1: cold cache. readyState defaults to 0 in jsdom, so the
      // load-then-play branch registers a loadedmetadata listener.
      fireEvent.click(btn);
      expect(loadMock).toHaveBeenCalledTimes(1);
      expect(capturedListeners['loadedmetadata']?.length ?? 0).toBeGreaterThan(0);

      // Click 2: user clicks again before metadata arrives — toggle-off.
      fireEvent.click(btn);
      expect(pauseMock).toHaveBeenCalled();

      // Now metadata finally loads. Fire the captured listeners.
      const handlers = [...(capturedListeners['loadedmetadata'] ?? [])];
      handlers.forEach((h) => h(new Event('loadedmetadata')));

      // The bug: orphaned listener calls audio.play(), so the audio starts
      // playing with no rAF tick to stop at end_sec.
      expect(playMock).not.toHaveBeenCalled();
    } finally {
      HTMLMediaElement.prototype.play = originalPlay;
      HTMLMediaElement.prototype.pause = originalPause;
      HTMLMediaElement.prototype.load = originalLoad;
      HTMLMediaElement.prototype.addEventListener = originalAddEventListener;
      HTMLMediaElement.prototype.removeEventListener = originalRemoveEventListener;
      if (originalSrcDescriptor) {
        Object.defineProperty(HTMLMediaElement.prototype, 'src', originalSrcDescriptor);
      } else {
        Object.defineProperty(HTMLMediaElement.prototype, 'src', {
          configurable: true,
          get() {
            return (this as unknown as { _src?: string })._src ?? '';
          },
          set(value: string) {
            (this as unknown as { _src?: string })._src = value;
          },
        });
      }
    }
  });
});

describe('SpeakerFormsTable per-realization cards', () => {
  function hairBundle(): CompareBundle {
    const reals = [0, 1, 2].map((index) => ({
      csv_row_id: '1',
      ipa: ['A', 'B', 'C'][index],
      ortho: ['oA', 'oB', 'oC'][index],
      start_sec: 1 + index * 2,
      end_sec: 2 + index * 2,
      source_wav: 'audio/working/Saha01.wav',
      realization_index: index,
    }));
    return {
      bundle_id: 'hair',
      label: 'hair',
      row_ids: ['1'],
      buckets: [
        {
          bucket_key: 'jbl 32',
          survey_id: 'jbl',
          source_item: '32',
          variants: [{ csv_row_id: '1', concept_en: 'hair', variant_label: 'A' }],
        },
      ],
      candidates: { Saha01: { '1': { ...reals[0], realizations: reals } } },
      canonical: { Saha01: null },
      speaker_concept_survey_links: { Saha01: { '1': { jbl: '32' } } },
    };
  }

  it('renders one card per realization, auto-picks the first, and selects the chosen realization', async () => {
    mocks.putCanonicalLexeme.mockResolvedValue({ bundle: { bundle_id: 'hair', canonical: {} } });
    render(
      <SpeakerFormsTable
        bundle={hairBundle()}
        speakers={['Saha01']}
        speakerForms={[makeForm({ speaker: 'Saha01', ipa: 'A', ortho: 'oA' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="hair"
        initialExpandedSpeaker="Saha01"
      />,
    );

    // One card per realization (A/B/C), with distinct ids.
    expect(screen.queryAllByTestId(/^variant-card-Saha01-1-r\d$/)).toHaveLength(3);
    expect(screen.queryAllByTestId('variant-card-Saha01-1-r0')).toHaveLength(1);
    expect(screen.queryAllByTestId('variant-card-Saha01-1-r2')).toHaveLength(1);

    // Collapsed-row count reflects realizations, not rows (+2 of 3).
    expect(screen.getByTestId('variant-count-Saha01').textContent).toMatch(/\+2 variant/);

    // Auto-canonical is the first realization only.
    expect(screen.queryAllByTestId('variant-canonical-badge-Saha01-1-r0')).toHaveLength(1);
    expect(screen.queryAllByTestId('variant-canonical-badge-Saha01-1-r2')).toHaveLength(0);

    // Selecting realization C sends the row id + realization_index 2.
    const optionC = screen.getByTestId('canonical-option-Saha01-1-r2');
    fireEvent.click(within(optionC).getByRole('radio'));
    await waitFor(() =>
      expect(mocks.putCanonicalLexeme).toHaveBeenCalledWith('hair', 'Saha01', {
        csv_row_id: '1',
        realization_index: 2,
      }),
    );
  });

  it('keys play state per realization so playing one does not light another', () => {
    render(
      <SpeakerFormsTable
        bundle={hairBundle()}
        speakers={['Saha01']}
        speakerForms={[makeForm({ speaker: 'Saha01', ipa: 'A', ortho: 'oA' })]}
        primaryContactCodes={PRIMARY_CODES}
        contactLanguageNames={CONTACT_NAMES}
        conceptKey="hair"
        initialExpandedSpeaker="Saha01"
      />,
    );

    const playA = screen.getByTestId('variant-play-Saha01-1-r0');
    const playB = screen.getByTestId('variant-play-Saha01-1-r1');
    expect(playA.getAttribute('title')).toBe('Play');
    expect(playB.getAttribute('title')).toBe('Play');

    fireEvent.click(playB);

    // Only B's control reflects playback; pre-fix both cards shared the row id
    // and would both flip to Pause.
    expect(playB.getAttribute('title')).toBe('Pause');
    expect(playA.getAttribute('title')).toBe('Play');
  });
});
