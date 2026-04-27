import type { LucideIcon } from 'lucide-react';
import { Cpu, Database, Filter, Save, Users as UsersIcon } from 'lucide-react';

import type { CompareTagFilter } from './types';

export const collapsedPanelIcons: ReadonlyArray<{ icon: LucideIcon; label: string }> = [
  { icon: Database, label: 'Project' },
  { icon: UsersIcon, label: 'Speakers' },
  { icon: Cpu, label: 'Compute' },
  { icon: Filter, label: 'Filters' },
  { icon: Save, label: 'Decisions' },
];

export const tagFilterOptions: ReadonlyArray<{
  key: CompareTagFilter;
  label: string;
  dot: string;
}> = [
  { key: 'all', label: 'All concepts', dot: 'bg-slate-400' },
  { key: 'untagged', label: 'Untagged', dot: 'bg-slate-300' },
  { key: 'review', label: 'Review needed', dot: 'bg-amber-400' },
  { key: 'confirmed', label: 'Confirmed', dot: 'bg-emerald-500' },
  { key: 'problematic', label: 'Problematic', dot: 'bg-rose-500' },
];
