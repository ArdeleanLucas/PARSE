import { useCallback, useEffect, useMemo, useState } from "react";
import { X, Search, Info, Check, AlertCircle, Play, Loader2 } from "lucide-react";
import {
  getClefCatalog,
  getClefConfig,
  getClefProviders,
  saveClefConfig,
  startContactLexemeFetch,
} from "../../api/client";
import type { ClefCatalogEntry, ClefConfigStatus, ClefProviderEntry } from "../../api/types";

export type ClefConfigModalTab = "languages" | "populate";

interface ClefConfigModalProps {
  open: boolean;
  onClose: () => void;
  /** Fired after the config is persisted. The parent uses this to refresh
   *  its cached CLEF status so the Reference Forms panel re-renders with
   *  the new primary languages. */
  onSaved?: (primary: string[]) => void;
  /** Fired when the user picks "Save & populate" and the backend has
   *  accepted the compute job. The parent should hand the jobId to its
   *  header-tracked action-job hook via `.adopt(jobId)` so the running
   *  process appears in the global header exactly like STT / IPA / the
   *  batch pipeline. The modal closes immediately after this fires; it
   *  does not poll the job itself. */
  onPopulateStarted?: (jobId: string) => void;
  /** Tab to show when the modal opens. Defaults to "languages". The
   *  "Retry with different providers" affordance on the empty-populate
   *  banner sets this to "populate" so the user lands directly on the
   *  provider checkboxes. Re-seeded on every open so a later plain-Run
   *  click still lands on the languages tab. */
  initialTab?: ClefConfigModalTab;
}

type Tab = ClefConfigModalTab;

const MAX_PRIMARY = 2;

export function ClefConfigModal({ open, onClose, onSaved, onPopulateStarted, initialTab = "languages" }: ClefConfigModalProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [catalog, setCatalog] = useState<ClefCatalogEntry[]>([]);
  const [providers, setProviders] = useState<ClefProviderEntry[]>([]);
  const [status, setStatus] = useState<ClefConfigStatus | null>(null);

  const [primary, setPrimary] = useState<string[]>([]);
  const [secondary, setSecondary] = useState<Set<string>>(new Set());
  const [customCode, setCustomCode] = useState("");
  const [customName, setCustomName] = useState("");
  const [search, setSearch] = useState("");

  const [tab, setTab] = useState<Tab>(initialTab);
  const [selectedProviders, setSelectedProviders] = useState<Set<string>>(new Set());
  const [overwrite, setOverwrite] = useState(false);

  // The modal no longer polls the populate job locally — the global
  // header takes over once onPopulateStarted fires. The shared `saving`
  // flag (declared above) covers the entire save→startJob→close window,
  // so no separate "populating" state is needed.
  /** Set when populate fails so the UI can switch the primary button from
   *  "Save & populate" to "Retry populate" without throwing away the
   *  user's language picks. Cleared on successful populate or when they
   *  plain-save without populate. */
  const [populateFailed, setPopulateFailed] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);

  const allLanguages = useMemo(() => {
    const byCode = new Map<string, ClefCatalogEntry>();
    for (const c of catalog) byCode.set(c.code, c);
    if (status) {
      for (const l of status.languages) {
        if (!byCode.has(l.code)) {
          byCode.set(l.code, {
            code: l.code,
            name: l.name,
            family: l.family ?? undefined,
            script: l.script ?? undefined,
          });
        }
      }
    }
    return Array.from(byCode.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [catalog, status]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return allLanguages;
    return allLanguages.filter(
      (l) =>
        l.code.toLowerCase().includes(q) ||
        l.name.toLowerCase().includes(q) ||
        (l.family ?? "").toLowerCase().includes(q),
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
          cfg.languages.map((l) => l.code).filter((c) => !cfg.primary_contact_languages.includes(c)),
        );
        setSecondary(secondarySet);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load CLEF config");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const togglePrimary = useCallback((code: string) => {
    setPrimary((prev) => {
      if (prev.includes(code)) return prev.filter((c) => c !== code);
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
    setPrimary((prev) => prev.filter((c) => c !== code));
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
    setCatalog((prev) => (prev.some((c) => c.code === code) ? prev : [...prev, { code, name }]));
    setSecondary((prev) => new Set(prev).add(code));
    setCustomCode("");
    setCustomName("");
  }, [customCode, customName]);

  const buildPayload = useCallback(() => {
    const byCode = new Map<string, ClefCatalogEntry>();
    for (const c of allLanguages) byCode.set(c.code, c);

    const codes = new Set<string>([...primary, ...secondary]);
    const languages = Array.from(codes).map((code) => {
      const entry = byCode.get(code);
      return {
        code,
        name: entry?.name || code,
        ...(entry?.family ? { family: entry.family } : {}),
        // ISO 15924 script hint (Arab, Latn, ...) gets persisted into
        // sil_contact_languages.json so the Reference Forms panel can
        // route bare strings deterministically instead of guessing.
        ...(entry?.script ? { script: entry.script } : {}),
      };
    });
    return { primary_contact_languages: primary, languages };
  }, [allLanguages, primary, secondary]);

  const handleSave = useCallback(
    async (runPopulate: boolean) => {
      if (primary.length === 0) {
        setError("Pick at least one primary contact language.");
        return;
      }
      setSaving(true);
      setError(null);
      setPopulateFailed(false);
      try {
        await saveClefConfig(buildPayload());
        onSaved?.(primary);
        if (!runPopulate) {
          onClose();
          return;
        }
        // Kick off the fetcher for the selected primary languages and
        // hand the jobId up to the parent -- the global header takes
        // over progress display from here, matching the UX of other
        // long-running jobs (STT, forced-align, full pipeline).
        const job = await startContactLexemeFetch({
          languages: primary,
          providers: selectedProviders.size > 0 ? Array.from(selectedProviders) : undefined,
          overwrite,
        });
        const id = job.jobId || job.job_id || "";
        if (!id) throw new Error("No job id returned");
        onPopulateStarted?.(id);
        onClose();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Save failed");
        if (runPopulate) setPopulateFailed(true);
      } finally {
        setSaving(false);
      }
    },
    [primary, buildPayload, selectedProviders, overwrite, onSaved, onPopulateStarted, onClose],
  );

  const applyDefaults = useCallback(() => {
    // Best-guess starter pair for first-time users. Prefers the 3-letter
    // ISO codes so the selection maps cleanly to the bundled catalog; if
    // the bundled catalog only has 2-letter fallbacks the backend still
    // accepts them.
    const preferred: Array<[string, string]> = [["eng", "English"], ["spa", "Spanish"]];
    setPrimary(preferred.map(([c]) => c));
    setSecondary((prev) => {
      const next = new Set(prev);
      for (const [c] of preferred) next.delete(c);
      return next;
    });
    // Make sure the catalog has these entries even if the backend call
    // hasn't returned (offline / 500) -- otherwise save would still work
    // but the chip list would show only the bare code.
    setCatalog((prev) => {
      const have = new Set(prev.map((c) => c.code));
      const additions = preferred
        .filter(([c]) => !have.has(c))
        .map(([code, name]) => ({ code, name }));
      return additions.length ? [...prev, ...additions] : prev;
    });
    setError(null);
  }, []);

  // Global keyboard shortcuts: Escape closes (unless mid-populate), and
  // the search list responds to arrow keys / Enter when the search box or
  // a list row has focus. Arrow keys on the search input move the
  // highlighted row; Enter toggles it as primary (falls back to secondary
  // when the primary slots are full).
  useEffect(() => {
    if (!open) return;
    function handle(e: KeyboardEvent) {
      if (saving) return;
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [open, saving, onClose]);

  // Reset highlight when the filtered list changes size so we never land
  // on a stale out-of-range index.
  useEffect(() => {
    if (highlightIdx >= filtered.length) setHighlightIdx(0);
  }, [filtered.length, highlightIdx]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={saving ? undefined : onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Borrowing detection (CLEF) — configure</h2>
            <p className="mt-1 text-[11px] text-slate-500">
              Pick the contact languages PARSE should compare your speakers against. One or two primary
              languages usually gives the cleanest borrowing signal — adding more dilutes it.
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Status banner */}
        {!loading && status && !status.concepts_csv_exists && (
          <div className="flex items-start gap-2 border-b border-amber-100 bg-amber-50 px-5 py-2 text-[11px] text-amber-800">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>
              No <code className="rounded bg-amber-100 px-1">concepts.csv</code> found in this workspace.
              You can still configure CLEF, but running Borrowing detection will fail until concepts are
              imported.
            </span>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 border-b border-slate-100 px-5 pt-2">
          {(["languages", "populate"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={
                "rounded-t-md px-3 py-1.5 text-[11px] font-semibold " +
                (tab === t
                  ? "bg-white text-indigo-700 border border-slate-200 border-b-white -mb-px"
                  : "text-slate-500 hover:text-slate-700")
              }
            >
              {t === "languages" ? "1. Languages" : "2. Auto-populate (optional)"}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-5 py-4">
          {loading && <div className="text-[12px] text-slate-500">Loading…</div>}
          {error && (
            <div className="mb-3 flex items-start gap-2 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <div className="flex-1">
                <div className="font-semibold">
                  {populateFailed ? "Populate failed — your selections were kept" : "Error"}
                </div>
                <div className="mt-0.5 break-words">{error}</div>
                {populateFailed && (
                  <div className="mt-1 text-rose-500">
                    Config was saved. Click <b>Retry populate</b> below, or close and run the fetcher
                    later from the Contact Lexemes panel.
                  </div>
                )}
              </div>
            </div>
          )}

          {!loading && tab === "languages" && (
            <div className="space-y-4">
              {/* Primary section */}
              <section>
                <div className="mb-1 flex items-center gap-1.5">
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                    Primary contact languages
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    ({primary.length}/{MAX_PRIMARY})
                  </span>
                  <span
                    title="Primary contact languages are the main languages CLEF weighs when deciding cognate vs. borrowing. Pick the languages your speech community has the most historical contact with."
                    className="text-slate-300"
                  >
                    <Info className="h-3 w-3" />
                  </span>
                </div>
                <div className="flex min-h-[34px] flex-wrap gap-1.5 rounded-md border border-slate-200 bg-slate-50 p-2">
                  {primary.length === 0 && (
                    <span className="text-[11px] italic text-slate-400">
                      None selected — click a language below to add it as primary.
                    </span>
                  )}
                  {primary.map((code) => {
                    const entry = allLanguages.find((l) => l.code === code);
                    return (
                      <button
                        key={code}
                        onClick={() => togglePrimary(code)}
                        className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-2.5 py-0.5 text-[11px] font-medium text-white hover:bg-indigo-700"
                      >
                        <Check className="h-3 w-3" /> {entry?.name || code}
                        <span className="ml-0.5 text-indigo-200">({code})</span>
                        <X className="h-3 w-3 opacity-80" />
                      </button>
                    );
                  })}
                </div>
              </section>

              {/* Search + language list */}
              <section>
                <div className="relative mb-2">
                  <Search className="absolute left-2 top-1.5 h-3.5 w-3.5 text-slate-400" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => { setSearch(e.target.value); setHighlightIdx(0); }}
                    onKeyDown={(e) => {
                      if (filtered.length === 0) return;
                      if (e.key === "ArrowDown") {
                        e.preventDefault();
                        setHighlightIdx((i) => (i + 1) % filtered.length);
                      } else if (e.key === "ArrowUp") {
                        e.preventDefault();
                        setHighlightIdx((i) => (i - 1 + filtered.length) % filtered.length);
                      } else if (e.key === "Enter") {
                        e.preventDefault();
                        const l = filtered[highlightIdx];
                        if (!l) return;
                        // Enter prefers primary when a slot is available,
                        // otherwise drops into the secondary set -- this
                        // mirrors the two buttons on the row without
                        // forcing the user onto Tab.
                        if (primary.includes(l.code) || primary.length < MAX_PRIMARY) {
                          togglePrimary(l.code);
                        } else {
                          toggleSecondary(l.code);
                        }
                      }
                    }}
                    placeholder="Search by code, name, or family… (↑/↓ to navigate, Enter to select)"
                    aria-label="Search contact languages"
                    aria-controls="clef-language-list"
                    aria-activedescendant={filtered[highlightIdx] ? `clef-lang-${filtered[highlightIdx].code}` : undefined}
                    className="w-full rounded-md border border-slate-200 bg-white py-1.5 pl-7 pr-2 text-[12px] focus:border-indigo-300 focus:outline-none"
                  />
                </div>
                <div id="clef-language-list" role="listbox" className="max-h-64 overflow-auto rounded-md border border-slate-200">
                  {filtered.map((l, idx) => {
                    const isPrimary = primary.includes(l.code);
                    const isSecondary = secondary.has(l.code);
                    const highlighted = idx === highlightIdx;
                    return (
                      <div
                        key={l.code}
                        id={`clef-lang-${l.code}`}
                        role="option"
                        aria-selected={isPrimary || isSecondary}
                        className={
                          "flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-1.5 text-[12px] last:border-b-0 " +
                          (highlighted ? "bg-indigo-50" : "")
                        }
                      >
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium text-slate-800">{l.name}</div>
                          <div className="text-[10px] text-slate-400">
                            {l.code}
                            {l.family ? ` · ${l.family}` : ""}
                          </div>
                        </div>
                        <div className="flex shrink-0 gap-1">
                          <button
                            onClick={() => togglePrimary(l.code)}
                            disabled={!isPrimary && primary.length >= MAX_PRIMARY}
                            className={
                              "rounded px-2 py-0.5 text-[10px] font-semibold " +
                              (isPrimary
                                ? "bg-indigo-600 text-white"
                                : "border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40")
                            }
                            title={
                              !isPrimary && primary.length >= MAX_PRIMARY
                                ? `At most ${MAX_PRIMARY} primary languages`
                                : ""
                            }
                          >
                            Primary
                          </button>
                          <button
                            onClick={() => toggleSecondary(l.code)}
                            className={
                              "rounded px-2 py-0.5 text-[10px] font-semibold " +
                              (isSecondary
                                ? "bg-slate-700 text-white"
                                : "border border-slate-200 text-slate-600 hover:bg-slate-50")
                            }
                          >
                            {isSecondary ? "Included" : "Include"}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                  {filtered.length === 0 && (
                    <div className="px-3 py-6 text-center text-[11px] text-slate-400">
                      No matches. Use the box below to add a custom SIL/ISO code.
                    </div>
                  )}
                </div>
              </section>

              {/* Custom code */}
              <section>
                <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Add custom SIL/ISO code
                </h3>
                <div className="flex gap-1.5">
                  <input
                    type="text"
                    value={customCode}
                    onChange={(e) => setCustomCode(e.target.value)}
                    placeholder="code"
                    className="w-24 rounded-md border border-slate-200 px-2 py-1.5 text-[12px] focus:border-indigo-300 focus:outline-none"
                  />
                  <input
                    type="text"
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    placeholder="display name (optional)"
                    className="flex-1 rounded-md border border-slate-200 px-2 py-1.5 text-[12px] focus:border-indigo-300 focus:outline-none"
                  />
                  <button
                    onClick={addCustom}
                    disabled={!customCode.trim()}
                    className="rounded-md border border-slate-200 bg-white px-3 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Add
                  </button>
                </div>
              </section>
            </div>
          )}

          {!loading && tab === "populate" && (
            <div className="space-y-4">
              <p className="text-[12px] text-slate-600">
                Optional — fill the chosen primary languages with lexeme forms from the providers below.
                You can always run this later from the Contact Lexemes panel.
              </p>

              <section>
                <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Providers (leave empty for all, in priority order)
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {providers.map((p) => {
                    const active = selectedProviders.has(p.id);
                    return (
                      <button
                        key={p.id}
                        onClick={() =>
                          setSelectedProviders((prev) => {
                            const next = new Set(prev);
                            if (next.has(p.id)) next.delete(p.id);
                            else next.add(p.id);
                            return next;
                          })
                        }
                        className={
                          "rounded border px-2 py-0.5 text-[11px] " +
                          (active
                            ? "border-indigo-600 bg-indigo-600 text-white"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50")
                        }
                      >
                        {p.name}
                      </button>
                    );
                  })}
                </div>
              </section>

              <label className="flex items-center gap-2 text-[12px] text-slate-700">
                <input
                  type="checkbox"
                  checked={overwrite}
                  onChange={(e) => setOverwrite(e.target.checked)}
                />
                Overwrite existing forms
              </label>

              {saving && (
                <div className="flex items-center gap-2 rounded border border-indigo-200 bg-indigo-50 p-3 text-[11px] font-semibold text-indigo-800">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Dispatching job… live progress will appear in the app header.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
          <span className="mr-auto text-[10px] text-slate-400">
            {primary.length} primary · {secondary.size} secondary
          </span>
          <button
            onClick={applyDefaults}
            disabled={saving}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            title="Preselect a sensible starter pair (English + Spanish). You can still edit before saving."
          >
            Use defaults
          </button>
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            title="Close without configuring. The Run button will reopen this modal next time."
          >
            Configure later
          </button>
          <button
            onClick={() => handleSave(false)}
            disabled={saving || primary.length === 0}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
          >
            Save
          </button>
          <button
            onClick={() => handleSave(true)}
            disabled={saving || primary.length === 0}
            className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-40"
          >
            <Play className="h-3 w-3" /> {populateFailed ? "Retry populate" : "Save & populate"}
          </button>
        </div>
      </div>
    </div>
  );
}
