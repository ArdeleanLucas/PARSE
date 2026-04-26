// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useParseUIModals } from '../useParseUIModals';

describe('useParseUIModals', () => {
  it('opens and closes the import and comments import modals independently', () => {
    const { result } = renderHook(() => useParseUIModals());

    expect(result.current.import.isOpen).toBe(false);
    expect(result.current.commentsImport.isOpen).toBe(false);

    act(() => {
      result.current.import.open();
      result.current.commentsImport.open();
    });

    expect(result.current.import.isOpen).toBe(true);
    expect(result.current.commentsImport.isOpen).toBe(true);

    act(() => {
      result.current.import.close();
      result.current.commentsImport.close();
    });

    expect(result.current.import.isOpen).toBe(false);
    expect(result.current.commentsImport.isOpen).toBe(false);
  });

  it('tracks the run modal payload and clears it on close', () => {
    const { result } = renderHook(() => useParseUIModals());

    act(() => {
      result.current.run.open('Run full pipeline', ['normalize', 'stt']);
    });

    expect(result.current.run.state).toEqual({
      title: 'Run full pipeline',
      fixedSteps: ['normalize', 'stt'],
    });

    act(() => {
      result.current.run.close();
    });

    expect(result.current.run.state).toBeNull();
  });

  it('supports parameterized CLEF opens and resets to the languages tab on close', () => {
    const { result } = renderHook(() => useParseUIModals());

    act(() => {
      result.current.clef.open('populate');
    });

    expect(result.current.clef.isOpen).toBe(true);
    expect(result.current.clef.initialTab).toBe('populate');

    act(() => {
      result.current.clef.close();
    });

    expect(result.current.clef.isOpen).toBe(false);
    expect(result.current.clef.initialTab).toBe('languages');
  });

  it('opens and closes the sources report and batch report modals', () => {
    const { result } = renderHook(() => useParseUIModals());

    act(() => {
      result.current.sourcesReport.open();
      result.current.batchReport.open();
    });

    expect(result.current.sourcesReport.isOpen).toBe(true);
    expect(result.current.batchReport.isOpen).toBe(true);

    act(() => {
      result.current.sourcesReport.close();
      result.current.batchReport.close();
    });

    expect(result.current.sourcesReport.isOpen).toBe(false);
    expect(result.current.batchReport.isOpen).toBe(false);
  });
});
