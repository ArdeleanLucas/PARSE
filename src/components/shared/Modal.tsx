import React, { useEffect } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  /** When false, backdrop clicks and the Escape key are no-ops. Use this
   * for phases that must run to completion (e.g. an async offset-detect
   * job) so a stray click doesn't silently drop the user out of the flow
   * while work continues in the background. Default: true. */
  dismissible?: boolean;
}

export function Modal({ open, onClose, title, children, dismissible = true }: ModalProps) {
  useEffect(() => {
    if (!open || !dismissible) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose, dismissible]);

  if (!open) return null;

  return (
    <div
      onClick={dismissible ? onClose : undefined}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: "0.5rem",
          padding: "1.5rem",
          minWidth: "20rem",
          maxWidth: "90vw",
          maxHeight: "90vh",
          overflow: "auto",
        }}
      >
        {title && (
          <div
            style={{
              fontWeight: 600,
              marginBottom: "1rem",
              fontSize: "1rem",
              fontFamily: "monospace",
            }}
          >
            {title}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
