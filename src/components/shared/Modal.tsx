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
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-900/50"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] min-w-[20rem] max-w-[90vw] overflow-auto rounded-lg bg-white p-6 text-slate-900 shadow-xl ring-1 ring-slate-200"
      >
        {title && (
          <div className="mb-4 font-mono text-base font-semibold text-slate-900">
            {title}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
