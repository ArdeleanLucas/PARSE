interface ContextRingProps {
  used: number | null
  limit: number | null
  size?: number
}

function formatTokenCount(value: number): string {
  if (value >= 1000) {
    const k = value / 1000
    return k >= 10 ? `${Math.round(k)}k` : `${k.toFixed(1)}k`
  }
  return String(value)
}

export function ContextRing({ used, limit, size = 12 }: ContextRingProps) {
  if (used === null || limit === null || limit <= 0) return null

  const fraction = Math.max(0, Math.min(1, used / limit))
  const percent = Math.round(fraction * 100)
  const radius = size / 2 - 1.5
  const circumference = 2 * Math.PI * radius
  const dashLength = circumference * fraction

  const tone =
    fraction >= 0.9
      ? "text-rose-500"
      : fraction >= 0.7
        ? "text-amber-500"
        : "text-indigo-500"
  const title = `Context used: ${formatTokenCount(used)} / ${formatTokenCount(limit)} (${percent}%)`

  return (
    <span
      className={`inline-flex items-center ${tone}`}
      title={title}
      aria-label={title}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.25}
          strokeWidth={1.5}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeDasharray={`${dashLength} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
    </span>
  )
}
