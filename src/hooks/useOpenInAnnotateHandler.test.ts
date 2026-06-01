// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useOpenInAnnotateHandler } from './useOpenInAnnotateHandler';
import { usePlaybackStore } from '../stores/playbackStore';
import { useCompareReturnStore } from '../stores/compareReturnStore';

describe('useOpenInAnnotateHandler realization selection', () => {
  beforeEach(() => {
    useCompareReturnStore.getState().clear?.();
  });

  function setup() {
    const setCurrentMode = vi.fn();
    const setSelectedRealizationKey = vi.fn();
    const seedActiveConceptKey = vi.fn();
    const requestSeek = vi.spyOn(usePlaybackStore.getState(), 'requestSeek');
    const setActiveSpeaker = vi.spyOn(usePlaybackStore.getState(), 'setActiveSpeaker');
    const { result } = renderHook(() =>
      useOpenInAnnotateHandler({
        conceptId: 7,
        conceptKey: 'concept-7',
        setCurrentMode,
        setSelectedRealizationKey,
        seedActiveConceptKey,
      }),
    );
    return { handler: result.current, setCurrentMode, setSelectedRealizationKey, seedActiveConceptKey, requestSeek, setActiveSpeaker };
  }

  it('selects the clicked realization interval (<row>:<index>) and seeks to its start', () => {
    const { handler, setCurrentMode, setSelectedRealizationKey, seedActiveConceptKey, requestSeek } = setup();

    act(() => {
      handler('Saha01', { csv_row_id: '1', start_sec: 12.5, realizationIndex: 2 });
    });

    // Annotate opens on the exact interval the user clicked (row 1, realization 2).
    expect(setSelectedRealizationKey).toHaveBeenCalledWith('1:2');
    expect(requestSeek).toHaveBeenCalledWith(12.5);
    expect(setCurrentMode).toHaveBeenCalledWith('annotate');
    // Seeds the mode-switch resolver with the clicked row, BEFORE the mode flip,
    // so a grouped concept resolves to this row instead of clobbering to A.
    expect(seedActiveConceptKey).toHaveBeenCalledWith('1');
    expect(seedActiveConceptKey.mock.invocationCallOrder[0])
      .toBeLessThan(setCurrentMode.mock.invocationCallOrder[0]);
  });

  it('defaults a single-realization row to interval 0', () => {
    const { handler, setSelectedRealizationKey } = setup();

    act(() => {
      handler('Saha01', { csv_row_id: '53', start_sec: null });
    });

    expect(setSelectedRealizationKey).toHaveBeenCalledWith('53:0');
  });
});
