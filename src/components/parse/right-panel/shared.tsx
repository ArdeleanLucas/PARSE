import type { LucideIcon } from 'lucide-react';
import { Cpu, Database, Filter, Save, Users as UsersIcon } from 'lucide-react';

export const collapsedPanelIcons: ReadonlyArray<{ icon: LucideIcon; label: string }> = [
  { icon: Database, label: 'Project' },
  { icon: UsersIcon, label: 'Speakers' },
  { icon: Cpu, label: 'Compute' },
  { icon: Filter, label: 'Filters' },
  { icon: Save, label: 'Decisions' },
];
