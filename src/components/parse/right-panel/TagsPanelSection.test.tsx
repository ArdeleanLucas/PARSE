// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useTagStore } from '@/stores/tagStore';
import type { Tag } from '@/api/types';
import { TagsPanelSection } from './TagsPanelSection';

const archaic: Tag = { id: 't1', label: 'Archaic', color: '#3554B8', concepts: ['sister', 'water'], lexemeTargets: [] };
const dialectal: Tag = { id: 't2', label: 'Dialectal', color: '#0f766e', concepts: ['fire'], lexemeTargets: [] };

function resetStore() {
  useTagStore.setState(useTagStore.getInitialState(), true);
}

beforeEach(() => {
  resetStore();
  useTagStore.setState({ tags: [archaic, dialectal] });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  resetStore();
});

describe('TagsPanelSection', () => {
  it('renders tag rows with name, color dot, usage count, and header trailing', () => {
    render(<TagsPanelSection conceptId="sister" />);

    expect(screen.getByText('Concept Tags')).toBeTruthy();
    expect(screen.getByLabelText('Applied concept tags').textContent).toBe('1 of 2');
    expect(screen.getByText('Archaic')).toBeTruthy();
    expect(screen.getByText('Dialectal')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
    const row = screen.getByRole('button', { name: /Archaic/i });
    const dot = row.querySelector('.tag-dot') as HTMLElement;
    expect(dot.style.backgroundColor).toBe('rgb(53, 84, 184)');
  });

  it('clicking an unchecked row calls tagConcept for the current concept', () => {
    const tagConcept = vi.fn();
    useTagStore.setState({ tagConcept });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Dialectal/i }));

    expect(tagConcept).toHaveBeenCalledWith('t2', 'sister');
  });

  it('clicking a checked row calls untagConcept for the current concept', () => {
    const untagConcept = vi.fn();
    useTagStore.setState({ untagConcept });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Archaic/i }));

    expect(untagConcept).toHaveBeenCalledWith('t1', 'sister');
  });

  it('search filters visible rows by case-insensitive substring', () => {
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.change(screen.getByLabelText('Search tags'), { target: { value: 'dial' } });

    expect(screen.queryByText('Archaic')).toBeNull();
    expect(screen.getByText('Dialectal')).toBeTruthy();
  });

  it('Create tag expands and submits to addTag', async () => {
    const addTag = vi.fn().mockReturnValue({ id: 't3', label: 'Compound', color: '#7c3aed', concepts: [], lexemeTargets: [] });
    useTagStore.setState({ addTag });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Create tag/i }));
    fireEvent.change(screen.getByLabelText('Tag name'), { target: { value: 'Compound' } });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await waitFor(() => expect(addTag).toHaveBeenCalledWith('Compound', '#3554B8'));
  });

  it('shows an inline error when addTag rejects with a 409 conflict', async () => {
    const addTag = vi.fn(() => { throw new Error('409: tag name already exists'); });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    useTagStore.setState({ addTag });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Create tag/i }));
    fireEvent.change(screen.getByLabelText('Tag name'), { target: { value: 'Archaic' } });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await waitFor(() => expect(screen.getByText('Name already exists')).toBeTruthy());
    expect(screen.getByLabelText('Tag name').getAttribute('aria-invalid')).toBe('true');
    expect(warn).toHaveBeenCalledWith('[tags] create failed', expect.any(Error));
  });

  it('typing in the name input clears the conflict error', async () => {
    const addTag = vi.fn(() => { throw new Error('409: tag name already exists'); });
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    useTagStore.setState({ addTag });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Create tag/i }));
    fireEvent.change(screen.getByLabelText('Tag name'), { target: { value: 'Archaic' } });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));
    await waitFor(() => expect(screen.getByText('Name already exists')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('Tag name'), { target: { value: 'Archaic 2' } });

    expect(screen.queryByText('Name already exists')).toBeNull();
    expect(screen.getByLabelText('Tag name').getAttribute('aria-invalid')).toBeNull();
  });

  it('empty registry shows the create affordance and empty-state hint', () => {
    useTagStore.setState({ tags: [] });
    render(<TagsPanelSection conceptId="sister" />);

    expect(screen.getByText('No tags yet. Create one below.')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Create tag/i })).toBeTruthy();
    expect(within(screen.getByLabelText('Concept tag list')).queryAllByRole('button')).toHaveLength(0);
  });
});
