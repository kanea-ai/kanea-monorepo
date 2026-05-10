'use client';

// Teams page. Phase 5 batch 2 reshape:
// - Invite flow moved to /directory (single home for all "add" flows).
// - Members table moved to /directory; this page is teams-only now.
// - Team rows are dense single-liners; click opens a side drawer with
//   rename + delete (admin) and the team-role editor for assigned
//   members. The drawer's footer links back to /directory.

import Link from 'next/link';
import { useEffect, useMemo, useState, type FormEvent } from 'react';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Modal } from '../../components/Modal';
import {
  ApiError,
  type Member,
  type TaskRequest,
  type TeamRecord,
  type TeamRole,
} from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import {
  useCreateTeam,
  useDeleteTeam,
  useFulfillRequest,
  useMembers,
  useRejectRequest,
  useSetMemberTeam,
  useTeamInboxRequests,
  useTeams,
  useUpdateTeam,
} from '../../lib/queries';

export default function TeamsPage() {
  const principal = useCurrentPrincipal();
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Teams</h1>
          <p className="text-sm text-slate-500">
            Group members under a head, managers, leads, and standard members. Workspace admins can
            create teams and edit assignments.
          </p>
        </div>
        <Link href="/directory" className="text-sm font-medium text-indigo-700 hover:underline">
          People &amp; agents →
        </Link>
      </header>

      <TeamsSection isAdmin={isAdmin} />
    </div>
  );
}

const TEAMS_PAGE_SIZE = 20;

function TeamsSection({ isAdmin }: { isAdmin: boolean }) {
  const { data: teams, isLoading, isError, error } = useTeams();
  const { data: members } = useMembers();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [openTeam, setOpenTeam] = useState<TeamRecord | null>(null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return teams ?? [];
    return (teams ?? []).filter((t) => t.name.toLowerCase().includes(q));
  }, [teams, search]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / TEAMS_PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * TEAMS_PAGE_SIZE, safePage * TEAMS_PAGE_SIZE);

  const membersByTeam = (teamId: string) => (members ?? []).filter((m) => m.team_id === teamId);
  const unassigned = (members ?? []).filter((m) => m.team_id == null);

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Teams</h2>
          <p className="mt-0.5 text-xs text-slate-500">Click a team to manage members and roles.</p>
        </div>
        {isAdmin ? (
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            Create team
          </button>
        ) : null}
      </header>

      <div className="border-b border-slate-100 px-4 py-2">
        <input
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Search teams by name…"
          className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>

      {isError ? (
        <p className="px-4 py-6 text-sm text-red-600">
          Failed to load teams: {(error as Error).message}
        </p>
      ) : isLoading ? (
        <p className="px-4 py-6 text-sm text-slate-500">Loading teams…</p>
      ) : filtered.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm italic text-slate-500">
          {search
            ? 'No teams match your search.'
            : isAdmin
              ? 'No teams yet. Create one above.'
              : 'No teams yet. Ask an admin to create one.'}
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {visible.map((t) => {
            const teamMembers = membersByTeam(t.id);
            return (
              <TeamRow
                key={t.id}
                team={t}
                memberCount={teamMembers.length}
                onOpen={() => setOpenTeam(t)}
              />
            );
          })}
        </ul>
      )}

      {unassigned.length > 0 ? (
        <p className="border-t border-slate-100 bg-slate-50 px-4 py-2 text-[11px] text-slate-500">
          {unassigned.length} member{unassigned.length === 1 ? '' : 's'} not assigned to a team —
          assign them from a team drawer.
        </p>
      ) : null}

      {filtered.length > 0 ? (
        <Paginator
          page={safePage}
          pageCount={pageCount}
          total={filtered.length}
          onChange={setPage}
        />
      ) : null}

      <CreateTeamDialog open={createOpen} onClose={() => setCreateOpen(false)} />

      {openTeam ? (
        <TeamDetailDrawer
          team={openTeam}
          isAdmin={isAdmin}
          members={members ?? []}
          onClose={() => setOpenTeam(null)}
        />
      ) : null}
    </section>
  );
}

function TeamRow({
  team,
  memberCount,
  onOpen,
}: {
  team: TeamRecord;
  memberCount: number;
  onOpen: () => void;
}) {
  // Pending cross-team-request count surfaces inline so admins know
  // there's something to action without opening the drawer.
  const { data: pending } = useTeamInboxRequests(team.id, 'PENDING');
  const pendingCount = pending?.length ?? 0;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left transition-colors hover:bg-slate-50"
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-900">{team.name}</p>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-xs">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
            {memberCount} {memberCount === 1 ? 'member' : 'members'}
          </span>
          {pendingCount > 0 ? (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-800">
              {pendingCount} pending
            </span>
          ) : null}
          <span className="text-slate-400">›</span>
        </div>
      </button>
    </li>
  );
}

function CreateTeamDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateTeam();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName('');
      setError(null);
    }
  }, [open]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({ name: name.trim() });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create team');
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      pending={create.isPending}
      title="Create team"
      subtitle="Pick a short, descriptive name. You can rename later."
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={create.isPending}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="create-team-form"
            disabled={create.isPending || name.trim() === ''}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {create.isPending ? 'Creating…' : 'Create team'}
          </button>
        </>
      }
    >
      <form id="create-team-form" onSubmit={onSubmit} className="space-y-3">
        <div>
          <label
            htmlFor="team_name"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Name
          </label>
          <input
            id="team_name"
            type="text"
            required
            value={name}
            maxLength={120}
            placeholder="Backend"
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}

// ---------- Team detail drawer ----------

function TeamDetailDrawer({
  team,
  isAdmin,
  members,
  onClose,
}: {
  team: TeamRecord;
  isAdmin: boolean;
  members: Member[];
  onClose: () => void;
}) {
  const update = useUpdateTeam();
  const remove = useDeleteTeam();
  const setMemberTeam = useSetMemberTeam();
  const [name, setName] = useState(team.name);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Reset name when a different team is opened.
  useEffect(() => {
    setName(team.name);
    setError(null);
  }, [team.id, team.name]);

  // Escape closes the drawer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !update.isPending && !remove.isPending) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, update.isPending, remove.isPending]);

  const onTeam = members.filter((m) => m.team_id === team.id);
  const ranked = [...onTeam].sort((a, b) => roleRank(a.team_role) - roleRank(b.team_role));

  const onSaveName = async (e: FormEvent) => {
    e.preventDefault();
    if (name.trim() === '' || name.trim() === team.name) return;
    setError(null);
    try {
      await update.mutateAsync({ id: team.id, payload: { name: name.trim() } });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to rename');
    }
  };

  const onDelete = async () => {
    setError(null);
    try {
      await remove.mutateAsync(team.id);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to delete');
    }
  };

  return (
    <>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Team ${team.name}`}
        className="fixed inset-0 z-40 flex justify-end bg-slate-900/30"
        onClick={() => {
          if (!update.isPending && !remove.isPending) onClose();
        }}
      >
        <aside
          className="flex h-full w-full max-w-md flex-col overflow-hidden bg-white shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                Team
              </p>
              <h2 className="truncate text-base font-semibold text-slate-900">{team.name}</h2>
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

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {isAdmin ? (
              <form onSubmit={onSaveName} className="mb-5 space-y-2">
                <label
                  htmlFor="team_drawer_name"
                  className="block text-xs font-medium uppercase tracking-wide text-slate-600"
                >
                  Rename
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id="team_drawer_name"
                    type="text"
                    required
                    value={name}
                    maxLength={120}
                    onChange={(e) => setName(e.target.value)}
                    className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  <button
                    type="submit"
                    disabled={update.isPending || name.trim() === '' || name.trim() === team.name}
                    className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {update.isPending ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </form>
            ) : null}

            <div className="mb-3 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-slate-900">
                Members
                <span className="ml-1.5 text-xs font-normal text-slate-500">({onTeam.length})</span>
              </h3>
              <Link
                href="/directory"
                className="text-xs font-medium text-indigo-700 hover:underline"
              >
                Manage in Directory →
              </Link>
            </div>

            {ranked.length === 0 ? (
              <p className="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-xs italic text-slate-500">
                No members yet.{' '}
                {isAdmin ? 'Pick people from the Unassigned list below.' : 'Ask an admin.'}
              </p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {ranked.map((m) => (
                  <DrawerMemberRow
                    key={m.id}
                    member={m}
                    isAdmin={isAdmin}
                    onChangeRole={async (role) => {
                      await setMemberTeam.mutateAsync({
                        memberId: m.id,
                        payload: { team_id: team.id, team_role: role },
                      });
                    }}
                    onRemove={async () => {
                      await setMemberTeam.mutateAsync({
                        memberId: m.id,
                        payload: { team_id: null, team_role: null },
                      });
                    }}
                    pending={setMemberTeam.isPending}
                  />
                ))}
              </ul>
            )}

            {isAdmin ? (
              <UnassignedSection
                team={team}
                members={members}
                pending={setMemberTeam.isPending}
                onAssign={async (memberId) => {
                  await setMemberTeam.mutateAsync({
                    memberId,
                    payload: { team_id: team.id, team_role: 'MEMBER' },
                  });
                }}
              />
            ) : null}

            <TeamInboxBlock teamId={team.id} />

            {error ? (
              <p role="alert" className="mt-4 text-sm text-red-600">
                {error}
              </p>
            ) : null}
          </div>

          {isAdmin ? (
            <footer className="border-t border-slate-200 bg-slate-50 px-5 py-3">
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                disabled={remove.isPending}
                className="w-full rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
              >
                {remove.isPending ? 'Deleting…' : 'Delete team'}
              </button>
            </footer>
          ) : null}
        </aside>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete "${team.name}"?`}
        message="Members on this team are unassigned but kept. Tasks owned by the team are unlinked, not deleted."
        confirmLabel="Delete team"
        pending={remove.isPending}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={async () => {
          await onDelete();
          setConfirmDelete(false);
        }}
      />
    </>
  );
}

function DrawerMemberRow({
  member,
  isAdmin,
  onChangeRole,
  onRemove,
  pending,
}: {
  member: Member;
  isAdmin: boolean;
  onChangeRole: (role: TeamRole) => Promise<void>;
  onRemove: () => Promise<void>;
  pending: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-2 py-2 text-sm">
      <div className="min-w-0">
        <p className="truncate font-medium text-slate-900">
          {member.name}
          {member.type === 'AGENT' ? (
            <span className="ml-1.5 rounded bg-violet-100 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-violet-700">
              Agent
            </span>
          ) : null}
        </p>
        {member.email ? (
          <p className="mt-0.5 truncate text-xs text-slate-500">{member.email}</p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {isAdmin ? (
          <>
            <select
              value={member.team_role ?? 'MEMBER'}
              disabled={pending}
              onChange={(e) => onChangeRole(e.target.value as TeamRole)}
              className="rounded border border-slate-300 px-1.5 py-0.5 text-[11px]"
            >
              <option value="HEAD">HEAD</option>
              <option value="MANAGER">MANAGER</option>
              <option value="LEAD">LEAD</option>
              <option value="MEMBER">MEMBER</option>
            </select>
            <button
              type="button"
              disabled={pending}
              onClick={onRemove}
              aria-label={`Remove ${member.name} from team`}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-red-600 disabled:opacity-40"
            >
              ✕
            </button>
          </>
        ) : (
          <TeamRolePill role={member.team_role} />
        )}
      </div>
    </li>
  );
}

function UnassignedSection({
  team,
  members,
  onAssign,
  pending,
}: {
  team: TeamRecord;
  members: Member[];
  onAssign: (memberId: string) => Promise<void>;
  pending: boolean;
}) {
  const unassigned = members.filter((m) => m.team_id == null && m.type === 'HUMAN');
  if (unassigned.length === 0) {
    return (
      <p className="mt-4 text-[11px] italic text-slate-400">
        Everyone in the workspace is already on a team.
      </p>
    );
  }
  return (
    <div className="mt-5 rounded-md border border-dashed border-slate-200 p-3">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        Unassigned humans
      </p>
      <ul className="space-y-1">
        {unassigned.map((m) => (
          <li key={m.id} className="flex items-center justify-between text-xs">
            <span className="truncate text-slate-800">{m.name}</span>
            <button
              type="button"
              disabled={pending}
              onClick={() => onAssign(m.id)}
              className="rounded border border-indigo-200 bg-white px-2 py-0.5 font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
            >
              Add to {team.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TeamInboxBlock({ teamId }: { teamId: string }) {
  const { data: requests, isLoading } = useTeamInboxRequests(teamId, 'PENDING');
  const count = requests?.length ?? 0;

  return (
    <section className="mt-5 rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-xs font-semibold text-slate-900">Cross-team requests</h3>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
          {count} pending
        </span>
      </div>
      {isLoading ? (
        <p className="text-[11px] text-slate-500">Loading…</p>
      ) : count === 0 ? (
        <p className="text-[11px] italic text-slate-500">Nothing to action.</p>
      ) : (
        <ul className="space-y-2">
          {(requests ?? []).map((r) => (
            <InboxRequestRow key={r.id} request={r} />
          ))}
        </ul>
      )}
    </section>
  );
}

function InboxRequestRow({ request }: { request: TaskRequest }) {
  const fulfill = useFulfillRequest(request.id);
  const reject = useRejectRequest(request.id);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const onFulfill = async () => {
    setError(null);
    try {
      await fulfill.mutateAsync({});
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to fulfill');
    }
  };

  const onReject = async () => {
    setError(null);
    try {
      await reject.mutateAsync({ reason: reason.trim() || null });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to reject');
    }
  };

  return (
    <li className="rounded-md border border-slate-200 bg-white p-2 text-[12px]">
      <p className="font-medium text-slate-900">{request.suggested_title}</p>
      {request.justification ? (
        <p className="mt-0.5 line-clamp-2 text-[11px] text-slate-600">{request.justification}</p>
      ) : null}
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={onFulfill}
          disabled={fulfill.isPending || reject.isPending}
          className="rounded-md bg-emerald-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          Accept
        </button>
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reject reason (optional)"
          className="flex-1 rounded border border-slate-300 px-2 py-1 text-[11px]"
        />
        <button
          type="button"
          onClick={onReject}
          disabled={fulfill.isPending || reject.isPending}
          className="rounded-md border border-red-200 bg-white px-2 py-1 text-[11px] font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
        >
          Reject
        </button>
      </div>
      {error ? (
        <p role="alert" className="mt-1 text-[11px] text-red-600">
          {error}
        </p>
      ) : null}
    </li>
  );
}

function Paginator({
  page,
  pageCount,
  total,
  onChange,
}: {
  page: number;
  pageCount: number;
  total: number;
  onChange: (next: number) => void;
}) {
  if (pageCount <= 1) {
    return (
      <div className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
        {total} {total === 1 ? 'team' : 'teams'}
      </div>
    );
  }
  const start = (page - 1) * 20 + 1;
  const end = Math.min(page * 20, total);
  return (
    <div className="flex items-center justify-between gap-2 border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
      <span>
        Showing {start}–{end} of {total}
      </span>
      <nav className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="rounded border border-slate-200 px-2 py-0.5 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          ‹
        </button>
        {Array.from({ length: pageCount }).map((_, i) => {
          const n = i + 1;
          const isCurrent = n === page;
          return (
            <button
              key={n}
              type="button"
              onClick={() => onChange(n)}
              className={`rounded px-2 py-0.5 ${
                isCurrent
                  ? 'bg-indigo-600 text-white'
                  : 'border border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {n}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => onChange(Math.min(pageCount, page + 1))}
          disabled={page === pageCount}
          className="rounded border border-slate-200 px-2 py-0.5 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          ›
        </button>
      </nav>
    </div>
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
