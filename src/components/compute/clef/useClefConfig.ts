import { useCallback, useEffect, useMemo, useState } from "react";
import { getAuthStatus, getClefCatalog, getClefConfig, getClefProviders } from "../../../api/client";
import type { AuthStatus } from "../../../api/types";
import type { ClefCatalogEntry } from "../../../api/types";
import { MAX_PRIMARY, type ClefConfigModalTab, type UseClefConfigResult } from "./types";
import { normalizeClefProviders } from "./shared";

function buildProviderStatuses(authStatus: AuthStatus | null, providerIds: string[]): Record<string, UseClefConfigResult["providerStatuses"][string]> {
  const out: Record<string, UseClefConfigResult["providerStatuses"][string]> = {};
  const grokipediaConnected = Boolean(authStatus?.authenticated && ["xai", "openai"].includes((authStatus.provider ?? "").toLowerCase()));
  for (const id of providerIds) {
    out[id] = id === "grokipedia"
      ? (grokipediaConnected ? "connected" : "needs_auth")
      : "ready";
  }
  return out;
}

export function useClefConfig(open: boolean, initialTab: ClefConfigModalTab): UseClefConfigResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<ClefCatalogEntry[]>([]);
  const [providers, setProviders] = useState<UseClefConfigResult["providers"]>([]);
  const [providerStatuses, setProviderStatuses] = useState<UseClefConfigResult["providerStatuses"]>({});
  const [status, setStatus] = useState<UseClefConfigResult["status"]>(null);
  const [primary, setPrimary] = useState<string[]>([]);
  const [secondary, setSecondary] = useState<Set<string>>(new Set());
  const [customCode, setCustomCode] = useState("");
  const [customName, setCustomName] = useState("");
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<ClefConfigModalTab>(initialTab);
  const [highlightIdx, setHighlightIdx] = useState(0);

  const allLanguages = useMemo(() => {
    const byCode = new Map<string, ClefCatalogEntry>();
    for (const entry of catalog) byCode.set(entry.code, entry);
    if (status) {
      for (const language of status.languages) {
        if (!byCode.has(language.code)) {
          byCode.set(language.code, {
            code: language.code,
            name: language.name,
            family: language.family ?? undefined,
            script: language.script ?? undefined,
          });
        }
      }
    }
    return Array.from(byCode.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [catalog, status]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return allLanguages;
    return allLanguages.filter(
      (language) =>
        language.code.toLowerCase().includes(query)
        || language.name.toLowerCase().includes(query)
        || (language.family ?? "").toLowerCase().includes(query),
    );
  }, [allLanguages, search]);

  const refreshAuthStatus = useCallback(async () => {
    const next = await getAuthStatus();
    setProviderStatuses((prev) => buildProviderStatuses(next, Object.keys(prev).length > 0 ? Object.keys(prev) : providers.map((provider) => provider.id)));
    return next;
  }, [providers]);

  useEffect(() => {
    if (!open) return;
    setTab(initialTab);
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getClefConfig(), getClefCatalog(), getClefProviders(), getAuthStatus().catch(() => null)])
      .then(([cfg, cat, prov, authStatus]) => {
        if (cancelled) return;
        const normalizedProviders = normalizeClefProviders(prov.providers);
        setStatus(cfg);
        setCatalog(cat.languages);
        setProviders(normalizedProviders);
        setProviderStatuses(buildProviderStatuses(authStatus, normalizedProviders.map((provider) => provider.id)));
        setPrimary(cfg.primary_contact_languages.slice(0, MAX_PRIMARY));
        const secondarySet = new Set<string>(
          cfg.languages.map((language) => language.code).filter((code) => !cfg.primary_contact_languages.includes(code)),
        );
        setSecondary(secondarySet);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load CLEF config");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [initialTab, open]);

  const togglePrimary = useCallback((code: string) => {
    setPrimary((prev) => {
      if (prev.includes(code)) return prev.filter((entry) => entry !== code);
      if (prev.length >= MAX_PRIMARY) return prev;
      return [...prev, code];
    });
    setSecondary((prev) => {
      const next = new Set(prev);
      next.delete(code);
      return next;
    });
  }, []);

  const toggleSecondary = useCallback((code: string) => {
    setPrimary((prev) => prev.filter((entry) => entry !== code));
    setSecondary((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }, []);

  const addCustom = useCallback(() => {
    const code = customCode.trim().toLowerCase();
    const name = customName.trim() || code;
    if (!code || code.startsWith("_")) return;
    setCatalog((prev) => (prev.some((entry) => entry.code === code) ? prev : [...prev, { code, name }]));
    setSecondary((prev) => new Set(prev).add(code));
    setCustomCode("");
    setCustomName("");
  }, [customCode, customName]);

  const buildPayload = useCallback(() => {
    const byCode = new Map<string, ClefCatalogEntry>();
    for (const entry of allLanguages) byCode.set(entry.code, entry);
    const codes = new Set<string>([...primary, ...secondary]);
    const languages = Array.from(codes).map((code) => {
      const entry = byCode.get(code);
      return {
        code,
        name: entry?.name || code,
        ...(entry?.family ? { family: entry.family } : {}),
        ...(entry?.script ? { script: entry.script } : {}),
      };
    });
    return { primary_contact_languages: primary, languages };
  }, [allLanguages, primary, secondary]);

  const applyDefaults = useCallback(() => {
    const preferred: Array<[string, string]> = [["eng", "English"], ["spa", "Spanish"]];
    setPrimary(preferred.map(([code]) => code));
    setSecondary((prev) => {
      const next = new Set(prev);
      for (const [code] of preferred) next.delete(code);
      return next;
    });
    setCatalog((prev) => {
      const have = new Set(prev.map((entry) => entry.code));
      const additions = preferred
        .filter(([code]) => !have.has(code))
        .map(([code, name]) => ({ code, name }));
      return additions.length ? [...prev, ...additions] : prev;
    });
    setError(null);
  }, []);

  useEffect(() => {
    if (highlightIdx >= filtered.length) setHighlightIdx(0);
  }, [filtered.length, highlightIdx]);

  return {
    allLanguages,
    applyDefaults,
    buildPayload,
    catalog,
    customCode,
    customName,
    error,
    filtered,
    highlightIdx,
    loading,
    primary,
    providers,
    providerStatuses,
    refreshAuthStatus,
    search,
    secondary,
    setCustomCode,
    setCustomName,
    setError,
    setHighlightIdx,
    setSearch,
    setTab,
    status,
    tab,
    togglePrimary,
    toggleSecondary,
    addCustom,
  };
}
