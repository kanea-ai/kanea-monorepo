'use client';

// Detail dialog for a single Member row, used by /directory.
// Phase 5 batch 2 follow-up — adds:
// - team + team-role editors (admin) so org chart edits don't need the
//   teams page round-trip,
// - priority editor (admin) so the directory's new Priority column
//   can be tuned in place,
// - stats panel (open assignments / completed / avg resolution / last
//   activity / accuracy / tokens) for both humans and agents.

import { useEffect, useMemo, useState } from 'react';

import { ApiError, type Member, type MemberRole, type TeamRole } from '../lib/api';
import {
  useMemberStats,
  useSetMemberSuspension,
  useSetMemberTeam,
  useTeams,
  useUpdateMemberProfile,
} from '../lib/queries';
import { ConfirmDialog } from './ConfirmDialog';

const ROLE_PILL: Record<MemberRole, string> = {
  WORKSPACE_OWNER: 'bg-indigo-100 text-indigo-800',
  WORKSPACE_ADMIN: 'bg-blue-100 text-blue-800',
  WORKSPACE_USER: 'bg-slate-100 text-slate-700',
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
  const setTeam = useSetMemberTeam();
  const setSuspension = useSetMemberSuspension();
  const { data: teams } = useTeams();
  const { data: stats, isLoading: statsLoading } = useMemberStats(member.id);
  // The suspension flow is destructive enough (kicks the member out
  // of every workspace request) that we route it through a confirm
  // dialog. Revoking is one click — no second prompt.
  const [confirmSuspend, setConfirmSuspend] = useState(false);

  const [name, setName] = useState(member.name);
  const [role, setRole] = useState<MemberRole>(member.role);
  const [priority, setPriority] = useState<number>(member.priority);
  const [teamId, setTeamId] = useState<string>(member.team_id ?? '');
  const [teamRole, setTeamRole] = useState<TeamRole>(member.team_role ?? 'MEMBER');
  const [error, setError] = useState<string | null>(null);

  // Reset form state whenever a different member's dialog is opened.
  useEffect(() => {
    setName(member.name);
    setRole(member.role);
    setPriority(member.priority);
    setTeamId(member.team_id ?? '');
    setTeamRole(member.team_role ?? 'MEMBER');
    setError(null);
  }, [member.id, member.name, member.role, member.priority, member.team_id, member.team_role]);

  // The "Save" button is enabled when any field diverges from the
  // current member. Team membership has its own button so a typo on
  // the priority field doesn't require committing the team change.
  const profileDirty = useMemo(
    () => name !== member.name || role !== member.role || priority !== member.priority,
    [name, role, priority, member.name, member.role, member.priority],
  );

  const teamFieldDirty = useMemo(() => {
    const currentTeam = member.team_id ?? '';
    const currentTeamRole = member.team_role ?? 'MEMBER';
    if (teamId !== currentTeam) return true;
    if (teamId !== '' && teamRole !== currentTeamRole) return true;
    return false;
  }, [teamId, teamRole, member.team_id, member.team_role]);

  const onSaveProfile = async () => {
    setError(null);
    try {
      await update.mutateAsync({
        memberId: member.id,
        payload: {
          name: name !== member.name ? name : undefined,
          role: role !== member.role ? role : undefined,
          priority: priority !== member.priority ? priority : undefined,
        },
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save');
    }
  };

  const onSaveTeam = async () => {
    setError(null);
    try {
      await setTeam.mutateAsync({
        memberId: member.id,
        payload: {
          team_id: teamId === '' ? null : teamId,
          team_role: teamId === '' ? null : teamRole,
        },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update team');
    }
  };

  const isHuman = member.type === 'HUMAN';
  const pending = update.isPending || setTeam.isPending || setSuspension.isPending;

  const onSuspend = async () => {
    setError(null);
    try {
      await setSuspension.mutateAsync({
        memberId: member.id,
        payload: { is_suspended: true },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to suspend');
    }
  };

  const onRevoke = async () => {
    setError(null);
    try {
      await setSuspension.mutateAsync({
        memberId: member.id,
        payload: { is_suspended: false },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to revoke');
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
        className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-slate-900">{member.name}</h2>
              {member.is_suspended ? (
                <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                  Suspended
                </span>
              ) : null}
            </div>
            {member.email ? <p className="text-xs text-slate-500">{member.email}</p> : null}
          </div>
          <TypePill type={member.type} />
        </div>

        {/* Profile card — name / role / priority. Editable by workspace
            owners + admins. Backend enforces the last-OWNER demotion
            guard; we surface its 403 inline below. */}
        <Section title="Profile & permissions">
          <Field label="Display name">
            {isAdmin ? (
              <input
                type="text"
                value={name}
                maxLength={120}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm shadow-sm"
              />
            ) : (
              <span className="text-sm text-slate-800">{member.name}</span>
            )}
          </Field>
          <Field label="Workspace role">
            {isAdmin ? (
              <div>
                {/* Workspace role is the system-power axis and applies
                    to humans AND agents — agents need access power
                    too. OWNER is reserved for humans (an agent has no
                    User row to anchor it on); the dropdown still
                    offers it for parity with the schema, but the api
                    refuses the change for agents. */}
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as MemberRole)}
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
                >
                  {isHuman ? <option value="WORKSPACE_OWNER">Owner</option> : null}
                  <option value="WORKSPACE_ADMIN">Admin</option>
                  <option value="WORKSPACE_USER">User</option>
                </select>
                <p className="mt-1 text-[10px] italic text-slate-500">
                  Cannot demote the last workspace owner.
                </p>
              </div>
            ) : (
              <RolePill role={member.role} />
            )}
          </Field>
          <Field label="Priority">
            {isAdmin ? (
              <input
                type="number"
                min={1}
                max={100}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm shadow-sm"
              />
            ) : (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700">
                P{member.priority}
              </span>
            )}
          </Field>
          {isAdmin ? (
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={onSaveProfile}
                disabled={!profileDirty || pending}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {update.isPending ? 'Saving…' : 'Save profile'}
              </button>
            </div>
          ) : null}
        </Section>

        {/* Team assignment. Admins (workspace owner/admin) can move a
            member between teams or unassign them. Read-only otherwise. */}
        <Section title="Team">
          <Field label="Team">
            {isAdmin ? (
              <select
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              >
                <option value="">— No team —</option>
                {(teams ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            ) : (
              <span className="text-sm text-slate-800">
                {member.team_id
                  ? ((teams ?? []).find((t) => t.id === member.team_id)?.name ?? '—')
                  : '—'}
              </span>
            )}
          </Field>
          <Field label="Team role">
            {isAdmin ? (
              <select
                value={teamRole}
                disabled={teamId === ''}
                onChange={(e) => setTeamRole(e.target.value as TeamRole)}
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              >
                <option value="HEAD">HEAD</option>
                <option value="MANAGER">MANAGER</option>
                <option value="LEAD">LEAD</option>
                <option value="MEMBER">MEMBER</option>
              </select>
            ) : (
              <span className="text-sm text-slate-800">{member.team_role ?? '—'}</span>
            )}
          </Field>
          {isAdmin ? (
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={onSaveTeam}
                disabled={!teamFieldDirty || pending}
                className="rounded-md border border-indigo-200 bg-white px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {setTeam.isPending ? 'Saving…' : 'Save team'}
              </button>
            </div>
          ) : null}
        </Section>

        {/* Stats — same surface for humans and agents. */}
        <Section title="Activity">
          {statsLoading ? (
            <p className="text-xs text-slate-500">Loading stats…</p>
          ) : !stats ? (
            <p className="text-xs italic text-slate-500">No stats available.</p>
          ) : (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <Stat label="Open assignments" value={stats.assigned_count} />
              <Stat label="Completed" value={stats.completed_count} />
              <Stat
                label="Avg resolution"
                value={
                  stats.avg_resolution_seconds != null
                    ? formatDuration(stats.avg_resolution_seconds)
                    : '—'
                }
              />
              <Stat
                label="Last activity"
                value={
                  stats.last_activity_at ? new Date(stats.last_activity_at).toLocaleString() : '—'
                }
              />
              {member.type === 'AGENT' && stats.accuracy_percent != null ? (
                <Stat label="Accuracy" value={`${stats.accuracy_percent.toFixed(1)}%`} />
              ) : null}
              <Stat label="Tokens used" value={stats.total_tokens_used} />
            </dl>
          )}
        </Section>

        {/* Suspension is workspace-scoped: a flipped member can still
            log in and use other workspaces, but every request bound to
            THIS workspace 403s at the api. Admin-only; the api enforces
            the last-active-owner invariant and refuses self-suspend. */}
        {isAdmin && !isSelf ? (
          <Section title="Workspace access">
            {member.is_suspended ? (
              <div className="space-y-2">
                <p className="text-sm text-red-700">
                  This member is currently suspended. They cannot use this workspace until the
                  suspension is revoked. They can still access other workspaces they belong to.
                </p>
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={onRevoke}
                    disabled={pending}
                    className="rounded-md border border-emerald-200 bg-white px-3 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {setSuspension.isPending ? 'Revoking…' : 'Revoke suspension'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-slate-600">
                  Suspending blocks every request this member sends to this workspace (403). They
                  can still use other workspaces they belong to. The last active workspace owner
                  cannot be suspended.
                </p>
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => setConfirmSuspend(true)}
                    disabled={pending}
                    className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Suspend member
                  </button>
                </div>
              </div>
            )}
          </Section>
        ) : null}

        {error ? (
          <p role="alert" className="px-5 pb-2 text-sm text-red-600">
            {error}
          </p>
        ) : null}

        <div className="flex items-center justify-between gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
          <span className="text-[11px] text-slate-500">
            {isSelf ? 'This is you.' : isAdmin ? 'Admin edit mode.' : 'Read-only view.'}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
        </div>

        <ConfirmDialog
          open={confirmSuspend}
          title={`Suspend ${member.name}?`}
          message="Every request this member sends to this workspace will be blocked with 403 until you revoke the suspension. Their tasks, comments and history are kept."
          confirmLabel="Suspend"
          pending={setSuspension.isPending}
          onCancel={() => setConfirmSuspend(false)}
          onConfirm={async () => {
            await onSuspend();
            setConfirmSuspend(false);
          }}
        />
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-slate-100 px-5 py-4 last:border-b-0">
      <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] items-center gap-2 text-sm">
      <span className="text-slate-500">{label}</span>
      <div>{children}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-dashed border-slate-100 pb-1.5">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-medium tabular-nums text-slate-900">{value}</dd>
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
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${ROLE_PILL[role]}`}
    >
      {label}
    </span>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}
