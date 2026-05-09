'use client';

import type { TaskActivity, TaskActivityType } from '../lib/api';

// Renders a chronological audit log for a task. Used on the task
// detail page (alongside the comment thread) and inside the project
// history view. The shapes here mirror the backend payload-per-event
// contract documented on TaskActivityType.

const EVENT_ICON: Record<TaskActivityType, string> = {
  CREATED: '✨',
  STATUS_CHANGED: '↻',
  ASSIGNED: '→',
  DELEGATED: '→',
  BLOCKED: '⛔',
  UNBLOCKED: '✔',
  PROJECT_CHANGED: '◇',
  TEAM_CHANGED: '◇',
  RATED: '★',
};

const EVENT_TONE: Record<TaskActivityType, string> = {
  CREATED: 'bg-slate-100 text-slate-700',
  STATUS_CHANGED: 'bg-blue-100 text-blue-800',
  ASSIGNED: 'bg-violet-100 text-violet-800',
  DELEGATED: 'bg-violet-100 text-violet-800',
  BLOCKED: 'bg-red-100 text-red-800',
  UNBLOCKED: 'bg-emerald-100 text-emerald-800',
  PROJECT_CHANGED: 'bg-slate-100 text-slate-700',
  TEAM_CHANGED: 'bg-slate-100 text-slate-700',
  RATED: 'bg-amber-100 text-amber-800',
};

export function ActivityTimeline({ activities }: { activities: TaskActivity[] }) {
  if (activities.length === 0) {
    return <p className="text-xs italic text-slate-400">No activity yet.</p>;
  }
  return (
    <ul className="space-y-2">
      {activities.map((a) => (
        <ActivityRow key={a.id} activity={a} />
      ))}
    </ul>
  );
}

function ActivityRow({ activity }: { activity: TaskActivity }) {
  return (
    <li className="flex items-start gap-2 rounded-md border border-slate-100 bg-slate-50/60 px-2 py-1.5">
      <span
        className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
          EVENT_TONE[activity.event_type] ?? 'bg-slate-100 text-slate-700'
        }`}
        aria-hidden
      >
        {EVENT_ICON[activity.event_type] ?? '·'}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-slate-800">
          <span className="font-medium">{activity.actor_name ?? 'system'}</span>{' '}
          {describe(activity)}
        </p>
        <p className="text-[10px] text-slate-400">
          {new Date(activity.created_at).toLocaleString()}
        </p>
      </div>
    </li>
  );
}

function describe(a: TaskActivity): string {
  const p = a.payload;
  switch (a.event_type) {
    case 'CREATED':
      return `created the task "${(p.title as string) ?? ''}"`;
    case 'STATUS_CHANGED':
      return `moved status from ${p.from} to ${p.to}`;
    case 'BLOCKED':
      return p.reason ? `blocked the task — ${p.reason}` : 'blocked the task';
    case 'UNBLOCKED':
      return 'unblocked the task';
    case 'DELEGATED':
      return `delegated to ${shorten(p.to as string | null)}`;
    case 'ASSIGNED':
      return `assigned to ${shorten(p.to as string | null)}`;
    case 'PROJECT_CHANGED':
      return `moved project ${shorten(p.from as string | null)} → ${shorten(p.to as string | null)}`;
    case 'TEAM_CHANGED':
      return `moved team ${shorten(p.from as string | null)} → ${shorten(p.to as string | null)}`;
    case 'RATED':
      return `rated the work ${p.score}/100${p.feedback ? ` — ${p.feedback}` : ''}`;
    default:
      return '';
  }
}

function shorten(id: string | null): string {
  if (!id) return 'none';
  return `${id.slice(0, 8)}…`;
}
