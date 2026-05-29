// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SpeakersSection } from './SpeakersSection';

afterEach(() => {
  cleanup();
});

function renderSection(overrides: Partial<Parameters<typeof SpeakersSection>[0]> = {}) {
  const onDeleteSpeaker = vi.fn();
  const onToggleSpeaker = vi.fn();
  render(
    <SpeakersSection
      currentMode="compare"
      selectedSpeakers={['Saha01']}
      speakers={['Saha01', 'Qasr01']}
      speakerPicker={null}
      onSpeakerSelect={vi.fn()}
      onAddSpeaker={vi.fn()}
      onToggleSpeaker={onToggleSpeaker}
      onSelectAllSpeakers={vi.fn()}
      onClearSpeakers={vi.fn()}
      onDeleteSpeaker={onDeleteSpeaker}
      {...overrides}
    />,
  );
  return { onDeleteSpeaker, onToggleSpeaker };
}

describe('SpeakersSection context menu', () => {
  it('opens a delete menu on right-click and fires onDeleteSpeaker', () => {
    const { onDeleteSpeaker } = renderSection();
    const chip = screen.getByRole('button', { name: /Qasr01/ });

    fireEvent.contextMenu(chip);
    const deleteItem = screen.getByTestId('speaker-context-delete');
    fireEvent.click(deleteItem);

    expect(onDeleteSpeaker).toHaveBeenCalledTimes(1);
    expect(onDeleteSpeaker).toHaveBeenCalledWith('Qasr01');
  });

  it('does not trigger the left-click toggle when right-clicking', () => {
    const { onToggleSpeaker } = renderSection();
    const chip = screen.getByRole('button', { name: /Qasr01/ });

    fireEvent.contextMenu(chip);

    expect(onToggleSpeaker).not.toHaveBeenCalled();
  });

  it('right-click works in annotate mode too', () => {
    const { onDeleteSpeaker } = renderSection({ currentMode: 'annotate' });
    const chip = screen.getByRole('button', { name: /Qasr01/ });

    fireEvent.contextMenu(chip);
    fireEvent.click(screen.getByTestId('speaker-context-delete'));

    expect(onDeleteSpeaker).toHaveBeenCalledWith('Qasr01');
  });

  it('renders no context menu when onDeleteSpeaker is not provided', () => {
    renderSection({ onDeleteSpeaker: undefined });
    const chip = screen.getByRole('button', { name: /Qasr01/ });

    fireEvent.contextMenu(chip);

    expect(screen.queryByTestId('speaker-context-menu')).toBeNull();
  });
});
