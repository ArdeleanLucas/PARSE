import React from 'react';

export const Pill: React.FC<{ children: React.ReactNode; tone?: 'slate'|'emerald'|'indigo' }> = ({ children, tone='slate' }) => {
  const tones: Record<string,string> = {
    slate: 'bg-slate-100 text-slate-600 ring-slate-200',
    emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  };
  return <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ${tones[tone]}`}>{children}</span>;
};

export const SectionCard: React.FC<{ title: string; aside?: React.ReactNode; children: React.ReactNode }> = ({ title, aside, children }) => (
  <section className="rounded-xl border border-slate-200/80 bg-white shadow-[0_1px_0_rgba(15,23,42,0.03)]">
    <header className="flex items-center justify-between px-5 pt-4 pb-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.09em] text-slate-500">{title}</h3>
      {aside}
    </header>
    <div className="px-5 pb-5">{children}</div>
  </section>
);
