// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useTagsStore, type Tag } from '@/state/tags';
import { TagsPanelSection } from './TagsPanelSection';

const archaic: Tag = { id: 't1', name: 'Archaic', color: '#3554B8', createdAt: '2026-05-01T00:00:00.000Z' };
const dialectal: Tag = { id: 't2', name: 'Dialectal', color: '#0f766e', createdAt: '2026-05-01T00:00:00.000Z' };

function resetStore() {
  useTagsStore.setState(useTagsStore.getInitialState(), true);
}

beforeEach(() => {
  resetStore();
  useTagsStore.setState({
    loaded: true,
    tags: [archaic, dialectal],
    attachmentsByConcept: { sister: ['t1'], water: ['t1'], fire: ['t2'] },
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  resetStore();
});

describe('TagsPanelSection', () => {
  it('renders tag rows with name, color dot, usage count, and header trailing', () => {
    render(<TagsPanelSection conceptId="sister" />);

    expect(screen.getByText('Concept tags')).toBeTruthy();
    expect(screen.getByLabelText('Applied concept tags').textContent).toBe('1 of 2');
    expect(screen.getByText('Archaic')).toBeTruthy();
    expect(screen.getByText('Dialectal')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
    const row = screen.getByRole('button', { name: /Archaic/i });
    const dot = row.querySelector('.tag-dot') as HTMLElement;
    expect(dot.style.backgroundColor).toBe('rgb(53, 84, 184)');
  });

  it('clicking an unchecked row calls attachTag for the current concept', async () => {
    const attachTag = vi.fn().mockResolvedValue(undefined);
    useTagsStore.setState({ attachTag });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Dialectal/i }));

    expect(attachTag).toHaveBeenCalledWith('sister', 't2');
  });

  it('clicking a checked row calls detachTag for the current concept', () => {
    const detachTag = vi.fn().mockResolvedValue(undefined);
    useTagsStore.setState({ detachTag });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Archaic/i }));

    expect(detachTag).toHaveBeenCalledWith('sister', 't1');
  });

  it('search filters visible rows by case-insensitive substring', () => {
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.change(screen.getByLabelText('Search tags'), { target: { value: 'dial' } });

    expect(screen.queryByText('Archaic')).toBeNull();
    expect(screen.getByText('Dialectal')).toBeTruthy();
  });

  it('Create tag expands and submits to createTag', async () => {
    const createTag = vi.fn().mockResolvedValue({ id: 't3', name: 'Compound', color: '#7c3aed', createdAt: '2026-05-01T00:00:00.000Z' });
    useTagsStore.setState({ createTag });
    render(<TagsPanelSection conceptId="sister" />);

    fireEvent.click(screen.getByRole('button', { name: /Create tag/i }));
    fireEvent.change(screen.getByLabelText('Tag name'), { target: { value: 'Compound' } });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    await waitFor(() => expect(createTag).toHaveBeenCalledWith('Compound', '#3554B8'));
  });

  it('empty registry shows the create affordance and empty-state hint', () => {
    useTagsStore.setState({ tags: [], attachmentsByConcept: {} });
    render(<TagsPanelSection conceptId="sister" />);

    expect(screen.getByText('No tags yet. Create one below.')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Create tag/i })).toBeTruthy();
    expect(within(screen.getByLabelText('Concept tag list')).queryAllByRole('button')).toHaveLength(0);
  });
});
