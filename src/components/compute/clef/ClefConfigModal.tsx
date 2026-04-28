import { AlertCircle, Play, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { AuthStatus } from "../../../api/types";
import { saveClefConfig } from "../../../api/client";
import { ConfigForm } from "./ConfigForm";
import { ProviderSelector } from "./ProviderSelector";
import { useClefConfig } from "./useClefConfig";
import { useClefFetchJob } from "./useClefFetchJob";
import type { ClefConfigModalProps, ClefConfigModalTab } from "./types";

export function ClefConfigModal({
  open,
  onClose,
  onSaved,
  onPopulateStarted,
  initialTab = "languages",
}: ClefConfigModalProps) {
  const [saving, setSaving] = useState(false);
  const [authExpandedProviderId, setAuthExpandedProviderId] = useState<string | null>(null);
  const {
    addCustom,
    allLanguages,
    applyDefaults,
    buildPayload,
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
  } = useClefConfig(open, initialTab);
  const {
    overwrite,
    populateFailed,
    selectedProviders,
    selectProvider,
    setOverwrite,
    setPopulateFailed,
    startPopulate,
    toggleProvider,
  } = useClefFetchJob(providers.map((provider) => provider.id));

  const selectedProviderCount = selectedProviders.size;
  const selectedReadyCount = useMemo(() => {
    let count = 0;
    for (const providerId of selectedProviders) {
      const kind = providerStatuses[providerId] ?? "ready";
      if (kind === "ready" || kind === "connected") count += 1;
    }
    return count;
  }, [providerStatuses, selectedProviders]);
  const grokipediaSelectedButUnauthed = selectedProviders.has("grokipedia") && (providerStatuses.grokipedia ?? "needs_auth") === "needs_auth";
  const canStart = !saving && selectedProviderCount > 0;

  const saveOnly = useCallback(async () => {
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
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [buildPayload, onClose, onSaved, primary, setError, setPopulateFailed]);

  const handleStart = useCallback(async () => {
    if (primary.length === 0) {
      setError("Pick at least one primary contact language.");
      setTab("languages");
      return;
    }
    if (selectedProviderCount === 0) {
      setError("Select at least one source before starting CLEF.");
      return;
    }
    if (grokipediaSelectedButUnauthed) {
      setError("Grokipedia is selected but no API key is configured. Connect a key or uncheck Grokipedia.");
      setTab("populate");
      setAuthExpandedProviderId("grokipedia");
      return;
    }
    setSaving(true);
    setError(null);
    setPopulateFailed(false);
    try {
      await saveClefConfig(buildPayload());
      onSaved?.(primary);
      const jobId = await startPopulate(primary);
      onPopulateStarted?.(jobId);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Start failed");
      setPopulateFailed(true);
    } finally {
      setSaving(false);
    }
  }, [buildPayload, grokipediaSelectedButUnauthed, onClose, onPopulateStarted, onSaved, primary, selectedProviderCount, setError, setPopulateFailed, setTab, startPopulate]);

  async function handleProviderAuthSaved(providerId: string, _status: AuthStatus) {
    await refreshAuthStatus();
    selectProvider(providerId);
    setAuthExpandedProviderId(null);
    setError(null);
  }

  useEffect(() => {
    if (!open) return;
    if (initialTab === "populate") {
      setTab("populate");
    }
  }, [initialTab, open, setTab]);

  useEffect(() => {
    if (!open) return;
    function handle(event: KeyboardEvent) {
      if (saving) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [onClose, open, saving]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onClick={saving ? undefined : onClose}>
      <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <ClefConfigHeader onClose={onClose} saving={saving} />
        {!loading && status && !status.concepts_csv_exists && <MissingConceptsBanner />}
        <SectionStrip tab={tab} onSelect={setTab} />
        <div className="flex-1 overflow-auto px-6 py-5">
          {loading && <div className="text-[12px] text-slate-500">Loading…</div>}
          {error && <ClefErrorBanner error={error} populateFailed={populateFailed} />}
          {!loading && tab === "languages" && (
            <div className="space-y-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-600">Languages</div>
                  <p className="mt-1 text-[12px] text-slate-600">
                    Pick the primary contact languages PARSE should compare your speakers against.
                  </p>
                </div>
                <ConfigForm
                  addCustom={addCustom}
                  allLanguages={allLanguages}
                  customCode={customCode}
                  customName={customName}
                  filtered={filtered}
                  highlightIdx={highlightIdx}
                  primary={primary}
                  search={search}
                  secondary={secondary}
                  setCustomCode={setCustomCode}
                  setCustomName={setCustomName}
                  setHighlightIdx={setHighlightIdx}
                  setSearch={setSearch}
                  togglePrimary={togglePrimary}
                  toggleSecondary={toggleSecondary}
                />
            </div>
          )}
          {!loading && tab === "populate" && (
            <ProviderSelector
              mode="detailed"
              authExpandedProviderId={authExpandedProviderId}
              onAuthSaved={(providerId, status) => void handleProviderAuthSaved(providerId, status)}
              onExpandAuth={setAuthExpandedProviderId}
              overwrite={overwrite}
              providerStatuses={providerStatuses}
              providers={providers}
              saving={saving}
              selectedProviders={selectedProviders}
              setOverwrite={setOverwrite}
              toggleProvider={toggleProvider}
            />
          )}
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50/60 px-6 py-4">
          <div className="text-[11px] text-slate-500">
            {selectedReadyCount} of {providers.length || 10} sources will run.
            {grokipediaSelectedButUnauthed && (
              <span className="ml-2 inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-semibold text-amber-700 ring-1 ring-amber-200">
                <AlertCircle className="h-3 w-3" /> Grokipedia needs a key
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={applyDefaults} disabled={saving} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Use defaults</button>
            <button onClick={saveOnly} disabled={saving || primary.length === 0} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Save only</button>
            <button onClick={onClose} disabled={saving} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Cancel</button>
            <button onClick={() => void handleStart()} disabled={!canStart} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300">
              <Play className="h-3 w-3" /> {populateFailed ? "Retry search" : "Start search"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

function ClefConfigHeader({ onClose, saving }: { onClose: () => void; saving: boolean }) {
  return (
    <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">Borrowing detection (CLEF) — configure sources</h2>
        <p className="mt-1 text-[11px] text-slate-500">
          Configure the contact languages and lexical sources once, then launch the CLEF search from this single surface.
        </p>
      </div>
      <button onClick={onClose} disabled={saving} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30" aria-label="Close">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

function MissingConceptsBanner() {
  return (
    <div className="border-b border-amber-100 bg-amber-50 px-6 py-3 text-[11px] text-amber-800">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          No <code className="rounded bg-amber-100 px-1">concepts.csv</code> found in this workspace.
          You can still configure CLEF, but running Borrowing detection will fail until concepts are imported.
        </span>
      </div>
    </div>
  );
}

function SectionStrip({ tab, onSelect }: { tab: ClefConfigModalTab; onSelect: (tab: ClefConfigModalTab) => void }) {
  return (
    <div className="flex gap-1 border-b border-slate-200 px-6 pt-2">
      {(["languages", "populate"] as ClefConfigModalTab[]).map((entry) => (
        <button
          key={entry}
          onClick={() => onSelect(entry)}
          className={
            "rounded-t-md px-3 py-1.5 text-[11px] font-semibold "
            + (tab === entry
              ? "border border-slate-200 border-b-white -mb-px bg-white text-slate-900"
              : "text-slate-500 hover:text-slate-700")
          }
        >
          {entry === "languages" ? "1. Languages" : "2. Sources"}
        </button>
      ))}
    </div>
  );
}

function ClefErrorBanner({ error, populateFailed }: { error: string; populateFailed: boolean }) {
  return (
    <div className="mb-3 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="flex-1">
        <div className="font-semibold">{populateFailed ? "Start failed — your selections were kept" : "Error"}</div>
        <div className="mt-0.5 break-words">{error}</div>
      </div>
    </div>
  );
}
