'use client';

// Detail dialog for a single Member row. Shared between the legacy
// /members page and the unified /directory introduced in batch 2.
// Admins land in edit-mode (display name + workspace role), everyone
// else gets a read-only contact card.

import { useMemo, useState } from 'react';

import { ApiError, type Member, type MemberRole } from '../lib/api';
import { useUpdateMemberProfile } from '../lib/queries';

const ROLE_PILL: Record<MemberRole, string> = {
  WORKSPACE_OWNER: 'bg-indigo-100 text-indigo-800',
  WORKSPACE_ADMIN: 'bg-blue-100 text-blue-800',
  WORKSPACE_MEMBER: 'bg-slate-100 text-slate-700',
};

export function MemberDetailDialog({
  member,
  isAdmin,
  isSelf,
  onClose,
}: {
  member: Member;
  isAdmin: boolean;
  isSelf: boolean;
  onClose: () => void;
}) {
  const update = useUpdateMemberProfile();
  const [name, setName] = useState(member.name);
  const [role, setRole] = useState<MemberRole>(member.role);
  const [error, setError] = useState<string | null>(null);

  const dirty = useMemo(
    () => name !== member.name || role !== member.role,
    [name, role, member.name, member.role],
  );

  const onSave = async () => {
    setError(null);
    try {
      await update.mutateAsync({
        memberId: member.id,
        payload: {
          name: name !== member.name ? name : undefined,
          role: role !== member.role ? role : undefined,
        },
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-900">{member.name}</h2>
          {member.email ? <p className="text-xs text-slate-500">{member.email}</p> : null}
        </div>

        <dl className="grid gap-2 px-5 py-4 text-sm sm:grid-cols-[8rem_1fr]">
          <dt className="text-slate-500">Type</dt>
          <dd className="text-slate-800">{member.type === 'AGENT' ? 'Agent' : 'Human'}</dd>
          <dt className="text-slate-500">Workspace role</dt>
          <dd>
            {isAdmin && member.type === 'HUMAN' ? (
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as MemberRole)}
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              >
                <option value="WORKSPACE_OWNER">Owner</option>
                <option value="WORKSPACE_ADMIN">Admin</option>
                <option value="WORKSPACE_MEMBER">Member</option>
              </select>
            ) : (
              <RolePill role={member.role} />
            )}
          </dd>
          <dt className="text-slate-500">Team role</dt>
          <dd className="text-slate-800">{member.team_role ?? '—'}</dd>

          {isAdmin ? (
            <>
              <dt className="text-slate-500">Display name</dt>
              <dd>
                <input
                  type="text"
                  value={name}
                  maxLength={120}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
                />
              </dd>
            </>
          ) : null}
        </dl>

        {error ? (
          <p role="alert" className="px-5 pb-2 text-sm text-red-600">
            {error}
          </p>
        ) : null}

        <div className="flex items-center justify-between gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
          <span className="text-[11px] text-slate-500">
            {isSelf ? 'This is you.' : isAdmin ? 'Admin edit mode.' : 'Read-only view.'}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Close
            </button>
            {isAdmin ? (
              <button
                type="button"
                onClick={onSave}
                disabled={!dirty || update.isPending}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {update.isPending ? 'Saving…' : 'Save'}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function RolePill({ role }: { role: MemberRole }) {
  const tail = role.slice('WORKSPACE_'.length);
  const label = tail.charAt(0) + tail.slice(1).toLowerCase();
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${ROLE_PILL[role]}`}
    >
      {label}
    </span>
  );
}
