'use client';

// Workspace members directory. Phase 2.
//
// Visibility is enforced by the api: OWNER/ADMIN see everyone, regular
// members see their team plus themselves. The page just renders what
// the api returned and exposes the narrowing filters (name/role/team/
// project/humans-only) on top.

import { useMemo, useState } from 'react';

import { ApiError, type Member, type MemberRole } from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import { useMembers, useProjects, useTeams, useUpdateMemberProfile } from '../../lib/queries';

const ROLE_OPTIONS: { value: MemberRole | ''; label: string }[] = [
  { value: '', label: 'Any role' },
  { value: 'WORKSPACE_OWNER', label: 'Owner' },
  { value: 'WORKSPACE_ADMIN', label: 'Admin' },
  { value: 'WORKSPACE_MEMBER', label: 'Member' },
];

export default function MembersPage() {
  const principal = useCurrentPrincipal();
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';

  const [name, setName] = useState('');
  const [role, setRole] = useState<MemberRole | ''>('');
  const [teamId, setTeamId] = useState('');
  const [projectId, setProjectId] = useState('');
  const [humansOnly, setHumansOnly] = useState(true);

  const {
    data: members,
    isLoading,
    isError,
    error,
  } = useMembers({
    name: name || undefined,
    role: role || undefined,
    teamId: teamId || undefined,
    projectId: projectId || undefined,
    humansOnly,
  });

  const { data: teams } = useTeams();
  const { data: projects } = useProjects();

  const [openMember, setOpenMember] = useState<Member | null>(null);

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Members</h1>
        <p className="text-sm text-slate-500">
          Workspace directory. Filter by name, role, team, or project. Click a row to{' '}
          {isAdmin ? 'edit details' : 'see contact + stats'}.
        </p>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="grid gap-2 border-b border-slate-100 p-3 sm:grid-cols-[1fr_auto_auto_auto_auto]">
          <input
            type="search"
            placeholder="Search by name…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as MemberRole | '')}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            {ROLE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <select
            value={teamId}
            onChange={(e) => setTeamId(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">Any team</option>
            {(teams ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">Any project</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <label className="inline-flex items-center gap-1 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={humansOnly}
              onChange={(e) => setHumansOnly(e.target.checked)}
            />
            Humans only
          </label>
        </div>

        {isError ? (
          <p className="px-4 py-6 text-sm text-red-600">
            Failed to load members: {(error as Error).message}
          </p>
        ) : isLoading ? (
          <p className="px-4 py-6 text-sm text-slate-500">Loading members…</p>
        ) : !members || members.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm italic text-slate-500">
            No members match these filters.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {members.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => setOpenMember(m)}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-slate-50"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate font-medium text-slate-900">{m.name}</span>
                    {m.type === 'AGENT' ? (
                      <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-violet-700">
                        Agent
                      </span>
                    ) : null}
                  </span>
                  <span className="flex shrink-0 items-center gap-3 text-xs text-slate-500">
                    {m.email ? <span className="truncate">{m.email}</span> : null}
                    <RolePill role={m.role} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {openMember ? (
        <MemberDetailDialog
          member={openMember}
          isAdmin={isAdmin}
          isSelf={openMember.id === principal?.member_id}
          onClose={() => setOpenMember(null)}
        />
      ) : null}
    </div>
  );
}

function MemberDetailDialog({
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

const ROLE_PILL: Record<MemberRole, string> = {
  WORKSPACE_OWNER: 'bg-indigo-100 text-indigo-800',
  WORKSPACE_ADMIN: 'bg-blue-100 text-blue-800',
  WORKSPACE_MEMBER: 'bg-slate-100 text-slate-700',
};

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
