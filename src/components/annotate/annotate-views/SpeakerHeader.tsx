import type { Concept } from "./types";

interface SpeakerHeaderProps {
  annotated: boolean;
  complete: boolean;
  concept: Concept;
  speaker: string;
  totalConcepts: number;
  onPrev: () => void;
  onNext: () => void;
}

export function SpeakerHeader({ annotated, complete, concept, speaker, totalConcepts, onPrev, onNext }: SpeakerHeaderProps) {
  return (
    <section className="px-8 pt-6">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-center gap-3">
          <button
            onClick={onPrev}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
          >
            <span>←</span>
            <span>Prev</span>
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
              Concept <span className="font-mono">#{concept.id}</span> <span>·</span> {concept.id} of {totalConcepts}
            </div>
            <div className="mt-0.5 flex items-center gap-3">
              <h1 className="text-[32px] font-semibold tracking-tight text-slate-900">{concept.name}</h1>
              <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-slate-700">
                {speaker}
              </span>
              {complete ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700 ring-1 ring-teal-200">
                  Complete
                </span>
              ) : annotated ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                  Annotated
                </span>
              ) : null}
            </div>
            <div className="mt-1 flex items-center gap-1 font-mono text-[11px] text-slate-400">
              <span className="text-[9px] uppercase tracking-wider text-slate-400">Source</span>
              <span className="text-slate-500">{speaker}.wav</span>
            </div>
          </div>
          <button
            onClick={onNext}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
          >
            <span>Next</span>
            <span>→</span>
          </button>
        </div>
      </div>
    </section>
  );
}
