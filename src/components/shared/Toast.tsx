import { useEffect } from "react";

type ToastVariant = "info" | "success" | "warning" | "error";

interface ToastProps {
  message: string;
  variant?: ToastVariant;
  duration?: number; // ms — 0 = persistent
  onDismiss?: () => void;
}

const variantColors: Record<ToastVariant, string> = {
  info: "#3b82f6",
  success: "#10b981",
  warning: "#f59e0b",
  error: "#ef4444",
};

export function Toast({ message, variant = "info", duration = 3000, onDismiss }: ToastProps) {
  useEffect(() => {
    if (!duration || !onDismiss) return;
    const id = setTimeout(onDismiss, duration);
    return () => clearTimeout(id);
  }, [duration, onDismiss]);

  return (
    <div
      role="alert"
      style={{
        position: "fixed",
        bottom: "1.5rem",
        right: "1.5rem",
        background: variantColors[variant],
        color: "#fff",
        padding: "0.75rem 1.25rem",
        borderRadius: "0.375rem",
        fontFamily: "monospace",
        fontSize: "0.875rem",
        zIndex: 2000,
        boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
      }}
    >
      <span>{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          style={{
            background: "transparent",
            border: "none",
            color: "inherit",
            cursor: "pointer",
            fontSize: "1rem",
            lineHeight: 1,
          }}
        >
          x
        </button>
      )}
    </div>
  );
}
