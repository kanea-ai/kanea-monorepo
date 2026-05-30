'use client';

import { useState } from 'react';

import { AdminShell } from '../components/AdminShell';
import { UserDetailDialog } from '../components/UserDetailDialog';
import { useRequireAuth } from '../lib/auth';
import { useAdminUsers } from '../lib/queries';

const PAGE_SIZE = 25;

export default function UsersPage() {
  const ready = useRequireAuth();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [openUserId, setOpenUserId] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useAdminUsers({
    name: search.trim() || undefined,
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  });

  if (!ready) return null;

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AdminShell>
      <div className="space-y-4 p-6">
        <header>
          <h1 className="text-xl font-semibold text-slate-900">Users</h1>
          <p className="text-sm text-slate-500">
            Every global User on the platform. Click a row to inspect their workspace memberships,
            manage their global ban, or force a password reset.
          </p>
        </header>

        <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-4 py-2">
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search by email or name…"
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
            />
          </div>

          {isError ? (
            <p className="px-4 py-6 text-sm text-red-600">
              Failed to load users: {(error as Error).message}
            </p>
          ) : isLoading ? (
            <p className="px-4 py-6 text-sm text-slate-500">Loading…</p>
          ) : items.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm italic text-slate-500">No users match.</p>
          ) : (
            <table className="w-full table-fixed text-sm">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-2 text-left">Name</th>
                  <th className="px-4 py-2 text-left">Email</th>
                  <th className="w-20 px-4 py-2 text-right">Workspaces</th>
                  <th className="w-28 px-4 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((u) => (
                  <tr
                    key={u.id}
                    onClick={() => setOpenUserId(u.id)}
                    className="cursor-pointer hover:bg-slate-50"
                  >
                    <td className="truncate px-4 py-2 font-medium text-slate-900">{u.full_name}</td>
                    <td className="truncate px-4 py-2 text-slate-600">{u.email}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{u.workspace_count}</td>
                    <td className="px-4 py-2">
                      {u.is_banned ? (
                        <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                          Banned
                        </span>
                      ) : u.is_superadmin ? (
                        <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-rose-800">
                          Superadmin
                        </span>
                      ) : (
                        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800">
                          Active
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {total > 0 ? (
            <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-[12px] text-slate-500">
              <p>
                {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
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

        {openUserId ? (
          <UserDetailDialog userId={openUserId} onClose={() => setOpenUserId(null)} />
        ) : null}
      </div>
    </AdminShell>
  );
}
