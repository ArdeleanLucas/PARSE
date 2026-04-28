import { ArrowRight, BookOpen, Folder, Loader2, Sparkles } from "lucide-react";
import { ProviderApiKeyForm } from "./ProviderApiKeyForm";
import { PROVIDER_GROUPS, PROVIDER_SUBTITLES, providerLabel } from "./shared";
import type { ProviderSelectorProps, ProviderStatusKind } from "./types";

const STATUS_COPY: Record<ProviderStatusKind, { label: string; tone: "emerald" | "amber" | "slate" | "rose" }> = {
  ready: { label: "Ready", tone: "emerald" },
  connected: { label: "Connected", tone: "emerald" },
  needs_auth: { label: "Needs API key", tone: "amber" },
  no_data: { label: "No data for selected language", tone: "slate" },
  missing_file: { label: "Local file missing", tone: "rose" },
  error: { label: "Errored", tone: "rose" },
};

const GROUP_ICONS = {
  "open-lexical-databases": BookOpen,
  "local-sources": Folder,
  "llm-augmented-search": Sparkles,
} as const;

export function StatusBadge({ kind }: { kind: ProviderStatusKind }) {
  const { label, tone } = STATUS_COPY[kind];
  const classes = {
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    amber: "bg-amber-50 text-amber-700 ring-amber-200",
    slate: "bg-slate-50 text-slate-600 ring-slate-200",
    rose: "bg-rose-50 text-rose-700 ring-rose-200",
  }[tone];
  const dotClass = kind === "ready" || kind === "connected"
    ? "bg-emerald-500"
    : kind === "needs_auth"
      ? "bg-amber-500"
      : kind === "missing_file" || kind === "error"
        ? "bg-rose-500"
        : "bg-slate-400";
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ${classes}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} aria-hidden />
      {label}
    </span>
  );
}

export function ProviderSelector({
  providers,
  selectedProviders,
  toggleProvider,
  overwrite,
  setOverwrite,
  saving,
  mode = "compact",
  providerStatuses = {},
  authExpandedProviderId = null,
  onExpandAuth,
  onAuthSaved,
}: ProviderSelectorProps) {
  if (mode === "compact") {
    return (
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
            {providers.map((provider) => {
              const active = selectedProviders.has(provider.id);
              return (
                <button
                  key={provider.id}
                  onClick={() => toggleProvider(provider.id)}
                  className={
                    "rounded border px-2 py-0.5 text-[11px] "
                    + (active
                      ? "border-indigo-600 bg-indigo-600 text-white"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50")
                  }
                >
                  {provider.name}
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
    );
  }

  const providerById = new Map(providers.map((provider) => [provider.id, provider]));

  return (
    <div className="space-y-4" data-testid="clef-detailed-provider-selector">
      <div className="space-y-1">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-600">Sources</h3>
        <p className="text-[12px] text-slate-600">
          Choose the lexical sources PARSE should query before the CLEF search starts.
        </p>
      </div>

      <div className="space-y-4">
        {PROVIDER_GROUPS.map((group) => {
          const Icon = GROUP_ICONS[group.id];
          const entries = group.providerIds
            .map((id) => providerById.get(id))
            .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry));
          const readyCount = entries.filter((provider) => {
            const kind = providerStatuses[provider.id] ?? "ready";
            return kind === "ready" || kind === "connected";
          }).length;
          return (
            <section key={group.id} className="space-y-2">
              <header className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <Icon className="h-4 w-4" />
                </span>
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-600">{group.label}</h4>
                  <div className="text-[11px] text-slate-400">{readyCount} ready</div>
                </div>
              </header>
              <div className="space-y-1">
                {entries.map((provider) => {
                  const checked = selectedProviders.has(provider.id);
                  const status = providerStatuses[provider.id] ?? "ready";
                  return (
                    <div key={provider.id} className="space-y-1">
                      <label className="flex items-center justify-between gap-3 rounded-lg border border-transparent px-2 py-1.5 hover:bg-slate-50">
                        <div className="flex items-center gap-2.5">
                          <input
                            type="checkbox"
                            checked={checked}
                            aria-label={providerLabel(provider.id)}
                            onChange={() => toggleProvider(provider.id)}
                            className="h-3.5 w-3.5 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
                          />
                          <span className="text-[12px] font-medium text-slate-800">{providerLabel(provider.id)}</span>
                          <span className="text-[11px] text-slate-500">{PROVIDER_SUBTITLES[provider.id] ?? "Reference provider"}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <StatusBadge kind={status} />
                          {status === "needs_auth" && onExpandAuth && (
                            <button
                              type="button"
                              onClick={() => onExpandAuth(provider.id)}
                              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                            >
                              Connect <ArrowRight className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      </label>
                      {provider.id === authExpandedProviderId && onExpandAuth && onAuthSaved && (
                        <div className="ml-6 mt-1">
                          <ProviderApiKeyForm
                            onCancel={() => onExpandAuth(null)}
                            onSaved={(status) => onAuthSaved(provider.id, status)}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>

      <label className="flex items-center gap-2 text-[12px] text-slate-700">
        <input
          type="checkbox"
          checked={overwrite}
          onChange={(event) => setOverwrite(event.target.checked)}
          className="h-3.5 w-3.5 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
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
  );
}
