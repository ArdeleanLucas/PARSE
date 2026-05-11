import { useEffect } from "react";
import { AlertCircle, CheckCircle, Info, XCircle } from "lucide-react";

type ToastVariant = "info" | "success" | "warning" | "error";

interface ToastProps {
  message: string;
  variant?: ToastVariant;
  duration?: number; // ms — 0 = persistent
  onDismiss?: () => void;
}

const variantStyles: Record<ToastVariant, { accent: string; background: string; text: string; Icon: typeof Info }> = {
  info: { accent: "#3b82f6", background: "#eff6ff", text: "#334155", Icon: Info },
  success: { accent: "#10b981", background: "#ecfdf5", text: "#334155", Icon: CheckCircle },
  warning: { accent: "#f59e0b", background: "#fffbeb", text: "#334155", Icon: AlertCircle },
  error: { accent: "#ef4444", background: "#fef2f2", text: "#334155", Icon: XCircle },
};

export function Toast({ message, variant = "info", duration = 3000, onDismiss }: ToastProps) {
  const style = variantStyles[variant];
  const Icon = style.Icon;
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
        background: style.background,
        color: style.text,
        padding: "0.75rem 1.25rem",
        border: "1px solid rgba(148, 163, 184, 0.2)",
        borderLeft: `4px solid ${style.accent}`,
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
      <Icon size={16} color={style.accent} aria-hidden="true" />
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
