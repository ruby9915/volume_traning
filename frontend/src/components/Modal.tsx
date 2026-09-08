import type { ReactNode } from "react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

export default function Modal({ open, onClose, title, children }: ModalProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50 dark:bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-card-lg bg-surface p-5 shadow-modal">
        {title ? <h2 className="mb-3 text-lg font-bold">{title}</h2> : null}
        {children}
      </div>
    </div>
  );
}
