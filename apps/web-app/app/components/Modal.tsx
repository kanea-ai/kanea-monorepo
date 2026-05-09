'use client';

// Generic modal/dialog used for forms (Create Team, Create Project).
// Distinct from ConfirmDialog — that one is purpose-built for destructive
// yes/no prompts and locks its layout. This one takes any children and
// is composable.
//
// UX:
// - Backdrop click closes (unless `pending` is true — same convention as
//   ConfirmDialog).
// - Escape closes.
// - The first focusable element inside `children` gets focus on open.
// - Footer slot lives at the bottom with a soft separator.

import { useEffect, useId, useRef, type ReactNode } from 'react';

interface ModalProps {
  open: boolean;
  title: string;
  /** Shown under the title. Optional. */
  subtitle?: string;
  /** Body content — usually a form. */
  children: ReactNode;
  /** Sticky bottom slot — typically Cancel + Submit buttons. */
  footer?: ReactNode;
  onClose: () => void;
  /** Block close while a mutation is in flight. */
  pending?: boolean;
  /** Tailwind max-width override. Defaults to max-w-md. */
  size?: 'sm' | 'md' | 'lg';
}

const SIZE: Record<NonNullable<ModalProps['size']>, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
};

export function Modal({
  open,
  title,
  subtitle,
  children,
  footer,
  onClose,
  pending = false,
  size = 'md',
}: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);

  // Escape closes; focus the first focusable element inside the dialog.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pending) onClose();
    };
    window.addEventListener('keydown', onKey);

    // Best-effort focus: try the first input/textarea/select, fallback to
    // the dialog container itself.
    const first = dialogRef.current?.querySelector<HTMLElement>(
      'input:not([disabled]), textarea:not([disabled]), select:not([disabled]), button:not([disabled])',
    );
    first?.focus();

    return () => window.removeEventListener('keydown', onKey);
  }, [open, pending, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={() => {
        if (!pending) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className={`w-full ${SIZE[size]} rounded-lg border border-slate-200 bg-white shadow-xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-slate-100 px-5 py-4">
          <h2 id={titleId} className="text-base font-semibold text-slate-900">
            {title}
          </h2>
          {subtitle ? <p className="mt-1 text-xs text-slate-500">{subtitle}</p> : null}
        </header>
        <div className="px-5 py-4">{children}</div>
        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}
