// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useTagStore } from '@/stores/tagStore';
import type { Tag } from '@/api/types';
import { TagsPanelSection } from './TagsPanelSection';

const archaic: Tag = { id: 't1', label: 'Archaic', color: '#3554B8' };
const dialectal: Tag = { id: 't2', label: 'Dialectal', color: '#0f766e' };

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
