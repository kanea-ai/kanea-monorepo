'use client';

import { useState } from 'react';

import { AdminShell } from '../components/AdminShell';
import { EntityDetailPanel } from '../components/EntityDetailPanel';
import { useRequireAuth } from '../lib/auth';
import { useAdminAgents, useAdminUsers } from '../lib/queries';

const PAGE_SIZE = 25;

// Discriminated union for the unified row + the open-detail target.
// HUMAN rows came from /admin/users; AGENT rows came from /admin/agents.
// The detail panel is opened with the appropriate Entry shape based
// on the type.
type RowType = 'HUMAN' | 'AGENT';

type OpenTarget =
  | { kind: 'user'; userId: string }
  | { kind: 'workspace-member'; workspaceId: string; memberId: string };

export default function UsersPage() {
  const ready = useRequireAuth();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<OpenTarget | null>(null);

  const opts = {
    name: search.trim() || undefined,
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
  // Two queries — humans and agents are listed independently and
  // merged into a single grid below. Each page is sliced at PAGE_SIZE
  // for both; the union may exceed PAGE_SIZE rows (acceptable for the
  // back-office, where the grid is for triage not pagination parity).
  const humansQuery = useAdminUsers(opts);
  const agentsQuery = useAdminAgents(opts);

  if (!ready) return null;

  const humanRows = (humansQuery.data?.items ?? []).map((u) => ({
    rowType: 'HUMAN' as RowType,
    key: `h:${u.id}`,
    full_name: u.full_name,
    email: u.email,
    badge: u.is_banned
      ? ('banned' as const)
      : u.is_superadmin
        ? ('superadmin' as const)
        : ('active' as const),
    onOpen: (): OpenTarget => ({ kind: 'user', userId: u.id }),
  }));
  const agentRows = (agentsQuery.data?.items ?? []).map((a) => ({
    rowType: 'AGENT' as RowType,
    key: `a:${a.member_id}`,
    full_name: a.full_name,
    email: a.workspace_name,
    badge: 'agent' as const,
    onOpen: (): OpenTarget => ({
      kind: 'workspace-member',
      workspaceId: a.workspace_id,
      memberId: a.member_id,
    }),
  }));
  const rows = [...humanRows, ...agentRows];

  const total = (humansQuery.data?.total ?? 0) + (agentsQuery.data?.total ?? 0);
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const isLoading = humansQuery.isLoading || agentsQuery.isLoading;
  const isError = humansQuery.isError || agentsQuery.isError;

  return (
    <AdminShell>
      <div className="space-y-4 p-6">
        <header>
          <h1 className="text-xl font-semibold text-slate-900">Users</h1>
          <p className="text-sm text-slate-500">
            Every human and AI agent on the platform. Click a row to inspect membership, edit the
            workspace slot, or run global actions (ban / force reset).
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
              placeholder="Search by name, email, or agent name…"
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
            />
          </div>

          {isError ? (
            <p className="px-4 py-6 text-sm text-red-600">
              Failed to load users:{' '}
              {(humansQuery.error as Error)?.message ??
                (agentsQuery.error as Error)?.message ??
                'unknown'}
            </p>
          ) : isLoading ? (
            <p className="px-4 py-6 text-sm text-slate-500">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm italic text-slate-500">No users match.</p>
          ) : (
            <table className="w-full table-fixed text-sm">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-2 text-left">Name</th>
                  <th className="w-24 px-4 py-2 text-left">Type</th>
                  <th className="px-4 py-2 text-left">Email / Workspace</th>
                  <th className="w-28 px-4 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr
                    key={r.key}
                    onClick={() => setOpen(r.onOpen())}
                    className="cursor-pointer hover:bg-slate-50"
                  >
                    <td className="truncate px-4 py-2 font-medium text-slate-900">{r.full_name}</td>
                    <td className="px-4 py-2">
                      <TypePill type={r.rowType} />
                    </td>
                    <td className="truncate px-4 py-2 text-slate-600">{r.email}</td>
                    <td className="px-4 py-2">
                      <StatusPill kind={r.badge} />
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

        {open ? <EntityDetailPanel entry={open} onClose={() => setOpen(null)} /> : null}
      </div>
    </AdminShell>
  );
}

function TypePill({ type }: { type: RowType }) {
  const classes =
    type === 'AGENT' ? 'bg-indigo-100 text-indigo-800' : 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${classes}`}
    >
      {type}
    </span>
  );
}

function StatusPill({ kind }: { kind: 'banned' | 'superadmin' | 'active' | 'agent' }) {
  const map = {
    banned: { label: 'Banned', cls: 'bg-red-100 text-red-800' },
    superadmin: { label: 'Superadmin', cls: 'bg-rose-100 text-rose-800' },
    active: { label: 'Active', cls: 'bg-emerald-100 text-emerald-800' },
    agent: { label: 'Agent', cls: 'bg-indigo-100 text-indigo-800' },
  } as const;
  const { label, cls } = map[kind];
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {label}
    </span>
  );
}
