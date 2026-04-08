import React from "react";

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: string; // required for a11y aria-label
  icon: string;  // text/unicode icon
  active?: boolean;
}

export function IconButton({ label, icon, active = false, style, ...props }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      title={label}
      style={{
        background: active ? "#dbeafe" : "transparent",
        border: "1px solid",
        borderColor: active ? "#93c5fd" : "#d1d5db",
        borderRadius: "0.25rem",
        color: active ? "#1d4ed8" : "#374151",
        cursor: "pointer",
        fontSize: "0.875rem",
        padding: "0.25rem 0.5rem",
        lineHeight: 1.5,
        fontFamily: "monospace",
        ...style,
      }}
      {...props}
    >
      {icon}
    </button>
  );
}
