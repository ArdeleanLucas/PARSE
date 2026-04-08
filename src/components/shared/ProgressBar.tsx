interface ProgressBarProps {
  value: number; // 0–100
  label?: string;
  height?: number;
}

export function ProgressBar({ value, label, height = 6 }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div style={{ width: "100%" }}>
      {label && (
        <div
          style={{ fontSize: "0.75rem", color: "#6b7280", marginBottom: "0.25rem", fontFamily: "monospace" }}
        >
          {label} {pct.toFixed(0)}%
        </div>
      )}
      <div
        style={{
          width: "100%",
          height,
          background: "#e5e7eb",
          borderRadius: height / 2,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: "#3b82f6",
            transition: "width 0.2s ease",
          }}
        />
      </div>
    </div>
  );
}
