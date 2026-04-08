import React from "react";

type Variant = "primary" | "secondary" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const styles: Record<Variant, React.CSSProperties> = {
  primary: { background: "#3b82f6", color: "#fff", border: "none" },
  secondary: { background: "transparent", color: "#374151", border: "1px solid #d1d5db" },
  danger: { background: "#ef4444", color: "#fff", border: "none" },
};

const sizes: Record<Size, React.CSSProperties> = {
  sm: { padding: "0.25rem 0.625rem", fontSize: "0.75rem" },
  md: { padding: "0.5rem 1rem", fontSize: "0.875rem" },
  lg: { padding: "0.75rem 1.5rem", fontSize: "1rem" },
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  children,
  disabled,
  style,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled ?? loading}
      style={{
        cursor: disabled ?? loading ? "not-allowed" : "pointer",
        borderRadius: "0.25rem",
        fontFamily: "inherit",
        ...styles[variant],
        ...sizes[size],
        ...style,
      }}
      {...props}
    >
      {loading ? "..." : children}
    </button>
  );
}
