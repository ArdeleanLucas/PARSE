import React from "react";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: SelectOption[];
  error?: string;
}

export function Select({ label, options, error, id, style, ...props }: SelectProps) {
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
      <select
        id={inputId}
        style={{
          border: error ? "1px solid #ef4444" : "1px solid #d1d5db",
          borderRadius: "0.25rem",
          padding: "0.375rem 0.625rem",
          fontSize: "0.875rem",
          fontFamily: "monospace",
          background: "#fff",
          outline: "none",
          cursor: "pointer",
          ...style,
        }}
        {...props}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {error && <span style={{ fontSize: "0.75rem", color: "#ef4444", fontFamily: "monospace" }}>{error}</span>}
    </div>
  );
}
