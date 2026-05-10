'use client';

// Modal opened from /audit when the user clicks an actor's name.
// Renders the priority-scoped MemberProfile — full shape for owners
// and same-rank-or-higher admins, reduced (id/name/email/type) for
// lower-rank admins. The api enforces the scoping; the UI just
// renders the fields that come back.

import { useEffect } from 'react';

import type { MemberRole } from '../lib/api';
import { useMemberProfile } from '../lib/queries';

const ROLE_PILL: Record<MemberRole, string> = {
  WORKSPACE_OWNER: 'bg-indigo-100 text-indigo-800',
  WORKSPACE_ADMIN: 'bg-blue-100 text-blue-800',
  WORKSPACE_USER: 'bg-slate-100 text-slate-700',
};

export function ActorProfileDialog({
  memberId,
  onClose,
}: {
  memberId: string;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error } = useMemberProfile(memberId);

  // Escape closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Actor profile"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Profile
            </p>
            <h2 className="truncate text-base font-semibold text-slate-900">{data?.name ?? '—'}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-slate-500 hover:bg-slate-100"
          >
            ✕
          </button>
        </header>

        {isLoading ? (
          <p className="px-5 py-6 text-sm text-slate-500">Loading…</p>
        ) : isError ? (
          <p className="px-5 py-6 text-sm text-red-600">
            Failed to load profile: {(error as Error).message}
          </p>
        ) : !data ? (
          <p className="px-5 py-6 text-sm text-slate-500">No profile data.</p>
        ) : (
          <div className="space-y-3 px-5 py-4 text-sm">
            <Field label="Type">
              <TypePill type={data.type} />
            </Field>
            <Field label="Email">
              <span className="text-slate-800">{data.email ?? '—'}</span>
            </Field>
            <Field label="ID">
              <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                {data.id}
              </code>
            </Field>

            {/* Restricted fields — hidden for lower-rank admins. The
                api returns null on those fields when is_limited_view
                is true, so we drive everything off that flag rather
                than per-field nullability. */}
            {data.is_limited_view ? (
              <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Limited view — your priority is below this member's, so role, team and suspension
                state aren't shown.
              </p>
            ) : (
              <>
                {data.role ? (
                  <Field label="Workspace role">
                    <RolePill role={data.role} />
                  </Field>
                ) : null}
                {data.priority != null ? (
                  <Field label="Priority">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700">
                      P{data.priority}
                    </span>
                  </Field>
                ) : null}
                {data.team_role ? (
                  <Field label="Team role">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700">
                      {data.team_role}
                    </span>
                  </Field>
                ) : null}
                {data.is_suspended ? (
                  <Field label="Status">
                    <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                      Suspended
                    </span>
                  </Field>
                ) : null}
              </>
            )}
          </div>
        )}

        <footer className="flex justify-end border-t border-slate-100 bg-slate-50 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
        </footer>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] items-center gap-2">
      <span className="text-xs text-slate-500">{label}</span>
      <div>{children}</div>
    </div>
  );
}

function TypePill({ type }: { type: 'HUMAN' | 'AGENT' }) {
  if (type === 'AGENT') {
    return (
      <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700">
        Agent
      </span>
    );
  }
  return (
    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
      Human
    </span>
  );
}

function RolePill({ role }: { role: MemberRole }) {
  const tail = role.slice('WORKSPACE_'.length);
  const label = tail.charAt(0) + tail.slice(1).toLowerCase();
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${ROLE_PILL[role]}`}
    >
      {label}
    </span>
  );
}
