'use client';

// Read-only by default + Edit/Save/Cancel toolbar used on every
// detail surface (Department / Team / User / Project).
//
// Two modes:
// - Viewing (editing=false): a single Edit button. Disabled when the
//   caller lacks permission; hovering it surfaces the "smart tooltip"
//   that names the nearest authorised editor.
// - Editing (editing=true): Cancel + Save. Save is disabled until the
//   form is dirty and is also disabled while the mutation is in flight.

import { useState } from 'react';

export interface EditToolbarProps {
  editing: boolean;
  canEdit: boolean;
  /** Tooltip shown when the Edit button is disabled. Pass the smart
   *  message produced by ``disabledEditTooltip`` (or similar). */
  disabledReason?: string;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void | Promise<void>;
  /** Save button stays disabled until the form has at least one change. */
  dirty: boolean;
  /** PATCH in flight. */
  saving: boolean;
  /** Optional override for the right-hand-side label. */
  saveLabel?: string;
  className?: string;
}

export function EditToolbar({
  editing,
  canEdit,
  disabledReason,
  onEdit,
  onCancel,
  onSave,
  dirty,
  saving,
  saveLabel,
  className,
}: EditToolbarProps) {
  return (
    <div className={`flex items-center justify-end gap-2 ${className ?? ''}`.trim()}>
      {editing ? (
        <>
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              void onSave();
            }}
            disabled={saving || !dirty}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? 'Saving…' : (saveLabel ?? 'Save')}
          </button>
        </>
      ) : (
        <EditButton canEdit={canEdit} disabledReason={disabledReason} onEdit={onEdit} />
      )}
    </div>
  );
}

function EditButton({
  canEdit,
  disabledReason,
  onEdit,
}: {
  canEdit: boolean;
  disabledReason?: string;
  onEdit: () => void;
}) {
  const [hover, setHover] = useState(false);
  // Styled tooltip is only useful on the disabled path; when the
  // button is enabled the label is self-explanatory. We also fall
  // back to the native ``title`` attribute for accessibility — a
  // styled popover alone doesn't show up for keyboard-only users.
  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <button
        type="button"
        onClick={onEdit}
        disabled={!canEdit}
        aria-disabled={!canEdit}
        title={!canEdit ? disabledReason : undefined}
        onFocus={() => setHover(true)}
        onBlur={() => setHover(false)}
        className="rounded-md border border-indigo-200 bg-white px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
      >
        Edit
      </button>
      {!canEdit && hover && disabledReason ? (
        <span
          role="tooltip"
          className="pointer-events-none absolute right-0 top-full z-30 mt-1 w-72 rounded-md border border-slate-200 bg-slate-900 px-3 py-2 text-[11px] leading-snug text-slate-50 shadow-lg"
        >
          {disabledReason}
        </span>
      ) : null}
    </span>
  );
}
