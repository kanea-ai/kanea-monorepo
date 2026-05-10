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

import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';

import { ActorProfileDialog } from '../../components/ActorProfileDialog';
import { Pagination } from '../../components/Pagination';
import type { AuditAction, AuditLog, AuditResourceType } from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import { useAuditLogs } from '../../lib/queries';

const PAGE_SIZE = 25;

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
  // When set, opens the priority-scoped profile dialog. The api
  // returns the limited shape automatically when the principal is
  // lower-rank than the actor.
  const [actorOpenId, setActorOpenId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // Server-side pagination via skip/limit; the resource and actor
  // filters above are client-side narrowing on top of the page slice
  // — fine for the audit log's scale, and keeps the URL contract
  // simple for now.
  const {
    data: logsPage,
    isLoading,
    isError,
    error,
  } = useAuditLogs({ skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE });
  const items = logsPage?.items ?? [];
  const total = logsPage?.total ?? 0;

  const filtered = useMemo(() => {
    let rows = items;
    if (resourceFilter !== 'all') {
      rows = rows.filter((r) => r.resource_type === resourceFilter);
    }
    const q = actorFilter.trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) => (r.actor_name ?? '').toLowerCase().includes(q));
    }
    return rows;
  }, [items, resourceFilter, actorFilter]);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Audit log</h1>
        <p className="text-sm text-slate-500">
          Org and access-control events: department / team CRUD, role changes, suspensions, team
          assignments. Per-task events live on each task&apos;s detail page.
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
            <>
              <ol className="divide-y divide-slate-100">
                {filtered.map((row) => (
                  <AuditRow
                    key={row.id}
                    log={row}
                    onActorClick={setActorOpenId}
                    onMemberResourceClick={setActorOpenId}
                  />
                ))}
              </ol>
              <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
            </>
          )}
        </section>
      )}

      {actorOpenId ? (
        <ActorProfileDialog memberId={actorOpenId} onClose={() => setActorOpenId(null)} />
      ) : null}
    </div>
  );
}

function AuditRow({
  log,
  onActorClick,
  onMemberResourceClick,
}: {
  log: AuditLog;
  onActorClick: (memberId: string) => void;
  onMemberResourceClick: (memberId: string) => void;
}) {
  const router = useRouter();

  // The resource pill becomes a button whenever there's somewhere
  // sensible to navigate. DELETED rows opt out — the entity is gone,
  // so a click would land on a stale page. MEMBER targets the same
  // priority-scoped profile dialog the actor click uses;
  // DEPARTMENT/TEAM deep-link into their list pages, which open the
  // corresponding drawer when ?open=<id> is present.
  const resourceClickable =
    log.resource_id != null &&
    log.action !== 'DELETED' &&
    (log.resource_type === 'MEMBER' ||
      log.resource_type === 'DEPARTMENT' ||
      log.resource_type === 'TEAM');

  const onResourceClick = () => {
    if (!log.resource_id) return;
    if (log.resource_type === 'MEMBER') {
      onMemberResourceClick(log.resource_id);
    } else if (log.resource_type === 'DEPARTMENT') {
      router.push(`/departments?open=${log.resource_id}`);
    } else if (log.resource_type === 'TEAM') {
      router.push(`/teams?open=${log.resource_id}`);
    }
  };

  const pillClass = `rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${RESOURCE_TYPE_TONE[log.resource_type]}`;

  return (
    <li className="grid grid-cols-[auto_1fr_auto] items-start gap-3 px-4 py-3 text-sm">
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${ACTION_TONE[log.action]}`}
      >
        {log.action.replaceAll('_', ' ')}
      </span>
      <div className="min-w-0">
        {/* Pill + summary form a single click target when the resource
            is live. The pill stays a visual marker, the summary
            (which embeds the resource's name) gets the navigable
            underline so admins can click "Backend" or "Engineering"
            directly. */}
        <div className="flex flex-wrap items-center gap-2 text-slate-900">
          {resourceClickable ? (
            <button
              type="button"
              onClick={onResourceClick}
              className="group flex flex-wrap items-center gap-2 text-left"
            >
              <span className={`${pillClass} transition-colors group-hover:brightness-95`}>
                {RESOURCE_TYPE_LABEL[log.resource_type]}
              </span>
              <span className="font-medium underline-offset-2 group-hover:text-indigo-700 group-hover:underline">
                {summariseChanges(log)}
              </span>
            </button>
          ) : (
            <>
              <span className={pillClass}>{RESOURCE_TYPE_LABEL[log.resource_type]}</span>
              <span className="font-medium">{summariseChanges(log)}</span>
            </>
          )}
        </div>
        <p className="mt-0.5 text-xs text-slate-500">
          by{' '}
          {log.actor_member_id && log.actor_name ? (
            <button
              type="button"
              onClick={() => onActorClick(log.actor_member_id as string)}
              className="font-medium text-slate-700 underline-offset-2 hover:text-indigo-700 hover:underline"
            >
              {log.actor_name}
            </button>
          ) : (
            <em className="italic text-slate-400">deleted member</em>
          )}
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
