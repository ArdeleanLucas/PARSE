import React from "react";

interface PanelProps {
  title?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export function Panel({ title, children, style }: PanelProps) {
  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "0.375rem",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        ...style,
      }}
    >
      {title && (
        <div
          style={{
            padding: "0.5rem 0.75rem",
            fontFamily: "monospace",
            fontWeight: 600,
            fontSize: "0.8125rem",
            background: "#f9fafb",
            borderBottom: "1px solid #e5e7eb",
            letterSpacing: "0.04em",
            textTransform: "uppercase",
          }}
        >
          {title}
        </div>
      )}
      <div style={{ padding: "0.75rem", flex: 1, overflow: "auto" }}>{children}</div>
    </div>
  );
}
