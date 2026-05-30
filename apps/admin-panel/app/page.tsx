'use client';

import Link from 'next/link';

import { AdminShell } from './components/AdminShell';
import { useRequireAuth } from './lib/auth';
import { useAdminMetrics } from './lib/queries';

export default function DashboardPage() {
  const ready = useRequireAuth();
  const { data, isLoading, isError, error } = useAdminMetrics();

  if (!ready) return null;

  return (
    <AdminShell>
      <div className="space-y-6 p-6">
        <header>
          <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500">
            Pulse of the platform. Numbers refresh every minute while this tab is in front.
          </p>
        </header>

        {isError ? (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Failed to load metrics: {(error as Error).message}
          </p>
        ) : null}

        <section className="grid gap-3 sm:grid-cols-3">
          <MetricCard
            label="Active workspaces"
            value={data?.total_active_workspaces}
            loading={isLoading}
            href="/workspaces"
            description="Workspaces not currently suspended."
          />
          <MetricCard
            label="Registered users"
            value={data?.total_registered_users}
            loading={isLoading}
            href="/users"
            description="Total global User rows on the platform."
          />
          <MetricCard
            label="AI tokens consumed"
            value={data?.total_tokens_used}
            loading={isLoading}
            description="Sum of `tasks.tokens_used` across every workspace."
          />
        </section>

        <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Recent signups</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                New User rows created in the last 7 days, newest first.
              </p>
            </div>
            <Link href="/users" className="text-xs font-medium text-rose-700 hover:underline">
              All users →
            </Link>
          </header>
          {isLoading ? (
            <p className="px-4 py-6 text-sm text-slate-500">Loading…</p>
          ) : data && data.recent_signups.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm italic text-slate-500">
              No signups in the last 7 days.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {(data?.recent_signups ?? []).map((s) => (
                <li key={s.id} className="flex items-baseline justify-between gap-4 px-4 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">{s.full_name}</p>
                    <p className="truncate text-xs text-slate-500">{s.email}</p>
                  </div>
                  <span className="shrink-0 text-[11px] text-slate-500" title={s.created_at}>
                    {formatRelative(s.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </AdminShell>
  );
}

function MetricCard({
  label,
  value,
  loading,
  description,
  href,
}: {
  label: string;
  value: number | undefined;
  loading: boolean;
  description: string;
  href?: '/workspaces' | '/users';
}) {
  const body = (
    <div className="h-full rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm transition hover:border-rose-300 hover:bg-rose-50/30">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums text-slate-900">
        {loading ? '—' : value != null ? value.toLocaleString() : '—'}
      </p>
      <p className="mt-1 text-[11px] text-slate-500">{description}</p>
    </div>
  );
  return href ? (
    <Link href={href} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
