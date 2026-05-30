'use client';

// Departments view. Department is an organisational tag that sits one
// level above Teams: a Department holds zero-or-more Teams via the
// optional teams.department_id FK. Anyone in the workspace can see
// the directory; only OWNER/ADMIN can create / rename / delete (the
// api enforces it; the UI hides the controls so the buttons don't
// look broken to non-admins).

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState, type FormEvent } from 'react';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { EditToolbar } from '../../components/EditToolbar';
import { Modal } from '../../components/Modal';
import { Pagination } from '../../components/Pagination';
import { ApiError, type Department, type Member, type TeamRecord } from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import { teamHref, userHref } from '../../lib/links';
import {
  canEditDepartment,
  DEPARTMENT_REACH_PRIORITY,
  disabledDepartmentEditTooltip,
} from '../../lib/permissions';
import {
  useCreateDepartment,
  useDeleteDepartment,
  useDepartments,
  useMembers,
  useTeams,
  useUpdateDepartment,
} from '../../lib/queries';

const PAGE_SIZE = 25;

export default function DepartmentsPage() {
  const principal = useCurrentPrincipal();
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  // The api accepts a server-side ``name`` filter; we forward it AND
  // also do a tiny client-side narrowing so typing feels instant. The
  // ``name`` query keeps the page slice small even when the server
  // round-trip is in flight.
  const {
    data: departmentsPage,
    isLoading,
    isError,
    error,
  } = useDepartments({
    name: search.trim() || undefined,
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  });
  const departments = departmentsPage?.items ?? [];
  const total = departmentsPage?.total ?? 0;

  // Teams are fetched all at once (default MAX_PAGE_SIZE) so the
  // departments view can group them under each card without paging
  // through the teams list separately.
  const { data: teamsPage } = useTeams();
  const teams = teamsPage?.items ?? [];

  // Human members feed the per-team MANAGER pill rendered next to each
  // team in a department's roster. Single workspace-scoped read; the
  // managers map below folds it into a {team_id -> Member} lookup so
  // the row + drawer share the same source.
  const { data: membersPage } = useMembers({ humansOnly: true });
  const managersByTeam = useMemo(() => {
    const map = new Map<string, Member>();
    for (const m of membersPage?.items ?? []) {
      if (m.team_id && m.team_role === 'MANAGER') map.set(m.team_id, m);
    }
    return map;
  }, [membersPage]);

  const [openDept, setOpenDept] = useState<Department | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  // Deep link: ?open=<dept_id> opens that department's drawer once
  // the list arrives. Used by /audit when an admin clicks a
  // DEPARTMENT-typed audit row. We strip the param after consuming
  // it so reload doesn't keep re-opening.
  const searchParams = useSearchParams();
  const router = useRouter();
  const requestedOpen = searchParams.get('open');
  useEffect(() => {
    if (!requestedOpen) return;
    const match = departments.find((d) => d.id === requestedOpen);
    if (match) {
      setOpenDept(match);
      router.replace('/departments');
    }
  }, [requestedOpen, departments, router]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return departments;
    return departments.filter((d) => d.name.toLowerCase().includes(q));
  }, [departments, search]);

  const teamsByDept = useMemo(() => {
    const map = new Map<string, TeamRecord[]>();
    for (const t of teams) {
      if (!t.department_id) continue;
      const list = map.get(t.department_id) ?? [];
      list.push(t);
      map.set(t.department_id, list);
    }
    return map;
  }, [teams]);

  const unfiledTeams = teams.filter((t) => !t.department_id);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Departments</h1>
          <p className="text-sm text-slate-500">
            Group teams into departments to mirror your org chart. Departments are organisational
            tags only — permissions still flow through workspace role and team role.
          </p>
        </div>
        <Link href="/teams" className="text-sm font-medium text-indigo-700 hover:underline">
          Manage teams →
        </Link>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">All departments</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Click a department to see its teams or edit it.
            </p>
          </div>
          {isAdmin ? (
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
            >
              Create department
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
            placeholder="Search departments by name…"
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        {isError ? (
          <p className="px-4 py-6 text-sm text-red-600">
            Failed to load departments: {(error as Error).message}
          </p>
        ) : isLoading ? (
          <p className="px-4 py-6 text-sm text-slate-500">Loading departments…</p>
        ) : filtered.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm italic text-slate-500">
            {search
              ? 'No departments match your search.'
              : isAdmin
                ? 'No departments yet. Create one above.'
                : 'No departments yet. Ask an admin to create one.'}
          </p>
        ) : (
          <>
            <ul className="divide-y divide-slate-100">
              {filtered.map((d) => (
                <DepartmentRow
                  key={d.id}
                  department={d}
                  teams={teamsByDept.get(d.id) ?? []}
                  managersByTeam={managersByTeam}
                  onOpen={() => setOpenDept(d)}
                />
              ))}
            </ul>
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
          </>
        )}

        {unfiledTeams.length > 0 ? (
          <p className="border-t border-slate-100 bg-slate-50 px-4 py-2 text-[11px] text-slate-500">
            {unfiledTeams.length} team{unfiledTeams.length === 1 ? '' : 's'} not yet filed under a
            department — file them from each team&apos;s drawer in{' '}
            <Link href="/teams" className="font-medium text-indigo-700 hover:underline">
              Teams
            </Link>
            .
          </p>
        ) : null}
      </section>

      <CreateDepartmentDialog open={createOpen} onClose={() => setCreateOpen(false)} />

      {openDept ? (
        <DepartmentDetailDrawer
          /* Re-resolve from the live ``departments`` cache so the
             drawer instantly reflects an edit (head change, rename,
             etc.) rather than holding the click-time snapshot.
             Falls back to the captured value during the brief window
             where the post-PATCH refetch is in flight. */
          department={departments.find((d) => d.id === openDept.id) ?? openDept}
          canEdit={canEditDepartment(principal)}
          teams={teamsByDept.get(openDept.id) ?? []}
          managersByTeam={managersByTeam}
          onClose={() => setOpenDept(null)}
        />
      ) : null}
    </div>
  );
}

function DepartmentRow({
  department,
  teams,
  managersByTeam,
  onOpen,
}: {
  department: Department;
  teams: TeamRecord[];
  managersByTeam: Map<string, Member>;
  onOpen: () => void;
}) {
  return (
    <li>
      {/* Row is a clickable container, not a <button>, so the nested
          user / team links below render valid HTML (anchors inside a
          button is not a permitted nesting). Same click + keyboard
          behaviour via role + onKeyDown. */}
      <div
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onOpen();
          }
        }}
        className="flex w-full cursor-pointer items-start justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900">{department.name}</p>
          {/* Head — prominent: avatar + name (clickable user link),
              amber Head badge. Empty-state placeholder keeps the
              column predictable. */}
          <div className="mt-1 flex items-center gap-2">
            {department.head ? (
              <>
                <AvatarCircle name={department.head.name} tone="amber" />
                <Link
                  href={userHref(department.head.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="text-xs font-medium text-slate-800 hover:text-indigo-700 hover:underline"
                >
                  {department.head.name}
                </Link>
                <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
                  Head
                </span>
              </>
            ) : (
              <>
                <AvatarCircle name="?" tone="muted" />
                <span className="text-xs italic text-slate-400">No head assigned</span>
              </>
            )}
          </div>
          {department.description ? (
            <p className="mt-1 line-clamp-2 text-xs text-slate-600">{department.description}</p>
          ) : null}
          {teams.length > 0 ? (
            <ul className="mt-2 space-y-1">
              {teams.slice(0, 4).map((t) => (
                <li key={t.id} className="flex items-center gap-2 text-[11px] text-slate-600">
                  <span className="font-medium text-slate-800">{t.name}</span>
                  <TeamManagerBadge manager={managersByTeam.get(t.id) ?? null} />
                </li>
              ))}
              {teams.length > 4 ? (
                <li className="text-[11px] italic text-slate-500">
                  +{teams.length - 4} more team{teams.length - 4 === 1 ? '' : 's'}
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
            {teams.length} {teams.length === 1 ? 'team' : 'teams'}
          </span>
          <span className="text-slate-400">›</span>
        </div>
      </div>
    </li>
  );
}

function AvatarCircle({
  name,
  tone = 'slate',
}: {
  name: string;
  tone?: 'amber' | 'slate' | 'muted';
}) {
  const initials = (name || '?')
    .split(/\s+/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();
  const cls =
    tone === 'amber'
      ? 'bg-amber-100 text-amber-800'
      : tone === 'muted'
        ? 'bg-slate-100 text-slate-400'
        : 'bg-slate-200 text-slate-700';
  return (
    <span
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${cls}`}
      aria-hidden
    >
      {initials || '?'}
    </span>
  );
}

function TeamManagerBadge({ manager }: { manager: Member | null }) {
  if (!manager) {
    return <span className="text-[10px] italic text-slate-400">— no manager —</span>;
  }
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-slate-600">
      <AvatarCircle name={manager.name} />
      <Link
        href={userHref(manager.id)}
        onClick={(e) => e.stopPropagation()}
        className="font-medium hover:text-indigo-700 hover:underline"
      >
        {manager.name}
      </Link>
      <span className="rounded bg-indigo-50 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-indigo-700">
        Manager
      </span>
    </span>
  );
}

function CreateDepartmentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateDepartment();
  const { data: membersPage } = useMembers({ humansOnly: true });
  const members = membersPage?.items ?? [];
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [headId, setHeadId] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
      setHeadId('');
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
        head_id: headId || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create department');
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      pending={create.isPending}
      title="Create department"
      subtitle="Group teams under a single org-chart bucket. Description is optional but useful."
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
            form="create-department-form"
            disabled={create.isPending || name.trim() === ''}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {create.isPending ? 'Creating…' : 'Create department'}
          </button>
        </>
      }
    >
      <form id="create-department-form" onSubmit={onSubmit} className="space-y-3">
        <div>
          <label
            htmlFor="dept_name"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Name
          </label>
          <input
            id="dept_name"
            type="text"
            required
            value={name}
            maxLength={120}
            placeholder="Engineering"
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label
            htmlFor="dept_description"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Description
          </label>
          <textarea
            id="dept_description"
            value={description}
            rows={3}
            maxLength={20_000}
            placeholder="What this department is responsible for."
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label
            htmlFor="dept_head"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Head (optional)
          </label>
          <select
            id="dept_head"
            value={headId}
            onChange={(e) => setHeadId(e.target.value)}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">No head</option>
            {members.map((m: Member) => (
              <option key={m.id} value={m.id}>
                {m.name}
                {m.email ? ` — ${m.email}` : ''}
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

function DepartmentDetailDrawer({
  department,
  canEdit,
  teams,
  managersByTeam,
  onClose,
}: {
  department: Department;
  canEdit: boolean;
  teams: TeamRecord[];
  managersByTeam: Map<string, Member>;
  onClose: () => void;
}) {
  const update = useUpdateDepartment();
  const remove = useDeleteDepartment();
  const { data: membersPage } = useMembers({ humansOnly: true });
  const members = membersPage?.items ?? [];
  // View by default; admin clicks Edit to switch into the form. Save
  // commits and snaps back to view; Cancel discards state.
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(department.name);
  const [description, setDescription] = useState(department.description ?? '');
  const [headId, setHeadId] = useState(department.head_id ?? '');
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Reset on a different dept opening.
  useEffect(() => {
    setName(department.name);
    setDescription(department.description ?? '');
    setHeadId(department.head_id ?? '');
    setEditing(false);
    setError(null);
  }, [department.id, department.name, department.description, department.head_id]);

  // Escape closes the drawer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !update.isPending && !remove.isPending) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, update.isPending, remove.isPending]);

  const trimmedName = name.trim();
  const trimmedDesc = description.trim();
  const nameChanged = trimmedName !== department.name && trimmedName !== '';
  const descChanged = trimmedDesc !== (department.description ?? '');
  const headChanged = (headId || null) !== (department.head_id ?? null);
  const dirty = nameChanged || descChanged || headChanged;

  const onSave = async () => {
    setError(null);
    if (!dirty) {
      setEditing(false);
      return;
    }
    try {
      await update.mutateAsync({
        id: department.id,
        payload: {
          ...(nameChanged ? { name: trimmedName } : {}),
          // Send description=null explicitly when the field is empty
          // and the dept previously had one — that's the api's clear
          // signal.
          ...(descChanged ? { description: trimmedDesc === '' ? null : trimmedDesc } : {}),
          // Same clear-signal convention for head_id: '' (empty
          // select) maps to null which the api treats as "clear".
          ...(headChanged ? { head_id: headId || null } : {}),
        },
      });
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save');
    }
  };

  const onCancel = () => {
    // Snap fields back to the persisted values and exit edit mode.
    setName(department.name);
    setDescription(department.description ?? '');
    setHeadId(department.head_id ?? '');
    setError(null);
    setEditing(false);
  };

  const onDelete = async () => {
    setError(null);
    try {
      await remove.mutateAsync(department.id);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to delete');
    }
  };

  const tooltip = disabledDepartmentEditTooltip(department);

  return (
    <>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Department ${department.name}`}
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
                Department
              </p>
              <h2 className="truncate text-base font-semibold text-slate-900">{department.name}</h2>
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
            {/* Head — prominent banner above the edit / read-only
                blocks. Mirrors the row's treatment so the org-chart
                anchor is immediately visible on both surfaces. */}
            <div className="mb-4 flex items-center gap-3 rounded-md border border-amber-100 bg-amber-50/60 px-3 py-2">
              {department.head ? (
                <>
                  <AvatarCircle name={department.head.name} tone="amber" />
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                      Head of department
                    </p>
                    <Link
                      href={userHref(department.head.id)}
                      className="block truncate text-sm font-medium text-slate-900 hover:text-indigo-700 hover:underline"
                    >
                      {department.head.name}
                    </Link>
                    {department.head.email ? (
                      <p className="truncate text-[11px] text-slate-500">{department.head.email}</p>
                    ) : null}
                  </div>
                </>
              ) : (
                <>
                  <AvatarCircle name="?" tone="muted" />
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      Head of department
                    </p>
                    <p className="text-sm italic text-slate-500">No head assigned yet.</p>
                  </div>
                </>
              )}
            </div>

            <section className="mb-5 space-y-3">
              {/* Toolbar sits above the details so the Edit / Save /
                  Cancel buttons stay at the top of the panel. The
                  disabled-state tooltip on Edit names the Department
                  Head as the nearest authorised editor (priority ≤
                  {DEPARTMENT_REACH_PRIORITY}). */}
              <EditToolbar
                editing={editing}
                canEdit={canEdit}
                disabledReason={tooltip}
                onEdit={() => setEditing(true)}
                onCancel={onCancel}
                onSave={onSave}
                dirty={dirty}
                saving={update.isPending}
                saveLabel="Save changes"
              />

              {editing ? (
                <div className="space-y-3 rounded-md border border-indigo-100 bg-indigo-50/40 px-3 py-3">
                  <div>
                    <label
                      htmlFor="dept_drawer_name"
                      className="block text-xs font-medium uppercase tracking-wide text-slate-600"
                    >
                      Name
                    </label>
                    <input
                      id="dept_drawer_name"
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
                      htmlFor="dept_drawer_description"
                      className="block text-xs font-medium uppercase tracking-wide text-slate-600"
                    >
                      Description
                    </label>
                    <textarea
                      id="dept_drawer_description"
                      rows={3}
                      value={description}
                      maxLength={20_000}
                      onChange={(e) => setDescription(e.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="dept_drawer_head"
                      className="block text-xs font-medium uppercase tracking-wide text-slate-600"
                    >
                      Head
                    </label>
                    <select
                      id="dept_drawer_head"
                      value={headId}
                      onChange={(e) => setHeadId(e.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="">No head</option>
                      {members.map((m: Member) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                          {m.email ? ` — ${m.email}` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : (
                <div className="space-y-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      Name
                    </p>
                    <p className="mt-1 text-sm text-slate-800">{department.name}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      Description
                    </p>
                    <p className="mt-1 text-sm text-slate-800">
                      {department.description ? (
                        department.description
                      ) : (
                        <span className="italic text-slate-500">No description.</span>
                      )}
                    </p>
                  </div>
                </div>
              )}
            </section>

            <div className="mb-3 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-slate-900">
                Teams
                <span className="ml-1.5 text-xs font-normal text-slate-500">({teams.length})</span>
              </h3>
              <Link href="/teams" className="text-xs font-medium text-indigo-700 hover:underline">
                File more from Teams →
              </Link>
            </div>

            {teams.length === 0 ? (
              <p className="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-xs italic text-slate-500">
                No teams in this department yet.{' '}
                {canEdit
                  ? 'Open a team in the Teams view to file it here.'
                  : 'Ask an admin to file teams.'}
              </p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {teams.map((t) => (
                  <li key={t.id} className="py-2">
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={teamHref(t.id)}
                        className="block text-sm font-medium text-slate-900 hover:text-indigo-700 hover:underline"
                      >
                        {t.name}
                      </Link>
                      <TeamManagerBadge manager={managersByTeam.get(t.id) ?? null} />
                    </div>
                    {t.description ? (
                      <p className="mt-0.5 line-clamp-2 text-xs text-slate-600">{t.description}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}

            {error ? (
              <p role="alert" className="mt-4 text-sm text-red-600">
                {error}
              </p>
            ) : null}
          </div>

          {canEdit ? (
            <footer className="border-t border-slate-200 bg-slate-50 px-5 py-3">
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                disabled={remove.isPending}
                className="w-full rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
              >
                {remove.isPending ? 'Deleting…' : 'Delete department'}
              </button>
            </footer>
          ) : null}
        </aside>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete "${department.name}"?`}
        message="Teams in this department keep existing — they're just unfiled. You can file them under another department later."
        confirmLabel="Delete department"
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
