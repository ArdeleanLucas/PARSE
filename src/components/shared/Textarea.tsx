import React from "react";

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export function Textarea({ label, error, id, style, ...props }: TextareaProps) {
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
      <textarea
        id={inputId}
        style={{
          border: error ? "1px solid #ef4444" : "1px solid #d1d5db",
          borderRadius: "0.25rem",
          padding: "0.375rem 0.625rem",
          fontSize: "0.875rem",
          fontFamily: "monospace",
          resize: "vertical",
          outline: "none",
          ...style,
        }}
        {...props}
      />
      {error && <span style={{ fontSize: "0.75rem", color: "#ef4444", fontFamily: "monospace" }}>{error}</span>}
    </div>
  );
}
