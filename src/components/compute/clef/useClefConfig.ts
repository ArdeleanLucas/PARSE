import { useCallback, useEffect, useMemo, useState } from "react";
import { getClefCatalog, getClefConfig, getClefProviders } from "../../../api/client";
import type { ClefCatalogEntry } from "../../../api/types";
import { MAX_PRIMARY, type ClefConfigModalTab, type UseClefConfigResult } from "./types";

export function useClefConfig(open: boolean, initialTab: ClefConfigModalTab): UseClefConfigResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<ClefCatalogEntry[]>([]);
  const [providers, setProviders] = useState<UseClefConfigResult["providers"]>([]);
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

  useEffect(() => {
    if (!open) return;
    setTab(initialTab);
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getClefConfig(), getClefCatalog(), getClefProviders()])
      .then(([cfg, cat, prov]) => {
        if (cancelled) return;
        setStatus(cfg);
        setCatalog(cat.languages);
        setProviders(prov.providers);
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
