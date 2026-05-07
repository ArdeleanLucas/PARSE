import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface CollapsibleSectionProps {
  title: string;
  icon?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
  defaultOpen?: boolean;
}

export function CollapsibleSection({
  title,
  icon,
  meta,
  children,
  className = 'border-b border-slate-100 p-4',
  defaultOpen = true,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const Icon = open ? ChevronDown : ChevronRight;

  return (
    <section className={className}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="mb-2 flex w-full items-center justify-between gap-2 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500"
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <Icon className="h-3 w-3 shrink-0 text-slate-400" />
          {icon}
          <span className="truncate">{title}</span>
        </span>
        {meta ? <span className="shrink-0 normal-case tracking-normal">{meta}</span> : null}
      </button>
      {open ? children : null}
    </section>
  );
}
