import { useCallback, useState } from 'react';
import { importTagCsv } from '../api/client';
import { useTagStore } from '../stores/tagStore';

interface UseTagImportOptions {
  promptForTagName?: (defaultName: string) => string | null;
}

function defaultPromptForTagName(defaultName: string): string | null {
  return window.prompt('Tag name for this concept list:', defaultName);
}

function formatImportSummary(result: { tagName: string; matchedCount: number; missedCount: number; skippedExistingCount?: number }): string {
  const missedNote = result.missedCount > 0 ? `, ${result.missedCount} unmatched` : '';
  const skippedNote = result.skippedExistingCount && result.skippedExistingCount > 0
    ? `, skipped: ${result.skippedExistingCount} tags already existed`
    : '';
  return `Tag "${result.tagName}": ${result.matchedCount} concepts assigned${missedNote}${skippedNote}`;
}

export function useTagImport(options: UseTagImportOptions = {}) {
  const syncTagsFromServer = useTagStore((store) => store.syncFromServer);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clearStatus = useCallback(() => {
    setSummary(null);
    setError(null);
  }, []);

  const importFile = useCallback(async (file: File) => {
    clearStatus();
    const defaultName = file.name.replace(/\.csv$/i, '');
    const promptForTagName = options.promptForTagName ?? defaultPromptForTagName;
    const tagName = promptForTagName(defaultName);
    if (tagName === null) {
      return;
    }

    try {
      const result = await importTagCsv(file, { tagName: tagName.trim() || defaultName });
      setSummary(formatImportSummary(result));
      await syncTagsFromServer();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [clearStatus, options.promptForTagName, syncTagsFromServer]);

  return { summary, error, importFile, clearStatus };
}
