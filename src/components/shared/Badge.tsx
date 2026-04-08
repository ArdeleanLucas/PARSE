interface BadgeProps {
  label: string;
  color?: string; // hex background
  textColor?: string;
}

export function Badge({ label, color = "#e5e7eb", textColor = "#374151" }: BadgeProps) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.125rem 0.5rem",
        borderRadius: "9999px",
        fontSize: "0.75rem",
        fontFamily: "monospace",
        background: color,
        color: textColor,
        fontWeight: 500,
        lineHeight: 1.5,
      }}
    >
      {label}
    </span>
  );
}
