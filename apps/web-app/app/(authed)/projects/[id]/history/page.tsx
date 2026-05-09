'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';

import { ActivityTimeline } from '../../../../components/ActivityTimeline';
import type { ProjectHistorySummary, ProjectTaskHistory } from '../../../../lib/api';
import { useProjectHistory } from '../../../../lib/queries';

// Project history page. Renders the same payload an AI agent reads
// from GET /projects/{id}/history — summary aggregates plus a
// per-task expandable block with activities, comments, and rating.
// Useful for humans to spot patterns (which tasks blocked? which
// landed late? which got bad ratings?) before asking the agent.

export default function ProjectHistoryPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { data, isLoading, isError, error } = useProjectHistory(id);

  if (isLoading) return <p className="p-6 text-sm text-slate-500">Loading history…</p>;
  if (isError) {
    return (
      <p className="p-6 text-sm text-red-600">Failed to load history: {(error as Error).message}</p>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header>
        <Link href={`/projects/${id}`} className="text-xs text-slate-500 hover:text-slate-700">
          ← {data.project.name}
        </Link>
        <h1 className="mt-1 text-xl font-semibold text-slate-900">History &amp; analysis</h1>
        <p className="text-xs text-slate-500">
          Same payload an AI agent reads from{' '}
          <code className="font-mono">GET /api/v1/projects/{id}/history</code>. The agent uses this
          to reason about what went well, what blocked, and what to mitigate next time.
        </p>
      </header>

      <SummaryCard summary={data.summary} />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-900">Tasks ({data.tasks.length})</h2>
        {data.tasks.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-sm italic text-slate-500">
            No tasks in this project yet.
          </p>
        ) : (
          <ul className="space-y-2">
            {data.tasks.map((t) => (
              <li key={t.id}>
                <TaskHistoryAccordion task={t} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SummaryCard({ summary }: { summary: ProjectHistorySummary }) {
  const tiles = [
    { label: 'Total tasks', value: summary.total_tasks.toString() },
    { label: 'Pending', value: (summary.by_status.PENDING ?? 0).toString() },
    {
      label: 'In progress',
      value: (summary.by_status.IN_PROGRESS ?? 0).toString(),
    },
    { label: 'Done', value: (summary.by_status.DONE ?? 0).toString() },
    { label: 'Cancelled', value: (summary.by_status.CANCELLED ?? 0).toString() },
    {
      label: 'Blocked now',
      value: summary.blocked_now.toString(),
      tone: summary.blocked_now > 0 ? 'warn' : 'default',
    },
    {
      label: 'Avg resolution',
      value:
        summary.avg_resolution_seconds == null
          ? '—'
          : formatDuration(summary.avg_resolution_seconds),
    },
    {
      label: 'Tokens used',
      value: summary.total_tokens_used.toLocaleString(),
    },
    {
      label: 'Avg rating',
      value: summary.avg_rating == null ? '—' : `${summary.avg_rating.toFixed(0)}/100`,
    },
  ];
  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {tiles.map((t) => (
        <div
          key={t.label}
          className={`rounded-lg border p-3 shadow-sm ${
            t.tone === 'warn' ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-white'
          }`}
        >
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {t.label}
          </p>
          <p className="mt-1 text-xl font-semibold text-slate-900">{t.value}</p>
        </div>
      ))}
    </section>
  );
}

function TaskHistoryAccordion({ task }: { task: ProjectTaskHistory }) {
  return (
    <details
      className={`group rounded-lg border bg-white shadow-sm [&_summary::-webkit-details-marker]:hidden ${
        task.is_blocked ? 'border-red-200' : 'border-slate-200'
      }`}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            aria-hidden
            className="text-[10px] text-slate-400 transition-transform group-open:rotate-90"
          >
            ▶
          </span>
          <span className="font-mono text-[10px] uppercase text-slate-400">{task.public_id}</span>
          <span className="truncate text-sm font-medium text-slate-800">{task.title}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {task.is_blocked ? (
            <span className="rounded bg-red-100 px-1.5 py-0.5 text-[9px] font-medium uppercase text-red-800">
              Blocked
            </span>
          ) : null}
          <span
            className={`rounded px-1.5 py-0.5 text-[9px] font-medium uppercase ${
              task.status === 'DONE'
                ? 'bg-emerald-100 text-emerald-800'
                : task.status === 'IN_PROGRESS'
                  ? 'bg-blue-100 text-blue-800'
                  : task.status === 'CANCELLED'
                    ? 'bg-slate-100 text-slate-500'
                    : 'bg-slate-100 text-slate-700'
            }`}
          >
            {task.status.replace('_', ' ')}
          </span>
          {task.rating ? (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-medium uppercase text-amber-800">
              ★ {task.rating.score}
            </span>
          ) : null}
        </div>
      </summary>

      <div className="space-y-3 border-t border-slate-100 px-3 py-3">
        {task.description ? (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Description
            </p>
            <p className="mt-0.5 whitespace-pre-wrap text-xs text-slate-700">{task.description}</p>
          </div>
        ) : null}

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Activity ({task.activities.length})
          </p>
          <div className="mt-1">
            <ActivityTimeline activities={task.activities} />
          </div>
        </div>

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Comments ({task.comments.length})
          </p>
          {task.comments.length === 0 ? (
            <p className="mt-1 text-xs italic text-slate-400">No comments.</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {task.comments.map((c) => (
                <li
                  key={c.id}
                  className="rounded-md border border-slate-100 bg-slate-50 px-2 py-1.5 text-xs"
                >
                  <p className="font-medium text-slate-700">
                    {c.author_name ?? 'deleted'}
                    <span className="ml-2 text-[10px] font-normal text-slate-400">
                      {new Date(c.created_at).toLocaleString()}
                    </span>
                  </p>
                  <p className="mt-0.5 whitespace-pre-wrap text-slate-800">{c.body}</p>
                </li>
              ))}
            </ul>
          )}
        </div>

        {task.rating ? (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Rating
            </p>
            <p className="mt-0.5 text-xs text-slate-800">
              <span className="font-semibold">{task.rating.score}/100</span>
              {task.rating.feedback ? ` — ${task.rating.feedback}` : ''}
            </p>
          </div>
        ) : null}

        <div className="flex justify-end">
          <Link
            href={`/tasks/${task.id}`}
            className="text-[11px] font-medium text-indigo-700 hover:underline"
          >
            Open task →
          </Link>
        </div>
      </div>
    </details>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const min = seconds / 60;
  if (min < 60) return `${Math.round(min)}m`;
  const hr = min / 60;
  if (hr < 24) return `${hr.toFixed(1)}h`;
  return `${(hr / 24).toFixed(1)}d`;
}
