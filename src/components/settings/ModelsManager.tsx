import { useEffect, useRef, useState } from "react";
import { Modal } from "../shared/Modal";
import { useModelStore } from "../../stores/modelStore";
import type { ModelFormat, ModelRecord, ModelStage } from "../../api/client";

export interface ModelsManagerProps {
  open: boolean;
  onClose: () => void;
}

const STAGES: { id: ModelStage; label: string }[] = [
  { id: "stt", label: "STT" },
  { id: "ipa", label: "IPA" },
  { id: "ortho", label: "ORTH" },
];

const FORMATS: { id: ModelFormat; label: string }[] = [
  { id: "faster-whisper-ct2", label: "faster-whisper (CTranslate2)" },
  { id: "hf-transformers", label: "HuggingFace Transformers" },
];

/** Standard Southern Kurdish STT model shipped as the first-run default. */
const DEFAULT_STT_HF_REPO = "razhan/whisper-base-sdh";

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = value >= 100 || unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
}

function SourceBadge({ record }: { record: ModelRecord }) {
  const isBundled = record.root === "bundled";
  const label = isBundled ? "Bundled" : record.source.type === "hf" ? "HuggingFace" : "User";
  const classes = isBundled
    ? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
    : "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300";
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold ${classes}`}>
      {label}
    </span>
  );
}

export function ModelsManager({ open, onClose }: ModelsManagerProps) {
  const models = useModelStore((s) => s.models);
  const binding = useModelStore((s) => s.binding);
  const loading = useModelStore((s) => s.loading);
  const error = useModelStore((s) => s.error);
  const install = useModelStore((s) => s.install);
  const refresh = useModelStore((s) => s.refresh);
  const installPack = useModelStore((s) => s.installPack);
  const installFromHf = useModelStore((s) => s.installFromHf);
  const remove = useModelStore((s) => s.remove);
  const setBinding = useModelStore((s) => s.setBinding);
  const resetInstall = useModelStore((s) => s.resetInstall);

  // Pure UI state only — the model data itself lives in the store.
  const [addMode, setAddMode] = useState<"pack" | "hf">("pack");
  const [hfRepoId, setHfRepoId] = useState("");
  const [hfStage, setHfStage] = useState<ModelStage>("stt");
  const [hfFormat, setHfFormat] = useState<ModelFormat>("faster-whisper-ct2");
  const [hfName, setHfName] = useState("");
  const [pendingRemoveId, setPendingRemoveId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) {
      void refresh();
    }
  }, [open, refresh]);

  const installing = install.status === "running";
  const hasStt = models.some((m) => m.stage === "stt");

  function handlePackChosen(file: File | undefined): void {
    if (!file) return;
    void installPack(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleHfInstall(): void {
    const repo = hfRepoId.trim();
    if (!repo) return;
    void installFromHf({
      hfRepoId: repo,
      stage: hfStage,
      format: hfFormat,
      name: hfName.trim() || undefined,
    });
  }

  function handleFirstRunStt(): void {
    setAddMode("hf");
    setHfStage("stt");
    setHfFormat("faster-whisper-ct2");
    setHfRepoId(DEFAULT_STT_HF_REPO);
  }

  const modelsForStage = (stage: ModelStage): ModelRecord[] =>
    models.filter((m) => m.stage === stage);

  return (
    <Modal open={open} onClose={onClose} title="Models">
      <div className="w-[42rem] max-w-full space-y-5 text-sm" data-testid="models-manager">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Install, remove, and assign the speech models used by the annotation
          pipeline. Bundled models ship with PARSE; user models can be added from
          a model pack or a HuggingFace repository.
        </p>

        {error && (
          <div
            data-testid="models-error"
            className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300"
          >
            {error}
          </div>
        )}

        {!hasStt && !loading && (
          <div
            data-testid="models-no-stt-cta"
            className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
          >
            <p className="mb-1 font-semibold">No speech-to-text model installed.</p>
            <p className="mb-2">
              Install the standard STT model to start transcribing audio.
            </p>
            <button
              type="button"
              onClick={handleFirstRunStt}
              className="inline-flex items-center rounded bg-amber-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-amber-700"
            >
              Install standard STT model
            </button>
          </div>
        )}

        {/* Installed models + per-stage assignment */}
        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Installed models
          </h3>
          {loading ? (
            <p className="text-xs text-slate-400">Loading…</p>
          ) : models.length === 0 ? (
            <p className="text-xs text-slate-400" data-testid="models-empty">
              No models installed yet.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
              {models.map((model) => (
                <li
                  key={model.id}
                  data-testid={`model-row-${model.id}`}
                  className="flex items-center gap-3 px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium text-slate-800 dark:text-slate-100">
                        {model.name}
                      </span>
                      <SourceBadge record={model} />
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                      <span className="uppercase">{model.stage}</span>
                      <span aria-hidden>·</span>
                      <span>{formatBytes(model.size_bytes)}</span>
                    </div>
                  </div>
                  {model.removable ? (
                    pendingRemoveId === model.id ? (
                      <span className="flex items-center gap-1.5">
                        <button
                          type="button"
                          data-testid={`model-remove-confirm-${model.id}`}
                          onClick={() => {
                            void remove(model.id);
                            setPendingRemoveId(null);
                          }}
                          className="rounded bg-rose-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-rose-700"
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingRemoveId(null)}
                          className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                        >
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        data-testid={`model-remove-${model.id}`}
                        onClick={() => setPendingRemoveId(model.id)}
                        className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-600 hover:bg-rose-50 hover:text-rose-700 dark:border-slate-700 dark:text-slate-300"
                      >
                        Remove
                      </button>
                    )
                  ) : null}
                </li>
              ))}
            </ul>
          )}

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {STAGES.map((stage) => {
              const options = modelsForStage(stage.id);
              return (
                <label key={stage.id} className="flex flex-col gap-1 text-[11px]">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">
                    {stage.label} model
                  </span>
                  <select
                    data-testid={`model-binding-${stage.id}`}
                    value={binding[stage.id] ?? ""}
                    disabled={options.length === 0}
                    onChange={(e) => {
                      const value = e.target.value;
                      void setBinding(stage.id, value === "" ? null : value);
                    }}
                    className="rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                  >
                    <option value="">Unassigned</option>
                    {options.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </label>
              );
            })}
          </div>
        </section>

        {/* Add a model */}
        <section className="space-y-3 border-t border-slate-100 pt-4 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Add a model
            </h3>
            <div className="ml-auto inline-flex rounded-md border border-slate-200 p-0.5 dark:border-slate-700">
              <button
                type="button"
                data-testid="add-mode-pack"
                onClick={() => setAddMode("pack")}
                className={`rounded px-2 py-0.5 text-[11px] font-semibold ${addMode === "pack" ? "bg-indigo-600 text-white" : "text-slate-600 dark:text-slate-300"}`}
              >
                Upload pack
              </button>
              <button
                type="button"
                data-testid="add-mode-hf"
                onClick={() => setAddMode("hf")}
                className={`rounded px-2 py-0.5 text-[11px] font-semibold ${addMode === "hf" ? "bg-indigo-600 text-white" : "text-slate-600 dark:text-slate-300"}`}
              >
                HuggingFace
              </button>
            </div>
          </div>

          {addMode === "pack" ? (
            <div className="space-y-2">
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Select a model pack (.zip or .parsemodel) to install.
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip,.parsemodel"
                data-testid="model-pack-input"
                disabled={installing}
                onChange={(e) => handlePackChosen(e.target.files?.[0])}
                className="block w-full text-xs text-slate-600 file:mr-3 file:rounded file:border-0 file:bg-indigo-600 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white hover:file:bg-indigo-700 disabled:opacity-50 dark:text-slate-300"
              />
            </div>
          ) : (
            <div className="space-y-2">
              <label className="flex flex-col gap-1 text-[11px]">
                <span className="font-semibold text-slate-600 dark:text-slate-300">
                  HuggingFace repo id
                </span>
                <input
                  type="text"
                  data-testid="hf-repo-input"
                  value={hfRepoId}
                  disabled={installing}
                  onChange={(e) => setHfRepoId(e.target.value)}
                  placeholder="org/model-name"
                  spellCheck={false}
                  className="rounded border border-slate-200 px-2 py-1 font-mono text-xs text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1 text-[11px]">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">Stage</span>
                  <select
                    data-testid="hf-stage-select"
                    value={hfStage}
                    disabled={installing}
                    onChange={(e) => setHfStage(e.target.value as ModelStage)}
                    className="rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                  >
                    {STAGES.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px]">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">Format</span>
                  <select
                    data-testid="hf-format-select"
                    value={hfFormat}
                    disabled={installing}
                    onChange={(e) => setHfFormat(e.target.value as ModelFormat)}
                    className="rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                  >
                    {FORMATS.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="flex flex-col gap-1 text-[11px]">
                <span className="font-semibold text-slate-600 dark:text-slate-300">
                  Display name (optional)
                </span>
                <input
                  type="text"
                  data-testid="hf-name-input"
                  value={hfName}
                  disabled={installing}
                  onChange={(e) => setHfName(e.target.value)}
                  placeholder="Defaults to the repo name"
                  className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                />
              </label>
              <button
                type="button"
                data-testid="hf-install-button"
                onClick={handleHfInstall}
                disabled={installing || hfRepoId.trim() === ""}
                className="inline-flex items-center rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Install from HuggingFace
              </button>
            </div>
          )}

          {install.status !== "idle" && (
            <div data-testid="install-status" className="space-y-1">
              {install.status === "error" ? (
                <div className="flex items-center gap-2 text-xs text-rose-600 dark:text-rose-400">
                  <span data-testid="install-error">Install failed: {install.error}</span>
                  <button
                    type="button"
                    onClick={resetInstall}
                    className="rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                  >
                    Dismiss
                  </button>
                </div>
              ) : install.status === "complete" ? (
                <div className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-400">
                  <span>Install complete.</span>
                  <button
                    type="button"
                    onClick={resetInstall}
                    className="rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                  >
                    Dismiss
                  </button>
                </div>
              ) : (
                <>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400">
                    {install.message ?? "Installing…"}{" "}
                    <span className="tabular-nums">{Math.round(install.progress * 100)}%</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-[width]"
                      style={{ width: `${Math.round(install.progress * 100)}%` }}
                    />
                  </div>
                </>
              )}
            </div>
          )}
        </section>

        <div className="flex justify-end border-t border-slate-100 pt-3 dark:border-slate-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
}
