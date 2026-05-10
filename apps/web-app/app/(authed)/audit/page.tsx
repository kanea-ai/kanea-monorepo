'use client';

// Audit log view. Surfaces the workspace's org/RBAC events: department
// CRUD, team CRUD, member role changes, suspensions, team assignments.
// Per-task events still live on the task detail page.
//
// Visibility is enforced server-side based on the principal's role +
// priority (see app/api/v1/audit.py). The UI is the same shape for
// every admin tier — the api just returns fewer rows for narrower
// reach. A USER-role principal gets an empty list and we surface that
// as a friendly "your role doesn't grant audit access" message.

import { useMemo, useState } from 'react';

import type { AuditAction, AuditLog, AuditResourceType } from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import { useAuditLogs } from '../../lib/queries';

const RESOURCE_TYPE_LABEL: Record<AuditResourceType, string> = {
  WORKSPACE: 'Workspace',
  DEPARTMENT: 'Department',
  TEAM: 'Team',
  MEMBER: 'Member',
};

const RESOURCE_TYPE_TONE: Record<AuditResourceType, string> = {
  WORKSPACE: 'bg-slate-100 text-slate-700',
  DEPARTMENT: 'bg-indigo-100 text-indigo-800',
  TEAM: 'bg-blue-100 text-blue-800',
  MEMBER: 'bg-emerald-100 text-emerald-800',
};

const ACTION_TONE: Record<AuditAction, string> = {
  CREATED: 'bg-emerald-100 text-emerald-800',
  UPDATED: 'bg-amber-100 text-amber-800',
  DELETED: 'bg-red-100 text-red-800',
  SUSPENDED: 'bg-red-100 text-red-800',
  SUSPENSION_REVOKED: 'bg-emerald-100 text-emerald-800',
  ROLE_CHANGED: 'bg-violet-100 text-violet-800',
  TEAM_ASSIGNED: 'bg-blue-100 text-blue-800',
  TEAM_UNASSIGNED: 'bg-slate-100 text-slate-600',
};

export default function AuditPage() {
  const principal = useCurrentPrincipal();
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';

  const [resourceFilter, setResourceFilter] = useState<'all' | AuditResourceType>('all');
  const [actorFilter, setActorFilter] = useState<string>('');

  const { data: logs, isLoading, isError, error } = useAuditLogs({ limit: 200 });

  const filtered = useMemo(() => {
    let rows = logs ?? [];
    if (resourceFilter !== 'all') {
      rows = rows.filter((r) => r.resource_type === resourceFilter);
    }
    const q = actorFilter.trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) => (r.actor_name ?? '').toLowerCase().includes(q));
    }
    return rows;
  }, [logs, resourceFilter, actorFilter]);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Audit log</h1>
        <p className="text-sm text-slate-500">
          Org and access-control events: department / team CRUD, role changes, suspensions, team
          assignments. Per-task events live on each task's detail page.
        </p>
        {isAdmin ? (
          <p className="mt-1 text-xs text-slate-500">
            Visibility is scoped by your priority — owners see everything, priority-2 admins see
            departments / teams / members, priority-3 admins see only the teams they oversee.
          </p>
        ) : null}
      </header>

      {!isAdmin ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-6 text-sm text-amber-800">
          The audit log is restricted to workspace admins. Ask an owner if you need access.
        </section>
      ) : (
        <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-2 border-b border-slate-100 px-4 py-3 sm:flex-row sm:items-center">
            <label className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              Resource
              <select
                value={resourceFilter}
                onChange={(e) => setResourceFilter(e.target.value as 'all' | AuditResourceType)}
                className="rounded-md border border-slate-300 px-2 py-1 text-sm font-normal normal-case text-slate-800 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="all">All</option>
                <option value="DEPARTMENT">Departments</option>
                <option value="TEAM">Teams</option>
                <option value="MEMBER">Members</option>
              </select>
            </label>
            <input
              type="search"
              value={actorFilter}
              onChange={(e) => setActorFilter(e.target.value)}
              placeholder="Filter by actor name…"
              className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <span className="ml-auto text-[11px] text-slate-500">
              {filtered.length} {filtered.length === 1 ? 'event' : 'events'}
            </span>
          </div>

          {isError ? (
            <p className="px-4 py-6 text-sm text-red-600">
              Failed to load audit logs: {(error as Error).message}
            </p>
          ) : isLoading ? (
            <p className="px-4 py-6 text-sm text-slate-500">Loading audit log…</p>
          ) : filtered.length === 0 ? (
            <EmptyState narrowed={resourceFilter !== 'all' || actorFilter !== ''} />
          ) : (
            <ol className="divide-y divide-slate-100">
              {filtered.map((row) => (
                <AuditRow key={row.id} log={row} />
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  );
}

function AuditRow({ log }: { log: AuditLog }) {
  return (
    <li className="grid grid-cols-[auto_1fr_auto] items-start gap-3 px-4 py-3 text-sm">
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${ACTION_TONE[log.action]}`}
      >
        {log.action.replaceAll('_', ' ')}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-slate-900">
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${RESOURCE_TYPE_TONE[log.resource_type]}`}
          >
            {RESOURCE_TYPE_LABEL[log.resource_type]}
          </span>
          <span className="font-medium">{summariseChanges(log)}</span>
        </div>
        <p className="mt-0.5 text-xs text-slate-500">
          by{' '}
          <span className="font-medium text-slate-700">
            {log.actor_name ?? <em className="italic text-slate-400">deleted member</em>}
          </span>
          {' · '}
          {new Date(log.created_at).toLocaleString()}
        </p>
        <ChangesDetails log={log} />
      </div>
    </li>
  );
}

function summariseChanges(log: AuditLog): string {
  const c = log.changes;
  if (log.action === 'ROLE_CHANGED') {
    return `${strField(c, 'member_name')}: ${strField(c, 'from')} → ${strField(c, 'to')}`;
  }
  if (log.action === 'SUSPENDED') {
    return `Suspended ${strField(c, 'member_name')}`;
  }
  if (log.action === 'SUSPENSION_REVOKED') {
    return `Revoked suspension on ${strField(c, 'member_name')}`;
  }
  if (log.action === 'TEAM_ASSIGNED') {
    return `Assigned ${strField(c, 'member_name')} to a team`;
  }
  if (log.action === 'TEAM_UNASSIGNED') {
    return `Unassigned ${strField(c, 'member_name')} from a team`;
  }
  if (log.action === 'CREATED' || log.action === 'DELETED') {
    return strField(c, 'name') ?? '—';
  }
  if (log.action === 'UPDATED') {
    const changedFields = Object.keys(c);
    return changedFields.length === 0 ? 'updated' : `Changed: ${changedFields.join(', ')}`;
  }
  return '—';
}

function ChangesDetails({ log }: { log: AuditLog }) {
  const c = log.changes;
  if (log.action !== 'UPDATED') return null;
  const entries = Object.entries(c).filter(
    ([, val]) => typeof val === 'object' && val != null && 'from' in (val as object),
  );
  if (entries.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5 text-[11px] text-slate-600">
      {entries.map(([field, val]) => {
        const fromTo = val as { from: unknown; to: unknown };
        return (
          <li key={field}>
            <span className="font-medium text-slate-700">{field}:</span>{' '}
            <span className="text-slate-400 line-through">{formatValue(fromTo.from)}</span> →{' '}
            <span>{formatValue(fromTo.to)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function formatValue(v: unknown): string {
  if (v == null) return '—';
  if (typeof v === 'string') return v === '' ? '(empty)' : v;
  return JSON.stringify(v);
}

function strField(c: Record<string, unknown>, key: string): string {
  const v = c[key];
  return typeof v === 'string' ? v : v == null ? '—' : JSON.stringify(v);
}

function EmptyState({ narrowed }: { narrowed: boolean }) {
  return (
    <div className="px-4 py-10 text-center">
      <p className="text-sm font-medium text-slate-700">
        {narrowed ? 'No matching events.' : 'No events yet.'}
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {narrowed
          ? 'Try clearing the filters.'
          : 'Department and team admins will see entries here as workspace settings change.'}
      </p>
    </div>
  );
}
