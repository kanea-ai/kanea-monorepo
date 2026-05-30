'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useMemo, useState } from 'react';

import { AdminShell } from '../../components/AdminShell';
import { EditWorkspaceUserDialog } from '../../components/EditWorkspaceUserDialog';
import { type AdminWorkspaceUserRow } from '../../lib/api';
import { useRequireAuth } from '../../lib/auth';
import { useWorkspaceDetail, useWorkspaceUsers } from '../../lib/queries';

const PAGE_SIZE = 25;

export default function WorkspaceDetailPage() {
  const ready = useRequireAuth();
  const params = useParams<{ id: string }>();
  const workspaceId = params.id;
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [openUser, setOpenUser] = useState<AdminWorkspaceUserRow | null>(null);

  const { data: detail, isLoading: detailLoading } = useWorkspaceDetail(workspaceId);
  const { data: usersPage, isLoading: usersLoading } = useWorkspaceUsers(workspaceId, {
    name: search.trim() || undefined,
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  });

  // The teams + departments dropdowns in the edit dialog are seeded
  // from whatever team / department references appear in the users
  // listing. This keeps the back-office self-sufficient — no extra
  // /admin/teams or /admin/departments endpoint needed for the MVP.
  // (When a workspace has thousands of users we'd swap this for a
  // dedicated lookup; for now the listing covers it.)
  const allUsers = usersPage?.items ?? [];
  const teamOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const u of allUsers) {
      if (u.team_id && u.team_name) map.set(u.team_id, u.team_name);
    }
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [allUsers]);
  const departmentOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const u of allUsers) {
      if (u.team_department_id && u.team_department_name) {
        map.set(u.team_department_id, u.team_department_name);
      }
      if (u.headed_department_id && u.headed_department_name) {
        map.set(u.headed_department_id, u.headed_department_name);
      }
    }
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [allUsers]);

  if (!ready) return null;
  const lastPage = Math.max(1, Math.ceil((usersPage?.total ?? 0) / PAGE_SIZE));

  return (
    <AdminShell>
      <div className="space-y-6 p-6">
        <header>
          <Link href="/workspaces" className="text-xs text-slate-500 hover:text-slate-700">
            ← Workspaces
          </Link>
          <h1 className="mt-1 text-xl font-semibold text-slate-900">
            {detail?.name ?? 'Workspace'}
          </h1>
          {detail ? (
            <p className="text-xs text-slate-500">
              <span className="font-mono">{detail.slug}</span> · created{' '}
              {new Date(detail.created_at).toLocaleDateString()}
              {detail.suspended_at ? (
                <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                  Suspended
                </span>
              ) : null}
            </p>
          ) : null}
        </header>

        {/* Stats grid */}
        <section className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Users" value={detail?.total_users} loading={detailLoading} />
          <Stat label="Teams" value={detail?.total_teams} loading={detailLoading} />
          <Stat label="Departments" value={detail?.total_departments} loading={detailLoading} />
          <Stat label="Projects" value={detail?.total_projects} loading={detailLoading} />
          <Stat label="Tasks" value={detail?.total_tasks} loading={detailLoading} />
          <Stat label="Tokens used" value={detail?.total_tokens_used} loading={detailLoading} />
        </section>

        <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <header className="border-b border-slate-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Task status</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Distribution of tasks across the workspace.
            </p>
          </header>
          <div className="grid grid-cols-2 gap-3 px-4 py-3 sm:grid-cols-6">
            <Stat
              label="Pending"
              value={detail?.status_breakdown.pending}
              loading={detailLoading}
            />
            <Stat
              label="In progress"
              value={detail?.status_breakdown.in_progress}
              loading={detailLoading}
            />
            <Stat
              label="In review"
              value={detail?.status_breakdown.in_review}
              loading={detailLoading}
            />
            <Stat label="Done" value={detail?.status_breakdown.done} loading={detailLoading} />
            <Stat
              label="Cancelled"
              value={detail?.status_breakdown.cancelled}
              loading={detailLoading}
            />
            <Stat
              label="Blocked"
              value={detail?.status_breakdown.blocked}
              loading={detailLoading}
            />
          </div>
        </section>

        {/* Users table */}
        <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <header className="border-b border-slate-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Workspace users</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Hierarchy slot per member. Click Edit to intervene on the tenant&apos;s behalf.
            </p>
          </header>
          <div className="border-b border-slate-100 px-4 py-2">
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search by name or email…"
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
            />
          </div>
          {usersLoading ? (
            <p className="px-4 py-6 text-sm text-slate-500">Loading…</p>
          ) : allUsers.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm italic text-slate-500">No users match.</p>
          ) : (
            <table className="w-full table-fixed text-sm">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-2 text-left">User</th>
                  <th className="w-32 px-4 py-2 text-left">Role</th>
                  <th className="w-40 px-4 py-2 text-left">Team / Head</th>
                  <th className="w-40 px-4 py-2 text-left">Department</th>
                  <th className="w-20 px-4 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {allUsers.map((u) => (
                  <tr key={u.member_id}>
                    <td className="truncate px-4 py-2">
                      <p className="truncate font-medium text-slate-900">{u.full_name}</p>
                      <p className="truncate text-[11px] text-slate-500">{u.email ?? '—'}</p>
                    </td>
                    <td className="px-4 py-2 text-[11px] text-slate-700">
                      {u.role.replace('WORKSPACE_', '')}
                    </td>
                    <td className="px-4 py-2 text-[11px] text-slate-700">
                      {u.headed_department_name ? (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
                          Head
                        </span>
                      ) : u.team_name ? (
                        <span>
                          {u.team_name} <span className="text-slate-500">({u.team_role})</span>
                        </span>
                      ) : (
                        <span className="italic text-slate-400">Unassigned</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-[11px] text-slate-700">
                      {u.headed_department_name ?? u.team_department_name ?? (
                        <span className="italic text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => setOpenUser(u)}
                        className="rounded-md border border-rose-200 bg-white px-2.5 py-1 text-xs font-medium text-rose-700 hover:bg-rose-50"
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {(usersPage?.total ?? 0) > 0 ? (
            <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-[12px] text-slate-500">
              <p>
                {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, usersPage?.total ?? 0)} of{' '}
                {usersPage?.total ?? 0}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="rounded-md border border-slate-200 px-2 py-0.5 text-xs hover:bg-slate-50 disabled:opacity-50"
                >
                  Prev
                </button>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
                  disabled={page >= lastPage}
                  className="rounded-md border border-slate-200 px-2 py-0.5 text-xs hover:bg-slate-50 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}
        </section>

        {openUser ? (
          <EditWorkspaceUserDialog
            workspaceId={workspaceId}
            user={openUser}
            teamOptions={teamOptions}
            departmentOptions={departmentOptions}
            onClose={() => setOpenUser(null)}
          />
        ) : null}
      </div>
    </AdminShell>
  );
}

function Stat({
  label,
  value,
  loading,
}: {
  label: string;
  value: number | undefined;
  loading: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">
        {loading ? '—' : value != null ? value.toLocaleString() : '—'}
      </p>
    </div>
  );
}
