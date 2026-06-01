'use client';

// Teams page. Phase 5 batch 2 reshape:
// - Invite flow moved to /directory (single home for all "add" flows).
// - Members table moved to /directory; this page is teams-only now.
// - Team rows are dense single-liners; click opens a side drawer with
//   rename + delete (admin) and the team-role editor for assigned
//   members. The drawer's footer links back to /directory.

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState, type FormEvent } from 'react';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { EditToolbar } from '../../components/EditToolbar';
import { Modal } from '../../components/Modal';
import { Pagination } from '../../components/Pagination';
import {
  findSittingRoleHolder,
  RoleReplacementConfirm,
  type RoleReplacementContext,
} from '../../components/RoleReplacementConfirm';
import {
  ApiError,
  type Department,
  type Member,
  type RequestStatus,
  type TaskRequest,
  type TeamRecord,
  type TeamRole,
} from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import { departmentHref, userHref } from '../../lib/links';
import {
  canEditTeam,
  disabledEditTooltip,
  nearestEditors,
  TEAM_REACH_PRIORITY,
} from '../../lib/permissions';
import {
  useCreateTeam,
  useDeleteTeam,
  useDepartments,
  useMembers,
  useSetMemberTeam,
  useTeamInboxRequests,
  useTeams,
  useUpdateTeam,
} from '../../lib/queries';

export default function TeamsPage() {
  const principal = useCurrentPrincipal();
  // Two gates live on this page:
  //   - isAdmin: workspace OWNER / ADMIN — controls the Create button
  //     and the member-roster management inside the drawer (assign,
  //     change team_role, remove). Those have always been admin-only.
  //   - teamReach: priority-gated reach (≤ TEAM_REACH_PRIORITY) —
  //     controls the team-metadata Edit toggle introduced in Task 3.
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';
  const teamReach = canEditTeam(principal);

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

      <TeamsSection isAdmin={isAdmin} teamReach={teamReach} />
    </div>
  );
}

const TEAMS_PAGE_SIZE = 20;

function TeamsSection({ isAdmin, teamReach }: { isAdmin: boolean; teamReach: boolean }) {
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState('');
  // 'all' = show every team, '' (empty string) = unfiled-only, else
  // a specific department id. Stored in state so the dropdown sticks
  // around while the user pages.
  const [departmentFilter, setDepartmentFilter] = useState<string>('all');
  const [page, setPage] = useState(1);
  const [openTeam, setOpenTeam] = useState<TeamRecord | null>(null);

  // Server-side pagination on the team list. ``departmentFilter`` is
  // forwarded to the api when it picks a specific department; the
  // 'all' / '' (unfiled) modes stay client-side because the api
  // doesn't have a "where department_id IS NULL" filter today.
  // ``search`` is also client-side narrowing on the page slice —
  // good enough for typical workspaces where the page covers most
  // teams; we can promote it to a query param later.
  const teamsQueryDept =
    departmentFilter !== '' && departmentFilter !== 'all' ? departmentFilter : undefined;
  const {
    data: teamsPage,
    isLoading,
    isError,
    error,
  } = useTeams({
    departmentId: teamsQueryDept,
    skip: (page - 1) * TEAMS_PAGE_SIZE,
    limit: TEAMS_PAGE_SIZE,
  });
  const teams = teamsPage?.items ?? [];
  // total reflects the *server-side* filter (department_id when set);
  // client-side search/unfiled trimming below shrinks ``filtered``
  // but the Pagination control still uses the server total — that's
  // the right call when the search is narrowing-only-on-this-page.
  const total = teamsPage?.total ?? 0;

  const { data: membersPage } = useMembers();
  const members = membersPage?.items ?? [];
  const { data: departmentsPage } = useDepartments();
  const departments = departmentsPage?.items ?? [];

  // Deep link: ?open=<team_id> opens that team's drawer once the
  // list arrives. Used by /audit when an admin clicks a TEAM-typed
  // audit row. Strip the param after consuming it so reload doesn't
  // keep re-opening.
  const searchParams = useSearchParams();
  const router = useRouter();
  const requestedOpen = searchParams.get('open');
  useEffect(() => {
    if (!requestedOpen) return;
    const match = teams.find((t) => t.id === requestedOpen);
    if (match) {
      setOpenTeam(match);
      router.replace('/teams');
    }
  }, [requestedOpen, teams, router]);

  const departmentsById = useMemo(() => {
    const map = new Map<string, Department>();
    for (const d of departments) map.set(d.id, d);
    return map;
  }, [departments]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = teams;
    if (departmentFilter === '') {
      rows = rows.filter((t) => t.department_id == null);
    }
    if (q) rows = rows.filter((t) => t.name.toLowerCase().includes(q));
    return rows;
  }, [teams, search, departmentFilter]);

  const membersByTeam = (teamId: string) => members.filter((m) => m.team_id === teamId);
  const unassigned = members.filter((m) => m.team_id == null);

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

      <div className="flex flex-col gap-2 border-b border-slate-100 px-4 py-2 sm:flex-row">
        <input
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Search teams by name…"
          className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <select
          value={departmentFilter}
          onChange={(e) => {
            setDepartmentFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="all">All departments</option>
          <option value="">Unfiled (no department)</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
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
          {filtered.map((t) => {
            const teamMembers = membersByTeam(t.id);
            return (
              <TeamRow
                key={t.id}
                team={t}
                memberCount={teamMembers.length}
                department={t.department_id ? (departmentsById.get(t.department_id) ?? null) : null}
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

      <Pagination page={page} pageSize={TEAMS_PAGE_SIZE} total={total} onChange={setPage} />

      <CreateTeamDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        departments={departments}
      />

      {openTeam ? (
        <TeamDetailDrawer
          /* After PATCH /teams/{id} the cache is refreshed; ``teams``
             carries the new row but our local ``openTeam`` captured
             the snapshot at click-time. Re-resolve from the list so
             the drawer always renders the latest version (e.g. the
             department field after a Save). Falls back to ``openTeam``
             during the brief window where the list refetch is in
             flight. */
          team={teams.find((t) => t.id === openTeam.id) ?? openTeam}
          isAdmin={isAdmin}
          teamReach={teamReach}
          members={members}
          departments={departments}
          onClose={() => setOpenTeam(null)}
        />
      ) : null}
    </section>
  );
}

function TeamRow({
  team,
  memberCount,
  department,
  onOpen,
}: {
  team: TeamRecord;
  memberCount: number;
  department: Department | null;
  onOpen: () => void;
}) {
  // Incoming-request count surfaces inline so admins know there's
  // something to look at without opening the drawer. Counts all
  // statuses (the default) — under the auto-fulfilment model in
  // production, new rows are born FULFILLED, so a 'PENDING' filter
  // would silently show 0 even when there's real recent activity.
  const { data: pending } = useTeamInboxRequests(team.id);
  const pendingCount = pending?.length ?? 0;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-medium text-slate-900">{team.name}</p>
            {department ? (
              <span className="shrink-0 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-indigo-700">
                {department.name}
              </span>
            ) : null}
          </div>
          {team.description ? (
            <p className="mt-0.5 line-clamp-2 text-xs text-slate-600">{team.description}</p>
          ) : (
            <p className="mt-0.5 text-xs italic text-slate-400">No description.</p>
          )}
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

function CreateTeamDialog({
  open,
  onClose,
  departments,
}: {
  open: boolean;
  onClose: () => void;
  departments: Department[];
}) {
  const create = useCreateTeam();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [departmentId, setDepartmentId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
      setDepartmentId('');
      setError(null);
    }
  }, [open]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({
        name: name.trim(),
        description: description.trim() || null,
        department_id: departmentId || null,
      });
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
      subtitle="Pick a short, descriptive name. Description and department are optional."
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
        <div>
          <label
            htmlFor="team_description"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Description
          </label>
          <textarea
            id="team_description"
            value={description}
            rows={3}
            maxLength={20_000}
            placeholder="What this team is responsible for."
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label
            htmlFor="team_department"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Department
          </label>
          <select
            id="team_department"
            value={departmentId}
            onChange={(e) => setDepartmentId(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">No department (file later)</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
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
  teamReach,
  members,
  departments,
  onClose,
}: {
  team: TeamRecord;
  isAdmin: boolean;
  /** Priority-gated reach (≤ TEAM_REACH_PRIORITY) — drives the team
   *  metadata Edit toggle. Distinct from isAdmin, which still gates
   *  the member-roster actions inside the drawer. */
  teamReach: boolean;
  members: Member[];
  departments: Department[];
  onClose: () => void;
}) {
  const update = useUpdateTeam();
  const remove = useDeleteTeam();
  const setMemberTeam = useSetMemberTeam();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(team.name);
  const [description, setDescription] = useState(team.description ?? '');
  const [departmentId, setDepartmentId] = useState<string>(team.department_id ?? '');
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Reset when a different team is opened.
  useEffect(() => {
    setName(team.name);
    setDescription(team.description ?? '');
    setDepartmentId(team.department_id ?? '');
    setEditing(false);
    setError(null);
  }, [team.id, team.name, team.description, team.department_id]);

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

  const trimmedName = name.trim();
  const trimmedDesc = description.trim();
  const nameChanged = trimmedName !== team.name && trimmedName !== '';
  const descChanged = trimmedDesc !== (team.description ?? '');
  // department_id select stores '' for "no department"; the api takes
  // null to mean the same. Both clear the FK.
  const newDept = departmentId === '' ? null : departmentId;
  const deptChanged = newDept !== team.department_id;
  const dirty = nameChanged || descChanged || deptChanged;

  const onSaveDetails = async () => {
    setError(null);
    if (!dirty) {
      setEditing(false);
      return;
    }
    try {
      await update.mutateAsync({
        id: team.id,
        payload: {
          ...(nameChanged ? { name: trimmedName } : {}),
          ...(descChanged ? { description: trimmedDesc === '' ? null : trimmedDesc } : {}),
          ...(deptChanged ? { department_id: newDept } : {}),
        },
      });
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save');
    }
  };

  const onCancelEdit = () => {
    setName(team.name);
    setDescription(team.description ?? '');
    setDepartmentId(team.department_id ?? '');
    setError(null);
    setEditing(false);
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

  // Smart-tooltip context — the nearest authorised editor for THIS
  // team. Falls back to "ask a workspace admin" when neither the
  // team Manager nor the Dept Head is set.
  const editors = nearestEditors({
    teamId: team.id,
    departmentId: team.department_id,
    members,
    departments,
  });
  const editTooltip = disabledEditTooltip(editors);

  // Role-replacement intercept. When admin changes a sitting member's
  // role to MANAGER (or LEAD) and someone ELSE already holds that
  // slot, we surface a confirm modal naming the displaced holder.
  // ``pendingRoleChange`` is the modal context plus the closure that
  // commits the PATCH once the admin confirms.
  const [pendingRoleChange, setPendingRoleChange] = useState<{
    context: RoleReplacementContext;
    commit: () => Promise<void>;
  } | null>(null);

  const requestRoleChange = async (target: Member, role: TeamRole) => {
    const commit = async () => {
      await setMemberTeam.mutateAsync({
        memberId: target.id,
        payload: { team_id: team.id, team_role: role },
      });
    };
    if (role === 'MANAGER' || role === 'LEAD') {
      const sitting = findSittingRoleHolder(members, team.id, role, target.id);
      if (sitting !== null) {
        setPendingRoleChange({
          context: {
            teamName: team.name,
            role,
            sittingHolder: sitting,
            newHolderName: target.name,
          },
          commit,
        });
        return;
      }
    }
    await commit();
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
            <section className="mb-5 space-y-3">
              <EditToolbar
                editing={editing}
                canEdit={teamReach}
                disabledReason={editTooltip}
                onEdit={() => setEditing(true)}
                onCancel={onCancelEdit}
                onSave={onSaveDetails}
                dirty={dirty}
                saving={update.isPending}
                saveLabel="Save changes"
              />

              {editing ? (
                <div className="space-y-3 rounded-md border border-indigo-100 bg-indigo-50/40 px-3 py-3">
                  <div>
                    <label
                      htmlFor="team_drawer_name"
                      className="block text-xs font-medium uppercase tracking-wide text-slate-600"
                    >
                      Name
                    </label>
                    <input
                      id="team_drawer_name"
                      type="text"
                      required
                      value={name}
                      maxLength={120}
                      onChange={(e) => setName(e.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="team_drawer_description"
                      className="block text-xs font-medium uppercase tracking-wide text-slate-600"
                    >
                      Description
                    </label>
                    <textarea
                      id="team_drawer_description"
                      rows={3}
                      value={description}
                      maxLength={20_000}
                      placeholder="What this team is responsible for."
                      onChange={(e) => setDescription(e.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="team_drawer_department"
                      className="block text-xs font-medium uppercase tracking-wide text-slate-600"
                    >
                      Department
                    </label>
                    <select
                      id="team_drawer_department"
                      value={departmentId}
                      onChange={(e) => setDepartmentId(e.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="">No department</option>
                      {departments.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : (
                <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      Name
                    </p>
                    <p className="mt-1 text-sm text-slate-800">{team.name}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      Description
                    </p>
                    <p className="mt-1 text-sm text-slate-800">
                      {team.description ? (
                        team.description
                      ) : (
                        <span className="italic text-slate-500">No description.</span>
                      )}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      Department
                    </p>
                    <p className="mt-1 text-sm text-slate-800">
                      {team.department_id ? (
                        <Link
                          href={departmentHref(team.department_id)}
                          className="text-slate-800 hover:text-indigo-700 hover:underline"
                        >
                          {departments.find((d) => d.id === team.department_id)?.name ?? '—'}
                        </Link>
                      ) : (
                        <span className="italic text-slate-500">Unfiled.</span>
                      )}
                    </p>
                  </div>
                </div>
              )}
            </section>

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
                    onChangeRole={(role) => requestRoleChange(m, role)}
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
              <AddMembersSection
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

          {teamReach ? (
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

      <RoleReplacementConfirm
        context={pendingRoleChange?.context ?? null}
        pending={setMemberTeam.isPending}
        onCancel={() => setPendingRoleChange(null)}
        onConfirm={async () => {
          if (!pendingRoleChange) return;
          await pendingRoleChange.commit();
          setPendingRoleChange(null);
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
          <Link
            href={userHref(member.id)}
            className="text-slate-900 hover:text-indigo-700 hover:underline"
          >
            {member.name}
          </Link>
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

function AddMembersSection({
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
  // Anyone in the workspace who isn't already on THIS team is fair
  // game. That includes humans/agents on other teams — moving someone
  // across teams is a one-click action; the previous "unassigned only"
  // list missed that flow entirely.
  const candidates = members.filter((m) => m.team_id !== team.id);
  const [search, setSearch] = useState('');
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = q ? candidates.filter((m) => m.name.toLowerCase().includes(q)) : candidates;
    // Show unassigned first, then alphabetical inside each group.
    return [...rows].sort((a, b) => {
      const aFree = a.team_id == null ? 0 : 1;
      const bFree = b.team_id == null ? 0 : 1;
      if (aFree !== bFree) return aFree - bFree;
      return a.name.localeCompare(b.name);
    });
  }, [candidates, search]);

  if (candidates.length === 0) {
    return (
      <p className="mt-4 text-[11px] italic text-slate-400">
        Everyone in the workspace is already on this team.
      </p>
    );
  }

  return (
    <div className="mt-5 rounded-md border border-dashed border-slate-200 p-3">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        Add members
      </p>
      <input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search…"
        className="mb-2 w-full rounded-md border border-slate-300 px-2 py-1 text-xs shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      />
      <ul className="max-h-48 space-y-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <li className="text-[11px] italic text-slate-400">No matches.</li>
        ) : (
          filtered.map((m) => {
            const onOther = m.team_id != null;
            return (
              <li key={m.id} className="flex items-center justify-between text-xs">
                <span className="min-w-0 truncate text-slate-800">
                  {m.name}
                  {m.type === 'AGENT' ? (
                    <span className="ml-1 rounded bg-violet-100 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-violet-700">
                      Agent
                    </span>
                  ) : null}
                  {onOther ? (
                    <span className="ml-1 text-[10px] italic text-slate-500">
                      (was on another team)
                    </span>
                  ) : null}
                </span>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => onAssign(m.id)}
                  className="ml-2 shrink-0 rounded border border-indigo-200 bg-white px-2 py-0.5 font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                >
                  {onOther ? 'Move' : 'Add'}
                </button>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}

function TeamInboxBlock({ teamId }: { teamId: string }) {
  // Default direction is incoming (other teams asking us); show all
  // statuses. The per-row badge surfaces FULFILLED vs PENDING vs
  // REJECTED so the reader can scan recent activity without a chip
  // filter (deferred to follow-up).
  const { data: requests, isLoading } = useTeamInboxRequests(teamId);
  const count = requests?.length ?? 0;

  return (
    <section className="mt-5 rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-xs font-semibold text-slate-900">Cross-team requests</h3>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
          {count} incoming
        </span>
      </div>
      {isLoading ? (
        <p className="text-[11px] text-slate-500">Loading…</p>
      ) : count === 0 ? (
        <p className="text-[11px] italic text-slate-500">No incoming requests.</p>
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

function StatusBadge({ status }: { status: RequestStatus }) {
  const tone =
    status === 'PENDING'
      ? 'bg-amber-100 text-amber-800'
      : status === 'FULFILLED'
        ? 'bg-emerald-100 text-emerald-800'
        : 'bg-slate-200 text-slate-700';
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${tone}`}
    >
      {status}
    </span>
  );
}

function InboxRequestRow({ request }: { request: TaskRequest }) {
  // Pure visibility: title + status badge + requester + a link to the
  // auto-minted task. No approval controls — under Model 1 the inbox's
  // job is "make the request visible," not "approve it." Whether the
  // target team should be able to reject after the fact is the product
  // question tracked in #50; this branch deliberately does not
  // prejudge that decision by shipping dormant approval UI.
  return (
    <li className="rounded-md border border-slate-200 bg-white p-2 text-[12px]">
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-slate-900">{request.suggested_title}</p>
        <StatusBadge status={request.status} />
      </div>
      {request.justification ? (
        <p className="mt-0.5 line-clamp-2 text-[11px] text-slate-600">{request.justification}</p>
      ) : null}
      {request.requester_name ? (
        <p className="mt-0.5 text-[10px] text-slate-500">From {request.requester_name}</p>
      ) : null}
      {request.fulfilled_task_id ? (
        <p className="mt-1 text-[10px]">
          <Link
            href={`/tasks/${request.fulfilled_task_id}`}
            className="text-indigo-700 underline-offset-2 hover:underline"
          >
            View the task →
          </Link>
        </p>
      ) : null}
    </li>
  );
}

function roleRank(role: TeamRole | null): number {
  switch (role) {
    case 'MANAGER':
      return 0;
    case 'LEAD':
      return 1;
    case 'MEMBER':
      return 2;
    default:
      return 3;
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
    role === 'MANAGER'
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
