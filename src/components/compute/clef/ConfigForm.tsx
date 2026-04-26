import { Check, Info, Search, X } from "lucide-react";
import { MAX_PRIMARY, type ConfigFormProps } from "./types";

export function ConfigForm({
  primary,
  secondary,
  allLanguages,
  filtered,
  search,
  setSearch,
  highlightIdx,
  setHighlightIdx,
  togglePrimary,
  toggleSecondary,
  customCode,
  setCustomCode,
  customName,
  setCustomName,
  addCustom,
}: ConfigFormProps) {
  return (
    <div className="space-y-4">
      <section>
        <div className="mb-1 flex items-center gap-1.5">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-600">
            Primary contact languages
          </h3>
          <span className="text-[11px] text-slate-400">({primary.length}/{MAX_PRIMARY})</span>
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
            const entry = allLanguages.find((language) => language.code === code);
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

      <section>
        <div className="relative mb-2">
          <Search className="absolute left-2 top-1.5 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setHighlightIdx(0);
            }}
            onKeyDown={(e) => {
              if (filtered.length === 0) return;
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setHighlightIdx((idx) => (idx + 1) % filtered.length);
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setHighlightIdx((idx) => (idx - 1 + filtered.length) % filtered.length);
              } else if (e.key === "Enter") {
                e.preventDefault();
                const language = filtered[highlightIdx];
                if (!language) return;
                if (primary.includes(language.code) || primary.length < MAX_PRIMARY) {
                  togglePrimary(language.code);
                } else {
                  toggleSecondary(language.code);
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
          {filtered.map((language, idx) => {
            const isPrimary = primary.includes(language.code);
            const isSecondary = secondary.has(language.code);
            const highlighted = idx === highlightIdx;
            return (
              <div
                key={language.code}
                id={`clef-lang-${language.code}`}
                role="option"
                aria-selected={isPrimary || isSecondary}
                className={
                  "flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-1.5 text-[12px] last:border-b-0 "
                  + (highlighted ? "bg-indigo-50" : "")
                }
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-slate-800">{language.name}</div>
                  <div className="text-[10px] text-slate-400">
                    {language.code}
                    {language.family ? ` · ${language.family}` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() => togglePrimary(language.code)}
                    disabled={!isPrimary && primary.length >= MAX_PRIMARY}
                    className={
                      "rounded px-2 py-0.5 text-[10px] font-semibold "
                      + (isPrimary
                        ? "bg-indigo-600 text-white"
                        : "border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40")
                    }
                    title={!isPrimary && primary.length >= MAX_PRIMARY ? `At most ${MAX_PRIMARY} primary languages` : ""}
                  >
                    Primary
                  </button>
                  <button
                    onClick={() => toggleSecondary(language.code)}
                    className={
                      "rounded px-2 py-0.5 text-[10px] font-semibold "
                      + (isSecondary
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
  );
}
