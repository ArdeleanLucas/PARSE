// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useTagStore } from '@/stores/tagStore';
import { useAnnotationStore } from '@/stores/annotationStore';
import { useUIStore } from '@/stores/uiStore';
import type { AnnotationRecord, Tag } from '@/api/types';
import { TagsPanelSection } from './TagsPanelSection';

const archaic: Tag = { id: 't1', label: 'Archaic', color: '#3554B8' };
const dialectal: Tag = { id: 't2', label: 'Dialectal', color: '#0f766e' };

function makeRecord(speaker: string, conceptTags: Record<string, string[]> = {}): AnnotationRecord {
  return {
    speaker,
    source_wav: `${speaker}.wav`,
    source_audio: `${speaker}.wav`,
    tiers: {},
    concept_tags: conceptTags,
  } as AnnotationRecord;
}

function resetStore() {
  useTagStore.setState(useTagStore.getInitialState(), true);
  useAnnotationStore.setState(useAnnotationStore.getInitialState(), true);
  useUIStore.setState(useUIStore.getInitialState(), true);
}

beforeEach(() => {
  resetStore();
  useTagStore.setState({ tags: [archaic, dialectal] });
  useUIStore.setState({ activeSpeaker: 'Fail01' });
  useAnnotationStore.setState({
    records: {
      Fail01: makeRecord('Fail01', { sister: ['t1'] }),
      Mand01: makeRecord('Mand01', { brother: ['t1'], sister: ['t2'] }),
    },
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  resetStore();
});

describe('TagsPanelSection', () => {
  it('renders vocabulary tag rows with name, color dot, and header trailing', () => {
    render(<TagsPanelSection conceptId="sister" />);

    expect(screen.getByText('Concept Tags')).toBeTruthy();
    expect(screen.getByLabelText('Tag vocabulary size').textContent).toBe('2 tags');
    expect(screen.getByText('Archaic')).toBeTruthy();
    expect(screen.getByText('Dialectal')).toBeTruthy();
    const row = screen.getByText('Archaic').closest('.tag-row') as HTMLElement;
    const dot = row.querySelector('.tag-dot') as HTMLElement;
    expect(dot.style.backgroundColor).toBe('rgb(53, 84, 184)');
  });

  it('search filters visible rows by case-insensitive substring', () => {
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.change(screen.getByLabelText('Search tags'), { target: { value: 'dial' } });

    expect(screen.queryByText('Archaic')).toBeNull();
    expect(screen.getByText('Dialectal')).toBeTruthy();
  });



  it('toggles tag membership for the active speaker concept', () => {
    const setConceptTag = vi.fn();
    const clearConceptTag = vi.fn();
    useAnnotationStore.setState({ setConceptTag, clearConceptTag });

    render(<TagsPanelSection conceptId="sister" />);

    const archaicButton = screen.getByRole('button', { name: /Archaic/i });
    const dialectalButton = screen.getByRole('button', { name: /Dialectal/i });
    expect(archaicButton.getAttribute('aria-pressed')).toBe('true');
    expect(dialectalButton.getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(dialectalButton);
    expect(setConceptTag).toHaveBeenCalledWith('Fail01', 'sister', 't2');

    fireEvent.click(archaicButton);
    expect(clearConceptTag).toHaveBeenCalledWith('Fail01', 'sister', 't1');
  });

  it('shows active-speaker applied count and global per-tag usage counts', () => {
    render(<TagsPanelSection conceptId="sister" />);

    expect(screen.getByLabelText('Applied tag count').textContent).toBe('1 of 2');
    expect(screen.getByTestId('tag-usage-t1').textContent).toBe('2');
    expect(screen.getByTestId('tag-usage-t2').textContent).toBe('1');
  });

  it('Create tag expands and submits to addTag', async () => {
    const addTag = vi.fn().mockReturnValue({ id: 't3', label: 'Compound', color: '#7c3aed' });
    useTagStore.setState({ addTag });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Create tag/i }));
    fireEvent.change(screen.getByPlaceholderText('Tag name'), { target: { value: 'Compound' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(addTag).toHaveBeenCalledWith('Compound', '#3554B8'));
  });

  it('shows an inline error when addTag rejects with a 409 conflict', async () => {
    const addTag = vi.fn(() => { throw new Error('409: tag name already exists'); });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    useTagStore.setState({ addTag });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Create tag/i }));
    fireEvent.change(screen.getByPlaceholderText('Tag name'), { target: { value: 'Archaic' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(screen.getByText('409: tag name already exists')).toBeTruthy());
    expect(warn).toHaveBeenCalledWith('[TagsPanelSection] create tag failed:', expect.any(Error));
  });

  it('empty registry shows the create affordance and empty-state hint', () => {
    useTagStore.setState({ tags: [] });
    render(<TagsPanelSection conceptId="sister" />);

    expect(screen.getByText('No tags yet. Create one below.')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Create tag/i })).toBeTruthy();
    expect(within(screen.getByLabelText('Concept tag list')).queryAllByRole('button')).toHaveLength(0);
  });
});
