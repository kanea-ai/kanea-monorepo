'use client';

import { useState, type FormEvent } from 'react';

import {
  ApiError,
  type InviteCreateResponse,
  type Member,
  type MemberRole,
  type TaskRequest,
  type TeamRecord,
  type TeamRole,
} from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import {
  useCreateInvite,
  useCreateTeam,
  useFulfillRequest,
  useMembers,
  useRejectRequest,
  useSetMemberTeam,
  useTeamInboxRequests,
  useTeams,
} from '../../lib/queries';

// Teams page. Three sections:
//  1. Invite form — workspace admins create one-time invite links.
//  2. Teams — a directory of teams; only admins see the create form.
//  3. Members — workspace roster, with team + team-role editors gated
//     to admins so MEMBERs can browse but not modify the org chart.

export default function TeamsPage() {
  const { data: members, isLoading, isError, error } = useMembers();
  const principal = useCurrentPrincipal();
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Teams</h1>
        <p className="text-sm text-slate-500">
          Workspace members, organised into teams. Each team has a head, managers, leads, and
          members. Only workspace admins can create teams or change team assignments.
        </p>
      </header>

      <InviteSection isAdmin={isAdmin} />

      <TeamsSection isAdmin={isAdmin} />

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <header className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Members</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Everyone with access to this workspace, including agents.
          </p>
        </header>
        <div className="p-1">
          {isError ? (
            <p className="px-3 py-6 text-sm text-red-600">
              Failed to load members: {(error as Error).message}
            </p>
          ) : isLoading ? (
            <SkeletonRows count={3} />
          ) : !members || members.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-slate-500">No members yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {members.map((m) => (
                <MemberRow key={m.id} member={m} isAdmin={isAdmin} />
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function TeamsSection({ isAdmin }: { isAdmin: boolean }) {
  const { data: teams, isLoading, isError, error } = useTeams();
  const { data: members } = useMembers();
  const create = useCreateTeam();
  const [name, setName] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setCreateError(null);
    try {
      await create.mutateAsync({ name: name.trim() });
      setName('');
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.detail : 'Failed to create team');
    }
  };

  const membersByTeam = (teamId: string) => (members ?? []).filter((m) => m.team_id === teamId);
  const unassigned = (members ?? []).filter((m) => m.team_id == null);

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Teams</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Each team groups members under a head, managers, leads, and standard members.
          </p>
        </div>
      </header>

      {isAdmin ? (
        <form
          className="flex flex-wrap items-end gap-2 border-b border-slate-100 px-4 py-3"
          onSubmit={onSubmit}
        >
          <div className="min-w-[12rem] flex-1">
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600">
              New team
            </label>
            <input
              type="text"
              required
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
              placeholder="Backend"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <button
            type="submit"
            disabled={create.isPending || name.trim() === ''}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {create.isPending ? 'Creating…' : 'Create team'}
          </button>
        </form>
      ) : null}
      {createError ? (
        <p role="alert" className="px-4 pt-2 text-sm text-red-600">
          {createError}
        </p>
      ) : null}

      <div className="p-1">
        {isError ? (
          <p className="px-3 py-6 text-sm text-red-600">
            Failed to load teams: {(error as Error).message}
          </p>
        ) : isLoading ? (
          <p className="px-3 py-6 text-sm text-slate-500">Loading teams…</p>
        ) : !teams || teams.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm italic text-slate-500">
            No teams yet. {isAdmin ? 'Create one above.' : 'Ask an admin to create one.'}
          </p>
        ) : (
          <ul className="space-y-2 px-2 py-2">
            {teams.map((t) => (
              <TeamCard key={t.id} team={t} members={membersByTeam(t.id)} isAdmin={isAdmin} />
            ))}
          </ul>
        )}
        {unassigned.length > 0 ? (
          <p className="px-4 py-2 text-[11px] text-slate-500">
            {unassigned.length} member{unassigned.length === 1 ? '' : 's'} not assigned to a team.
          </p>
        ) : null}
      </div>
    </section>
  );
}

function TeamCard({
  team,
  members,
  isAdmin,
}: {
  team: TeamRecord;
  members: Member[];
  isAdmin: boolean;
}) {
  // Sort by role rank so HEAD floats to the top.
  const ranked = [...members].sort((a, b) => roleRank(a.team_role) - roleRank(b.team_role));
  return (
    <li className="rounded-md border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <p className="text-sm font-semibold text-slate-900">{team.name}</p>
        <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
          {members.length} {members.length === 1 ? 'member' : 'members'}
        </span>
      </div>
      {ranked.length === 0 ? (
        <p className="px-3 py-2 text-xs italic text-slate-400">
          {isAdmin ? 'No members yet — assign someone below.' : 'No members yet.'}
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {ranked.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs">
              <span className="truncate text-slate-800">
                {m.name}
                {m.type === 'AGENT' ? (
                  <span className="ml-1 text-[10px] text-violet-700">(agent)</span>
                ) : null}
              </span>
              <TeamRolePill role={m.team_role} />
            </li>
          ))}
        </ul>
      )}

      <TeamInbox teamId={team.id} />
    </li>
  );
}

function TeamInbox({ teamId }: { teamId: string }) {
  // Pending cross-team requests anchored to a task on *this* team.
  // Surfaces what the team's leadership needs to act on. Visible to
  // every workspace member; the actions are gated server-side.
  const { data: requests, isLoading } = useTeamInboxRequests(teamId, 'PENDING');
  const count = requests?.length ?? 0;

  return (
    <details className="border-t border-slate-100 [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-1.5 text-xs hover:bg-slate-50">
        <span className="font-medium text-slate-700">Pending requests</span>
        <span
          className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
            count > 0 ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-500'
          }`}
        >
          {count}
        </span>
      </summary>
      <div className="space-y-1.5 px-3 py-2">
        {isLoading ? (
          <p className="text-[11px] text-slate-500">Loading…</p>
        ) : count === 0 ? (
          <p className="text-[11px] italic text-slate-400">Nothing waiting.</p>
        ) : (
          <ul className="space-y-1.5">
            {requests!.map((r) => (
              <InboxRequestRow key={r.id} request={r} />
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}

function InboxRequestRow({ request }: { request: TaskRequest }) {
  const fulfill = useFulfillRequest(request.id);
  const reject = useRejectRequest(request.id);
  const [open, setOpen] = useState<'fulfill' | 'reject' | null>(null);
  const [title, setTitle] = useState(request.suggested_title);
  const [description, setDescription] = useState(request.suggested_description ?? '');
  const [priority, setPriority] = useState(0);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const onFulfill = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await fulfill.mutateAsync({
        title: title.trim() || null,
        description: description.trim() || null,
        priority,
      });
      setOpen(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to fulfill');
    }
  };

  const onReject = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await reject.mutateAsync({ reason: reason.trim() || null });
      setOpen(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to reject');
    }
  };

  return (
    <li className="rounded-md border border-amber-200 bg-amber-50/40 p-2 text-[11px]">
      <p className="font-medium text-slate-800">{request.suggested_title}</p>
      <p className="mt-0.5 text-[10px] text-slate-500">
        from {request.requester_name ?? 'unknown'} · {new Date(request.created_at).toLocaleString()}
      </p>
      {request.justification ? (
        <p className="mt-1 whitespace-pre-wrap text-slate-700">{request.justification}</p>
      ) : null}

      {open === 'fulfill' ? (
        <form onSubmit={onFulfill} className="mt-2 space-y-1">
          <input
            type="text"
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Final title for the new task"
            className="w-full rounded border border-slate-300 px-2 py-1 text-[11px]"
          />
          <textarea
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description"
            className="w-full rounded border border-slate-300 px-2 py-1 text-[11px]"
          />
          <input
            type="number"
            value={priority}
            min={0}
            max={1000}
            onChange={(e) => setPriority(Number(e.target.value))}
            placeholder="Priority"
            className="w-24 rounded border border-slate-300 px-2 py-1 text-[11px]"
          />
          {error ? <p className="text-red-600">{error}</p> : null}
          <div className="flex justify-end gap-1">
            <button
              type="button"
              onClick={() => setOpen(null)}
              className="rounded border border-slate-200 px-2 py-0.5 text-[10px] text-slate-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={fulfill.isPending}
              className="rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
            >
              {fulfill.isPending ? 'Fulfilling…' : 'Mint task & link'}
            </button>
          </div>
        </form>
      ) : open === 'reject' ? (
        <form onSubmit={onReject} className="mt-2 space-y-1">
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Optional reason"
            className="w-full rounded border border-slate-300 px-2 py-1 text-[11px]"
          />
          {error ? <p className="text-red-600">{error}</p> : null}
          <div className="flex justify-end gap-1">
            <button
              type="button"
              onClick={() => setOpen(null)}
              className="rounded border border-slate-200 px-2 py-0.5 text-[10px] text-slate-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={reject.isPending}
              className="rounded bg-red-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-red-700 disabled:opacity-60"
            >
              {reject.isPending ? 'Rejecting…' : 'Reject'}
            </button>
          </div>
        </form>
      ) : (
        <div className="mt-1 flex gap-1">
          <button
            type="button"
            onClick={() => setOpen('fulfill')}
            className="rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-emerald-700"
          >
            Fulfill
          </button>
          <button
            type="button"
            onClick={() => setOpen('reject')}
            className="rounded border border-red-200 bg-white px-2 py-0.5 text-[10px] font-medium text-red-700 hover:bg-red-50"
          >
            Reject
          </button>
        </div>
      )}
    </li>
  );
}

function roleRank(role: TeamRole | null): number {
  switch (role) {
    case 'HEAD':
      return 0;
    case 'MANAGER':
      return 1;
    case 'LEAD':
      return 2;
    case 'MEMBER':
      return 3;
    default:
      return 4;
  }
}

function TeamRolePill({ role }: { role: TeamRole | null }) {
  if (role == null) {
    return (
      <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-medium uppercase text-slate-500">
        —
      </span>
    );
  }
  const tone =
    role === 'HEAD'
      ? 'bg-indigo-100 text-indigo-800'
      : role === 'MANAGER'
        ? 'bg-amber-100 text-amber-800'
        : role === 'LEAD'
          ? 'bg-blue-100 text-blue-800'
          : 'bg-slate-100 text-slate-700';
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium uppercase ${tone}`}>
      {role}
    </span>
  );
}

function InviteSection({ isAdmin }: { isAdmin: boolean }) {
  const createInvite = useCreateInvite();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'WORKSPACE_ADMIN' | 'WORKSPACE_MEMBER'>('WORKSPACE_MEMBER');
  const [lastInvite, setLastInvite] = useState<InviteCreateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isAdmin) return null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const invite = await createInvite.mutateAsync({ email, role });
      setLastInvite(invite);
      setEmail('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create invite');
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Invite a member</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Generates a one-time link. Copy and share it via your usual channel — we don&apos;t send
          email yet.
        </p>
      </header>

      <form
        className="grid gap-3 px-4 py-4 sm:grid-cols-[1fr_auto_auto] sm:items-end"
        onSubmit={onSubmit}
      >
        <Field label="Email" htmlFor="invite_email">
          <input
            id="invite_email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="bob@example.com"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>
        <Field label="Role" htmlFor="invite_role">
          <select
            id="invite_role"
            value={role}
            onChange={(e) => setRole(e.target.value as 'WORKSPACE_ADMIN' | 'WORKSPACE_MEMBER')}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="WORKSPACE_MEMBER">Member</option>
            <option value="WORKSPACE_ADMIN">Admin</option>
          </select>
        </Field>
        <button
          type="submit"
          disabled={createInvite.isPending}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {createInvite.isPending ? 'Creating…' : 'Create invite'}
        </button>
      </form>

      {error ? (
        <p role="alert" className="px-4 pb-4 text-sm text-red-600">
          {error}
        </p>
      ) : null}

      {lastInvite ? <InviteLinkReveal invite={lastInvite} /> : null}
    </section>
  );
}

function InviteLinkReveal({ invite }: { invite: InviteCreateResponse }) {
  // Phase 2: stop revealing the raw invite URL in the UI. Once Gmail is
  // wired the api will deliver the link directly to the invitee; for
  // now we just confirm the invite was queued.
  return (
    <div className="border-t border-slate-100 bg-emerald-50/50 px-4 py-3">
      <p className="text-sm font-medium text-emerald-900">
        Invite queued for {invite.email} ({roleLabel(invite.role)}).
      </p>
      <p className="mt-1 text-xs text-emerald-800">
        We&apos;ll email it shortly. The link expires {new Date(invite.expires_at).toLocaleString()}
        .
      </p>
    </div>
  );
}

function MemberRow({ member, isAdmin }: { member: Member; isAdmin: boolean }) {
  const { data: teams } = useTeams();
  const setTeam = useSetMemberTeam();

  const onChangeTeam = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const team_id = e.target.value || null;
    // When picking a team, default the role to MEMBER unless one is
    // already set; clear team_role if the team is unset.
    const team_role = team_id == null ? null : (member.team_role ?? 'MEMBER');
    await setTeam.mutateAsync({
      memberId: member.id,
      payload: { team_id, team_role },
    });
  };

  const onChangeRole = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (member.team_id == null) return; // role makes no sense without a team
    await setTeam.mutateAsync({
      memberId: member.id,
      payload: { team_id: member.team_id, team_role: e.target.value as TeamRole },
    });
  };

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900">{member.name}</p>
        {member.email ? (
          <p className="mt-0.5 truncate text-xs text-slate-500">{member.email}</p>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {member.type === 'AGENT' ? (
          <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-violet-800">
            Agent
          </span>
        ) : null}
        <RolePill role={member.role} />

        {isAdmin ? (
          <>
            <select
              value={member.team_id ?? ''}
              onChange={onChangeTeam}
              disabled={setTeam.isPending}
              className="rounded border border-slate-300 px-1.5 py-0.5 text-[11px]"
            >
              <option value="">— No team —</option>
              {(teams ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            <select
              value={member.team_role ?? ''}
              onChange={onChangeRole}
              disabled={setTeam.isPending || member.team_id == null}
              className="rounded border border-slate-300 px-1.5 py-0.5 text-[11px]"
            >
              <option value="" disabled>
                — Role —
              </option>
              <option value="HEAD">HEAD</option>
              <option value="MANAGER">MANAGER</option>
              <option value="LEAD">LEAD</option>
              <option value="MEMBER">MEMBER</option>
            </select>
          </>
        ) : (
          <TeamRolePill role={member.team_role} />
        )}
      </div>
    </li>
  );
}

const ROLE_PILL: Record<MemberRole, string> = {
  WORKSPACE_OWNER: 'bg-indigo-100 text-indigo-800',
  WORKSPACE_ADMIN: 'bg-blue-100 text-blue-800',
  WORKSPACE_MEMBER: 'bg-slate-100 text-slate-700',
};

function RolePill({ role }: { role: MemberRole }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${ROLE_PILL[role]}`}
    >
      {roleLabel(role)}
    </span>
  );
}

function roleLabel(role: MemberRole): string {
  // Strip the WORKSPACE_ prefix and title-case the rest.
  const tail = role.slice('WORKSPACE_'.length);
  return tail.charAt(0) + tail.slice(1).toLowerCase();
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <ul className="divide-y divide-slate-100">
      {Array.from({ length: count }).map((_, i) => (
        <li key={i} className="px-3 py-3">
          <div className="h-3 w-1/3 animate-pulse rounded bg-slate-100" />
          <div className="mt-2 h-3 w-1/4 animate-pulse rounded bg-slate-100" />
        </li>
      ))}
    </ul>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
      >
        {label}
      </label>
      {children}
    </div>
  );
}
