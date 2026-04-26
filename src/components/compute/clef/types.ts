import type {
  ClefCatalogEntry,
  ClefConfigStatus,
  ClefProviderEntry,
  ClefSourceCitation,
  ClefSourcesReport,
  ClefSourcesReportLanguage,
} from "../../../api/types";

export const MAX_PRIMARY = 2;

export type ClefConfigModalTab = "languages" | "populate";

export interface ClefConfigModalProps {
  open: boolean;
  onClose: () => void;
  onSaved?: (primary: string[]) => void;
  onPopulateStarted?: (jobId: string) => void;
  initialTab?: ClefConfigModalTab;
}

export interface ClefSourcesReportModalProps {
  open: boolean;
  onClose: () => void;
}

export interface PopulateSummary {
  state: "ok" | "empty" | "error";
  totalFilled: number;
  perLang: Record<string, number>;
  warning: string | null;
}

export interface ClefPopulateSummaryBannerProps {
  summary: PopulateSummary;
  onDismiss: () => void;
  onRetryWithProviders: () => void;
}

export interface ConfigFormProps {
  primary: string[];
  secondary: Set<string>;
  allLanguages: ClefCatalogEntry[];
  filtered: ClefCatalogEntry[];
  search: string;
  setSearch: (value: string) => void;
  highlightIdx: number;
  setHighlightIdx: (value: number | ((current: number) => number)) => void;
  togglePrimary: (code: string) => void;
  toggleSecondary: (code: string) => void;
  customCode: string;
  setCustomCode: (value: string) => void;
  customName: string;
  setCustomName: (value: string) => void;
  addCustom: () => void;
}

export interface ProviderSelectorProps {
  providers: ClefProviderEntry[];
  selectedProviders: Set<string>;
  toggleProvider: (providerId: string) => void;
  overwrite: boolean;
  setOverwrite: (value: boolean) => void;
  saving: boolean;
}

export interface CoverageMatrixProps {
  report: ClefSourcesReport;
  activeLang: string | null;
  setActiveLang: (code: string) => void;
  activeLangEntry: ClefSourcesReportLanguage | null;
}

export interface SourcesTableProps {
  entry: ClefSourcesReportLanguage;
  citations: Record<string, ClefSourceCitation>;
}

export interface UseClefConfigResult {
  loading: boolean;
  error: string | null;
  setError: (value: string | null) => void;
  catalog: ClefCatalogEntry[];
  providers: ClefProviderEntry[];
  status: ClefConfigStatus | null;
  primary: string[];
  secondary: Set<string>;
  customCode: string;
  customName: string;
  search: string;
  tab: ClefConfigModalTab;
  highlightIdx: number;
  allLanguages: ClefCatalogEntry[];
  filtered: ClefCatalogEntry[];
  setTab: (tab: ClefConfigModalTab) => void;
  setSearch: (value: string) => void;
  setHighlightIdx: (value: number | ((current: number) => number)) => void;
  setCustomCode: (value: string) => void;
  setCustomName: (value: string) => void;
  togglePrimary: (code: string) => void;
  toggleSecondary: (code: string) => void;
  addCustom: () => void;
  applyDefaults: () => void;
  buildPayload: () => {
    primary_contact_languages: string[];
    languages: Array<{ code: string; name: string; family?: string; script?: string }>;
  };
}
