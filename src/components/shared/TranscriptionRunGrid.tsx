import {
  STEP_ICONS,
  STEP_LABELS,
  cellClasses,
  cellLabel,
  CellIcon,
  computeCell,
  keepTooltip,
  type PipelineStepId,
  type RunScope,
  type SpeakerLoadEntry,
} from "./transcriptionRunShared";

export function TranscriptionRunGrid({
  speakers,
  gridStepColumns,
  selectedSpeakers,
  stateBySpeaker,
  scopeByStep,
  onToggleSpeaker,
  onSetAllSpeakers,
  onSetStepScope,
}: {
  speakers: string[];
  gridStepColumns: PipelineStepId[];
  selectedSpeakers: Set<string>;
  stateBySpeaker: Record<string, SpeakerLoadEntry>;
  scopeByStep: Record<PipelineStepId, RunScope>;
  onToggleSpeaker: (speaker: string) => void;
  onSetAllSpeakers: (next: Set<string>) => void;
  onSetStepScope: (step: PipelineStepId, scope: RunScope) => void;
}) {
  const setAllSpeakers = (mode: "all" | "none" | "runnable") => {
    if (mode === "none") {
      onSetAllSpeakers(new Set());
      return;
    }
    if (mode === "all") {
      onSetAllSpeakers(
        new Set(speakers.filter((s) => stateBySpeaker[s]?.status !== "error")),
      );
      return;
    }
    const next = new Set<string>();
    for (const speaker of speakers) {
      const entry = stateBySpeaker[speaker];
      if (!entry || entry.status !== "ready" || !entry.state) continue;
      const anyRunnable = gridStepColumns.some((step) => entry.state![step].can_run);
      if (anyRunnable) next.add(speaker);
    }
    onSetAllSpeakers(next);
  };

  const collisionSteps = gridStepColumns.filter((step) =>
    Array.from(selectedSpeakers).some((speaker) => {
      const entry = stateBySpeaker[speaker];
      return !!(entry?.status === "ready" && entry.state && entry.state[step].done);
    }),
  );

  return (
    <>
      <div className="flex items-center gap-2 text-[11px] text-slate-600">
        <span className="font-semibold">Speakers:</span>
        <button
          type="button"
          onClick={() => setAllSpeakers("all")}
          className="rounded px-2 py-0.5 hover:bg-slate-100"
          data-testid="transcription-run-select-all"
        >
          Select all
        </button>
        <span className="text-slate-300">·</span>
        <button
          type="button"
          onClick={() => setAllSpeakers("runnable")}
          className="rounded px-2 py-0.5 hover:bg-slate-100"
          data-testid="transcription-run-select-runnable"
        >
          Select visible-runnable
        </button>
        <span className="text-slate-300">·</span>
        <button
          type="button"
          onClick={() => setAllSpeakers("none")}
          className="rounded px-2 py-0.5 hover:bg-slate-100"
          data-testid="transcription-run-select-none"
        >
          None
        </button>
      </div>

      {collisionSteps.length > 0 && (
        <div
          className="flex flex-wrap items-center gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2"
          data-testid="transcription-run-scope-bar"
        >
          <span
            className="text-xs font-semibold text-amber-900"
            title="Some selected speakers already have finalized output for these steps. Choose Keep to preserve existing data, or Overwrite to clobber it."
          >
            Existing data
          </span>
          {collisionSteps.map((step) => {
            const Icon = STEP_ICONS[step];
            const scope = scopeByStep[step];
            return (
              <div
                key={step}
                className="flex items-center gap-1.5 text-xs text-slate-700"
                data-testid={`transcription-run-scope-${step}`}
                data-step-scope={scope}
              >
                <Icon className="h-3.5 w-3.5 text-slate-500" />
                <span className="font-medium">{STEP_LABELS[step]}</span>
                <div
                  role="radiogroup"
                  aria-label={`${STEP_LABELS[step]} scope`}
                  className="ml-0.5 inline-flex overflow-hidden rounded border border-slate-300"
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={scope === "gaps"}
                    onClick={() => onSetStepScope(step, "gaps")}
                    data-testid={`transcription-run-scope-${step}-keep`}
                    className={`px-2 py-0.5 text-[11px] font-medium transition ${
                      scope === "gaps"
                        ? "bg-sky-600 text-white"
                        : "bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    Keep
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={scope === "overwrite"}
                    onClick={() => onSetStepScope(step, "overwrite")}
                    data-testid={`transcription-run-scope-${step}-overwrite`}
                    className={`border-l border-slate-300 px-2 py-0.5 text-[11px] font-medium transition ${
                      scope === "overwrite"
                        ? "bg-amber-600 text-white"
                        : "bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    Overwrite
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div
        className="max-h-[50vh] overflow-auto rounded-md border border-slate-200"
        data-testid="transcription-run-grid"
      >
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 bg-slate-100 text-slate-700">
            <tr>
              <th className="px-3 py-2 text-left font-semibold">Speaker</th>
              {gridStepColumns.map((step) => {
                const Icon = STEP_ICONS[step];
                return (
                  <th
                    key={step}
                    className="px-3 py-2 text-left font-semibold"
                    data-testid={`transcription-run-col-${step}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      <Icon className="h-3.5 w-3.5" />
                      {STEP_LABELS[step]}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {speakers.map((speaker) => {
              const entry = stateBySpeaker[speaker];
              const speakerSelected = selectedSpeakers.has(speaker);
              const loadFailed = entry?.status === "error";
              return (
                <tr
                  key={speaker}
                  className="border-t border-slate-200"
                  data-testid={`transcription-run-row-${speaker}`}
                >
                  <td className="px-3 py-2">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        data-testid={`transcription-run-speaker-${speaker}`}
                        checked={speakerSelected}
                        disabled={loadFailed}
                        onChange={() => onToggleSpeaker(speaker)}
                        className="h-3.5 w-3.5 rounded border-slate-300"
                      />
                      <span
                        className={`font-medium ${loadFailed ? "text-slate-400" : "text-slate-800"}`}
                      >
                        {speaker}
                      </span>
                      {loadFailed && (
                        <span className="text-[11px] text-slate-400">(failed to load state)</span>
                      )}
                    </label>
                  </td>
                  {gridStepColumns.map((step) => {
                    const info = computeCell(step, entry, speakerSelected, scopeByStep[step]);
                    const tooltip = (() => {
                      if (info.kind === "blocked") return info.reason ?? "Blocked by backend";
                      if (info.kind === "skip") {
                        return `Already done (${info.count} items). Tick this row's speaker to choose a scope.`;
                      }
                      if (info.kind === "keep") return keepTooltip(step, info.count);
                      if (info.kind === "overwrite") {
                        return `Will overwrite ${info.count} existing items.`;
                      }
                      if (info.kind === "unknown") return info.reason ?? "State unavailable";
                      return undefined;
                    })();
                    return (
                      <td
                        key={step}
                        className="px-3 py-2"
                        data-testid={`transcription-run-cell-${speaker}-${step}`}
                        data-cell-kind={info.kind}
                        title={tooltip}
                      >
                        <span
                          className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-medium ${cellClasses(
                            info.kind,
                          )}`}
                        >
                          <CellIcon kind={info.kind} />
                          <span>{cellLabel(info.kind)}</span>
                        </span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
