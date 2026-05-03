export const fmtTime = (s: number | null): string => {
  if (s == null) return '—';
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, '0')}`;
};
