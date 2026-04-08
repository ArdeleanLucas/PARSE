import React from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({ label, error, id, style, ...props }: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
      {label && (
        <label
          htmlFor={inputId}
          style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "#374151", fontWeight: 500 }}
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        style={{
          border: error ? "1px solid #ef4444" : "1px solid #d1d5db",
          borderRadius: "0.25rem",
          padding: "0.375rem 0.625rem",
          fontSize: "0.875rem",
          fontFamily: "monospace",
          outline: "none",
          ...style,
        }}
        {...props}
      />
      {error && <span style={{ fontSize: "0.75rem", color: "#ef4444", fontFamily: "monospace" }}>{error}</span>}
    </div>
  );
}
