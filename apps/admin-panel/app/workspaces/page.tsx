'use client';

import { useState } from 'react';

import { AdminShell } from '../components/AdminShell';
import { SuspendWorkspaceModal } from '../components/SuspendWorkspaceModal';
import { type AdminWorkspaceRow } from '../lib/api';
import { useRequireAuth } from '../lib/auth';
import { useAdminWorkspaces } from '../lib/queries';

const PAGE_SIZE = 25;

type SortKey =
  | 'created_at_desc'
  | 'created_at_asc'
  | 'name_asc'
  | 'name_desc'
  | 'suspended_at_desc';

export default function WorkspacesPage() {
  const ready = useRequireAuth();
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortKey>('created_at_desc');
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<{
    workspace: AdminWorkspaceRow;
    intent: 'suspend' | 'restore';
  } | null>(null);

  const { data, isLoading, isError, error } = useAdminWorkspaces({
    name: search.trim() || undefined,
    sort,
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
          <h1 className="text-xl font-semibold text-slate-900">Workspaces</h1>
          <p className="text-sm text-slate-500">
            Every tenant on the platform. Suspending blocks all of their API traffic with 403 until
            you restore — data is preserved.
          </p>
        </header>

        <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2">
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search by name or slug…"
              className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
            />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
            >
              <option value="created_at_desc">Newest first</option>
              <option value="created_at_asc">Oldest first</option>
              <option value="name_asc">Name A → Z</option>
              <option value="name_desc">Name Z → A</option>
              <option value="suspended_at_desc">Suspended first</option>
            </select>
          </div>

          {isError ? (
            <p className="px-4 py-6 text-sm text-red-600">
              Failed to load workspaces: {(error as Error).message}
            </p>
          ) : isLoading ? (
            <p className="px-4 py-6 text-sm text-slate-500">Loading…</p>
          ) : items.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm italic text-slate-500">
              No workspaces match.
            </p>
          ) : (
            <table className="w-full table-fixed text-sm">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-2 text-left">Name</th>
                  <th className="w-24 px-4 py-2 text-left">Slug</th>
                  <th className="w-16 px-4 py-2 text-right">Users</th>
                  <th className="w-16 px-4 py-2 text-right">Tasks</th>
                  <th className="w-24 px-4 py-2 text-right">Tokens</th>
                  <th className="w-28 px-4 py-2 text-left">Status</th>
                  <th className="w-28 px-4 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((w) => (
                  <WorkspaceRow
                    key={w.id}
                    workspace={w}
                    onSuspend={() => setPending({ workspace: w, intent: 'suspend' })}
                    onRestore={() => setPending({ workspace: w, intent: 'restore' })}
                  />
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

        {pending ? (
          <SuspendWorkspaceModal
            workspace={pending.workspace}
            intent={pending.intent}
            onClose={() => setPending(null)}
          />
        ) : null}
      </div>
    </AdminShell>
  );
}

function WorkspaceRow({
  workspace,
  onSuspend,
  onRestore,
}: {
  workspace: AdminWorkspaceRow;
  onSuspend: () => void;
  onRestore: () => void;
}) {
  const isSuspended = workspace.suspended_at !== null;
  return (
    <tr className={isSuspended ? 'bg-red-50/40' : undefined}>
      <td className="truncate px-4 py-2 font-medium text-slate-900">{workspace.name}</td>
      <td className="truncate px-4 py-2 font-mono text-[11px] text-slate-500">{workspace.slug}</td>
      <td className="px-4 py-2 text-right tabular-nums">{workspace.metrics.total_users}</td>
      <td className="px-4 py-2 text-right tabular-nums">{workspace.metrics.total_tasks}</td>
      <td className="px-4 py-2 text-right tabular-nums">{workspace.metrics.total_tokens_used}</td>
      <td className="px-4 py-2">
        {isSuspended ? (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
            Suspended
          </span>
        ) : (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800">
            Active
          </span>
        )}
      </td>
      <td className="px-4 py-2 text-right">
        {isSuspended ? (
          <button
            type="button"
            onClick={onRestore}
            className="rounded-md border border-emerald-200 bg-white px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
          >
            Restore
          </button>
        ) : (
          <button
            type="button"
            onClick={onSuspend}
            className="rounded-md border border-red-200 bg-white px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            Suspend
          </button>
        )}
      </td>
    </tr>
  );
}
