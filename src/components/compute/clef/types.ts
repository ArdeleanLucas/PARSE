import type {
  AuthStatus,
  ClefCatalogEntry,
  ClefConfigStatus,
  ClefProviderEntry,
  ClefSourceCitation,
  ClefSourcesReport,
  ClefSourcesReportLanguage,
  ContactLexemePopulateResult,
} from "../../../api/types";

export const MAX_PRIMARY = 2;

export type ClefConfigModalTab = "languages" | "populate" | "settings";

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
  warnings?: ContactLexemePopulateResult["warnings"];
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
  mode?: "compact" | "detailed";
  providerStatuses?: Record<string, ProviderStatusKind>;
  authExpandedProviderId?: string | null;
  onExpandAuth?: (providerId: string | null) => void;
  onAuthSaved?: (providerId: string, status: AuthStatus) => void;
}

export type ProviderStatusKind = "ready" | "needs_auth" | "connected" | "no_data" | "missing_file" | "error";

export interface ProviderApiKeyFormProps {
  defaultProvider?: "xai" | "openai";
  onCancel: () => void;
  onSaved: (status: AuthStatus) => void | Promise<void>;
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

export interface ConceptProviderMatrixProps {
  report: ClefSourcesReport;
}

export interface UseClefConfigResult {
  loading: boolean;
  error: string | null;
  setError: (value: string | null) => void;
  catalog: ClefCatalogEntry[];
  providers: ClefProviderEntry[];
  providerStatuses: Record<string, ProviderStatusKind>;
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
  refreshAuthStatus: () => Promise<AuthStatus>;
  refreshStatus: () => Promise<ClefConfigStatus>;
  togglePrimary: (code: string) => void;
  toggleSecondary: (code: string) => void;
  addCustom: () => void;
  applyDefaults: () => void;
  buildPayload: () => {
    primary_contact_languages: string[];
    languages: Array<{ code: string; name: string; family?: string; script?: string }>;
  };
}
