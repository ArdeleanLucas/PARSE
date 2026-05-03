export const fmtTime = (s: number | null): string => {
  if (s == null) return '—';
  const total = Math.round(s * 10) / 10;
  const m = Math.floor(total / 60);
  const r = total - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, '0')}`;
};
