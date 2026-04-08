import { useEffect, useState } from "react";

interface SpinnerProps {
  size?: number;
  label?: string;
}

export function Spinner({ size = 24, label }: SpinnerProps) {
  const [angle, setAngle] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setAngle((a) => (a + 30) % 360), 80);
    return () => clearInterval(id);
  }, []);

  return (
    <span
      role="status"
      aria-label={label ?? "Loading"}
      style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        style={{ transform: `rotate(${angle}deg)` }}
      >
        <circle cx="12" cy="12" r="10" stroke="#e5e7eb" strokeWidth="3" />
        <path d="M12 2a10 10 0 0 1 10 10" stroke="#3b82f6" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {label && <span style={{ fontSize: "0.875rem", color: "#6b7280", fontFamily: "monospace" }}>{label}</span>}
    </span>
  );
}
