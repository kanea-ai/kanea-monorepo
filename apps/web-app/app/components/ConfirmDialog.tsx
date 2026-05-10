'use client';

import { useEffect } from 'react';

// Generic modal for destructive actions. Backdrop click + Escape both
// close. Caller wires the actual mutation through onConfirm and surfaces
// a loading state via `pending`.

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  pending = false,
  onConfirm,
  onCancel,
  tone = 'danger',
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  tone?: 'danger' | 'neutral';
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pending) onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, pending, onCancel]);

  if (!open) return null;

  const confirmTone =
    tone === 'danger'
      ? 'bg-red-600 hover:bg-red-700 focus-visible:ring-red-300'
      : 'bg-indigo-600 hover:bg-indigo-700 focus-visible:ring-indigo-300';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={() => {
        if (!pending) onCancel();
      }}
    >
      <div
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4">
          <h2 id="confirm-dialog-title" className="text-base font-semibold text-slate-900">
            {title}
          </h2>
          <p className="mt-2 text-sm text-slate-600">{message}</p>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className={`rounded-md px-3 py-1.5 text-sm font-medium text-white shadow-sm focus-visible:outline-none focus-visible:ring-2 disabled:opacity-60 ${confirmTone}`}
          >
            {pending ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
