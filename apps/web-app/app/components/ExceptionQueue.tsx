'use client';

import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';

import type { Task } from '../lib/api';
import { tasksApi } from '../lib/api';
import { taskKeys, useBlockedTasks } from '../lib/queries';

export function ExceptionQueue({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { data, isLoading, isError, error } = useBlockedTasks();
  const qc = useQueryClient();
  const tasks = data ?? [];

  const handleResolve = async (taskId: string) => {
    // Resolving = clearing the blocked flag. Status is untouched —
    // unblocking a PENDING task leaves it PENDING; an IN_PROGRESS
    // task stays in progress.
    await tasksApi.setBlocked(taskId, { is_blocked: false });
    qc.invalidateQueries({ queryKey: taskKeys.all });
  };

  // Collapsed state is a thin vertical rail (desktop) / a single
  // pill (mobile, which lives below the board). Either way the
  // toggle button surfaces the count + an amber dot when there's
  // unresolved work, so the user doesn't need to expand to know
  // they have exceptions waiting.
  if (collapsed) {
    return <CollapsedRail count={tasks.length} onExpand={onToggle} />;
  }

  return (
    <aside className="flex h-72 shrink-0 flex-col border-t border-slate-200 bg-white lg:h-full lg:w-96 lg:border-l lg:border-t-0">
      <header className="border-b border-slate-200 p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
            Exception Queue
          </h2>
          <div className="flex items-center gap-1.5">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                tasks.length > 0 ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600'
              }`}
            >
              {tasks.length}
            </span>
            <button
              type="button"
              aria-label="Collapse exception queue"
              onClick={onToggle}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Tasks an agent could not complete. Review the reason and resolve to put the task back in
          progress.
        </p>
      </header>

      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading exceptions…</p>
        ) : isError ? (
          <p className="text-sm text-red-600">
            Failed to load exceptions: {(error as Error).message}
          </p>
        ) : tasks.length === 0 ? (
          <EmptyState />
        ) : (
          <ul className="space-y-3">
            {tasks.map((task) => (
              <ExceptionCard key={task.id} task={task} onResolve={handleResolve} />
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}

function CollapsedRail({ count, onExpand }: { count: number; onExpand: () => void }) {
  // Desktop: thin vertical rail along the right edge. Mobile: a small
  // bar across the top of where the panel would be. Both share the
  // same toggle button + count badge with an amber pulse when count
  // > 0 so unresolved work surfaces without sacrificing board space.
  const hasExceptions = count > 0;
  return (
    <aside
      className="flex shrink-0 items-stretch border-t border-slate-200 bg-white lg:w-10 lg:flex-col lg:border-l lg:border-t-0"
      aria-label="Exception queue collapsed"
    >
      <button
        type="button"
        onClick={onExpand}
        aria-label={
          hasExceptions ? `Expand exception queue (${count} pending)` : 'Expand exception queue'
        }
        className="group relative flex w-full items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 lg:flex-col lg:gap-3 lg:py-4"
      >
        <ChevronLeft className="h-4 w-4 text-slate-400 group-hover:text-slate-600" />
        <span className="lg:rotate-180 lg:[writing-mode:vertical-rl]">Exceptions</span>
        {hasExceptions ? (
          <span
            className="absolute right-1.5 top-1.5 inline-flex min-w-[1.1rem] items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white shadow-sm lg:right-1.5 lg:top-1.5"
            aria-hidden="true"
          >
            {count > 99 ? '99+' : count}
          </span>
        ) : null}
        {hasExceptions ? (
          // Subtle pulsing dot underneath the badge — visible even at
          // a glance from across the room.
          <span
            aria-hidden="true"
            className="absolute right-1.5 top-1.5 h-4 w-4 animate-ping rounded-full bg-amber-400 opacity-60"
          />
        ) : null}
      </button>
    </aside>
  );
}

function ChevronRight({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function ChevronLeft({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function ExceptionCard({
  task,
  onResolve,
}: {
  task: Task;
  onResolve: (id: string) => Promise<void>;
}) {
  return (
    <li className="rounded-lg border border-red-200 bg-red-50/60 p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/tasks/${task.id}`} className="min-w-0 flex-1">
          <p className="font-mono text-[10px] font-medium uppercase text-slate-400">
            {task.public_id}
          </p>
          <h3 className="truncate text-sm font-medium text-slate-900 hover:text-indigo-700">
            {task.title}
          </h3>
        </Link>
        <span className="shrink-0 rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-red-800">
          Blocked
        </span>
      </div>

      {task.blocked_reason ? (
        <div className="mt-2 rounded border border-red-200 bg-white p-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Reason</p>
          <p className="mt-0.5 whitespace-pre-wrap break-words text-xs text-slate-800">
            {task.blocked_reason}
          </p>
        </div>
      ) : (
        <p className="mt-2 text-xs italic text-slate-500">No reason provided.</p>
      )}

      <button
        type="button"
        onClick={() => onResolve(task.id)}
        className="mt-3 w-full rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
      >
        Unblock
      </button>
    </li>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 p-6 text-center">
      <p className="text-sm font-medium text-slate-700">All clear.</p>
      <p className="mt-1 text-xs text-slate-500">No blocked tasks waiting on a human.</p>
    </div>
  );
}
