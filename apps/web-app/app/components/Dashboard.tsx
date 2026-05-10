'use client';

import Link from 'next/link';
import { useMemo } from 'react';

import type { Task, TaskStatus } from '../lib/api';
import { useDashboard } from '../lib/queries';

const STATUS_LABEL: Record<TaskStatus, string> = {
  PENDING: 'Pending',
  IN_PROGRESS: 'In Progress',
  IN_REVIEW: 'In Review',
  DONE: 'Done',
  CANCELLED: 'Cancelled',
};

export function Dashboard() {
  const { data, isLoading, isError, error } = useDashboard();
  const tasks = useMemo(() => data?.tasks ?? [], [data]);
  const scope = data?.scope;

  const counts = useMemo(() => bucketByStatus(tasks), [tasks]);
  const blocked = useMemo(() => tasks.filter((t) => t.is_blocked), [tasks]);
  const recent = useMemo(
    () => [...tasks].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 8),
    [tasks],
  );

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
            {scope ? (
              <span
                title={
                  scope.is_admin
                    ? 'Workspace-wide view (you are an admin/owner).'
                    : 'Scope is derived from your role and team. Admins see the entire workspace.'
                }
                className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                  scope.is_admin ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600'
                }`}
              >
                {scope.label}
                {scope.project_count > 0 ? ` · ${scope.project_count} projects` : ''}
              </span>
            ) : null}
          </div>
          <p className="text-sm text-slate-500">
            Snapshot scoped to your role. Admins/owners see the whole workspace; managers, leads,
            and members see progressively narrower slices.
          </p>
        </div>
        <Link
          href="/board"
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
        >
          Open board
        </Link>
      </header>

      {isError ? (
        <ErrorBanner message={(error as Error).message} />
      ) : (
        <>
          <section
            aria-label="Status summary"
            className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
          >
            <StatTile
              label="Total"
              value={tasks.length}
              loading={isLoading}
              tone="default"
              href="/board"
            />
            <StatTile
              label={STATUS_LABEL.PENDING}
              value={counts.PENDING}
              loading={isLoading}
              tone="default"
              href="/board"
            />
            <StatTile
              label={STATUS_LABEL.IN_PROGRESS}
              value={counts.IN_PROGRESS}
              loading={isLoading}
              tone="info"
              href="/board"
            />
            <StatTile
              label="Blocked"
              value={blocked.length}
              loading={isLoading}
              tone={blocked.length > 0 ? 'warn' : 'default'}
              href="/blocks"
            />
            <StatTile
              label={STATUS_LABEL.DONE}
              value={counts.DONE}
              loading={isLoading}
              tone="success"
              href="/board"
            />
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <Panel
              title="Needs human intervention"
              subtitle="Tasks an agent flagged as blocked."
              action={
                <Link
                  href="/blocks"
                  className="text-xs font-medium text-indigo-700 hover:underline"
                >
                  View all →
                </Link>
              }
            >
              {isLoading ? (
                <SkeletonRows count={3} />
              ) : blocked.length === 0 ? (
                <EmptyRow message="All clear — no blocked tasks." />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {blocked.slice(0, 5).map((t) => (
                    <BlockedRow key={t.id} task={t} />
                  ))}
                </ul>
              )}
            </Panel>

            <Panel title="Recent activity" subtitle="Latest task updates across the workspace.">
              {isLoading ? (
                <SkeletonRows count={4} />
              ) : recent.length === 0 ? (
                <EmptyRow message="No tasks yet — create one from the board." />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {recent.map((t) => (
                    <ActivityRow key={t.id} task={t} />
                  ))}
                </ul>
              )}
            </Panel>
          </section>
        </>
      )}
    </div>
  );
}

function bucketByStatus(tasks: Task[]): Record<TaskStatus, number> {
  const out: Record<TaskStatus, number> = {
    PENDING: 0,
    IN_PROGRESS: 0,
    IN_REVIEW: 0,
    DONE: 0,
    CANCELLED: 0,
  };
  for (const t of tasks) out[t.status] += 1;
  return out;
}

type Tone = 'default' | 'info' | 'success' | 'warn';

const TONE_CLASSES: Record<Tone, string> = {
  default: 'border-slate-200 bg-white',
  info: 'border-blue-200 bg-blue-50',
  success: 'border-emerald-200 bg-emerald-50',
  warn: 'border-amber-200 bg-amber-50',
};

function StatTile({
  label,
  value,
  loading,
  tone,
  href,
}: {
  label: string;
  value: number;
  loading: boolean;
  tone: Tone;
  href: string;
}) {
  return (
    <Link
      href={href}
      className={`rounded-lg border p-4 shadow-sm transition-shadow hover:shadow-md ${TONE_CLASSES[tone]}`}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">
        {loading ? (
          <span className="inline-block h-7 w-12 animate-pulse rounded bg-slate-200" />
        ) : (
          value
        )}
      </p>
    </Link>
  );
}

function Panel({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex items-start justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p> : null}
        </div>
        {action}
      </header>
      <div className="p-1">{children}</div>
    </section>
  );
}

function BlockedRow({ task }: { task: Task }) {
  return (
    <li className="flex items-start justify-between gap-3 px-3 py-2.5">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-slate-900">{task.title}</p>
        {task.blocked_reason ? (
          <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">{task.blocked_reason}</p>
        ) : (
          <p className="mt-0.5 text-xs italic text-slate-400">No reason provided.</p>
        )}
      </div>
      <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-800">
        P{task.priority}
      </span>
    </li>
  );
}

function ActivityRow({ task }: { task: Task }) {
  return (
    <li className="flex items-center justify-between gap-3 px-3 py-2.5">
      <div className="min-w-0">
        <p className="truncate text-sm text-slate-900">{task.title}</p>
        <p className="mt-0.5 text-xs text-slate-500">Updated {formatRelative(task.updated_at)}</p>
      </div>
      <StatusPill status={task.status} />
    </li>
  );
}

const STATUS_PILL: Record<TaskStatus, string> = {
  PENDING: 'bg-slate-100 text-slate-700',
  IN_PROGRESS: 'bg-blue-100 text-blue-800',
  IN_REVIEW: 'bg-amber-100 text-amber-800',
  DONE: 'bg-emerald-100 text-emerald-800',
  CANCELLED: 'bg-slate-100 text-slate-500',
};

function StatusPill({ status }: { status: TaskStatus }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${STATUS_PILL[status]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <ul className="divide-y divide-slate-100">
      {Array.from({ length: count }).map((_, i) => (
        <li key={i} className="px-3 py-3">
          <div className="h-3 w-2/3 animate-pulse rounded bg-slate-100" />
          <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-slate-100" />
        </li>
      ))}
    </ul>
  );
}

function EmptyRow({ message }: { message: string }) {
  return <p className="px-3 py-6 text-center text-sm text-slate-500">{message}</p>;
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {message}
    </div>
  );
}

function formatRelative(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const diff = Date.now() - ts;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}
