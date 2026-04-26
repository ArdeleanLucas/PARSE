import { useCallback, useState } from 'react';
import type { ClefConfigModalTab } from '../components/compute/ClefConfigModal';
import type { PipelineStepId } from '../components/shared/TranscriptionRunModal';

export interface ParseUIRunModalState {
  title: string;
  fixedSteps: PipelineStepId[] | undefined;
}

export interface UseParseUIModalsResult {
  import: {
    isOpen: boolean;
    open: () => void;
    close: () => void;
  };
  commentsImport: {
    isOpen: boolean;
    open: () => void;
    close: () => void;
  };
  run: {
    state: ParseUIRunModalState | null;
    open: (title: string, fixedSteps?: PipelineStepId[]) => void;
    close: () => void;
  };
  batchReport: {
    isOpen: boolean;
    open: () => void;
    close: () => void;
  };
  clef: {
    isOpen: boolean;
    initialTab: ClefConfigModalTab;
    open: (tab?: ClefConfigModalTab) => void;
    close: () => void;
  };
  sourcesReport: {
    isOpen: boolean;
    open: () => void;
    close: () => void;
  };
}

export function useParseUIModals(): UseParseUIModalsResult {
  const [importOpen, setImportOpen] = useState(false);
  const [commentsImportOpen, setCommentsImportOpen] = useState(false);
  const [runModalState, setRunModalState] = useState<ParseUIRunModalState | null>(null);
  const [batchReportOpen, setBatchReportOpen] = useState(false);
  const [clefModalOpen, setClefModalOpen] = useState(false);
  const [clefInitialTab, setClefInitialTab] = useState<ClefConfigModalTab>('languages');
  const [sourcesReportOpen, setSourcesReportOpen] = useState(false);

  const openImport = useCallback(() => setImportOpen(true), []);
  const closeImport = useCallback(() => setImportOpen(false), []);

  const openCommentsImport = useCallback(() => setCommentsImportOpen(true), []);
  const closeCommentsImport = useCallback(() => setCommentsImportOpen(false), []);

  const openRun = useCallback((title: string, fixedSteps?: PipelineStepId[]) => {
    setRunModalState({ title, fixedSteps });
  }, []);
  const closeRun = useCallback(() => setRunModalState(null), []);

  const openBatchReport = useCallback(() => setBatchReportOpen(true), []);
  const closeBatchReport = useCallback(() => setBatchReportOpen(false), []);

  const openClef = useCallback((tab: ClefConfigModalTab = 'languages') => {
    setClefInitialTab(tab);
    setClefModalOpen(true);
  }, []);
  const closeClef = useCallback(() => {
    setClefModalOpen(false);
    setClefInitialTab('languages');
  }, []);

  const openSourcesReport = useCallback(() => setSourcesReportOpen(true), []);
  const closeSourcesReport = useCallback(() => setSourcesReportOpen(false), []);

  return {
    import: { isOpen: importOpen, open: openImport, close: closeImport },
    commentsImport: { isOpen: commentsImportOpen, open: openCommentsImport, close: closeCommentsImport },
    run: { state: runModalState, open: openRun, close: closeRun },
    batchReport: { isOpen: batchReportOpen, open: openBatchReport, close: closeBatchReport },
    clef: { isOpen: clefModalOpen, initialTab: clefInitialTab, open: openClef, close: closeClef },
    sourcesReport: { isOpen: sourcesReportOpen, open: openSourcesReport, close: closeSourcesReport },
  };
}
