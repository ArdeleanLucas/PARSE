import { Loader2 } from "lucide-react";
import type { ProviderSelectorProps } from "./types";

export function ProviderSelector({
  providers,
  selectedProviders,
  toggleProvider,
  overwrite,
  setOverwrite,
  saving,
}: ProviderSelectorProps) {
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
