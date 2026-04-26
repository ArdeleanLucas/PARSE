import { AlertCircle, Play, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
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
    setOverwrite,
    setPopulateFailed,
    startPopulate,
    toggleProvider,
  } = useClefFetchJob();

  const handleSave = useCallback(async (runPopulate: boolean) => {
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
      const jobId = await startPopulate(primary);
      onPopulateStarted?.(jobId);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
      if (runPopulate) setPopulateFailed(true);
    } finally {
      setSaving(false);
    }
  }, [buildPayload, onClose, onPopulateStarted, onSaved, primary, setError, setPopulateFailed, startPopulate]);

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
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <ClefConfigHeader onClose={onClose} saving={saving} />
        {!loading && status && !status.concepts_csv_exists && <MissingConceptsBanner />}
        <TabStrip tab={tab} setTab={setTab} />
        <div className="flex-1 overflow-auto px-5 py-4">
          {loading && <div className="text-[12px] text-slate-500">Loading…</div>}
          {error && <ClefErrorBanner error={error} populateFailed={populateFailed} />}
          {!loading && tab === "languages" && (
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
          )}
          {!loading && tab === "populate" && (
            <ProviderSelector
              overwrite={overwrite}
              providers={providers}
              saving={saving}
              selectedProviders={selectedProviders}
              setOverwrite={setOverwrite}
              toggleProvider={toggleProvider}
            />
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
          <span className="mr-auto text-[10px] text-slate-400">{primary.length} primary · {secondary.size} secondary</span>
          <button onClick={applyDefaults} disabled={saving} className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40" title="Preselect a sensible starter pair (English + Spanish). You can still edit before saving.">Use defaults</button>
          <button onClick={onClose} disabled={saving} className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40" title="Close without configuring. The Run button will reopen this modal next time.">Configure later</button>
          <button onClick={() => void handleSave(false)} disabled={saving || primary.length === 0} className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40">Save</button>
          <button onClick={() => void handleSave(true)} disabled={saving || primary.length === 0} className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-40"><Play className="h-3 w-3" /> {populateFailed ? "Retry populate" : "Save & populate"}</button>
        </div>
      </div>
    </div>
  );
}

function ClefConfigHeader({ onClose, saving }: { onClose: () => void; saving: boolean }) {
  return (
    <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">Borrowing detection (CLEF) — configure</h2>
        <p className="mt-1 text-[11px] text-slate-500">
          Pick the contact languages PARSE should compare your speakers against. One or two primary
          languages usually gives the cleanest borrowing signal — adding more dilutes it.
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
    <div className="flex items-start gap-2 border-b border-amber-100 bg-amber-50 px-5 py-2 text-[11px] text-amber-800">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>
        No <code className="rounded bg-amber-100 px-1">concepts.csv</code> found in this workspace.
        You can still configure CLEF, but running Borrowing detection will fail until concepts are
        imported.
      </span>
    </div>
  );
}

function TabStrip({ tab, setTab }: { tab: ClefConfigModalTab; setTab: (tab: ClefConfigModalTab) => void }) {
  return (
    <div className="flex gap-1 border-b border-slate-100 px-5 pt-2">
      {(["languages", "populate"] as ClefConfigModalTab[]).map((entry) => (
        <button
          key={entry}
          onClick={() => setTab(entry)}
          className={
            "rounded-t-md px-3 py-1.5 text-[11px] font-semibold "
            + (tab === entry
              ? "bg-white text-indigo-700 border border-slate-200 border-b-white -mb-px"
              : "text-slate-500 hover:text-slate-700")
          }
        >
          {entry === "languages" ? "1. Languages" : "2. Auto-populate (optional)"}
        </button>
      ))}
    </div>
  );
}

function ClefErrorBanner({ error, populateFailed }: { error: string; populateFailed: boolean }) {
  return (
    <div className="mb-3 flex items-start gap-2 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="flex-1">
        <div className="font-semibold">{populateFailed ? "Populate failed — your selections were kept" : "Error"}</div>
        <div className="mt-0.5 break-words">{error}</div>
        {populateFailed && (
          <div className="mt-1 text-rose-500">
            Config was saved. Click <b>Retry populate</b> below, or close and run the fetcher later from the Contact Lexemes panel.
          </div>
        )}
      </div>
    </div>
  );
}
