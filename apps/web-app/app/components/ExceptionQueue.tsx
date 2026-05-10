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

  // Hidden state: no rail at all — just a small floating toggle
  // anchored middle-right by the parent. This component renders only
  // the button; the parent decides where to place it. Returning a
  // fragment with the bare button keeps the kanban full-width and
  // avoids any overflow-induced scrollbar bouncing the rail used to
  // cause.
  if (collapsed) {
    return <FloatingToggle count={tasks.length} onExpand={onToggle} />;
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
          Tasks an agent or teammate flagged as blocked. Review the reason and unblock once the
          dependency is cleared.
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

function FloatingToggle({ count, onExpand }: { count: number; onExpand: () => void }) {
  // Floating expander, pinned middle-right of the board's main
  // container by the parent (`fixed-right-0 top-1/2`). Compact
  // enough to be unobtrusive but explicit about the count, so the
  // user can see pending exceptions without giving up board space
  // for a permanent rail.
  const hasExceptions = count > 0;
  const colour = hasExceptions
    ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-lg shadow-amber-500/30'
    : 'bg-white text-slate-600 hover:bg-slate-50 shadow-md ring-1 ring-slate-200';
  return (
    <button
      type="button"
      onClick={onExpand}
      aria-label={
        hasExceptions ? `Show exception queue (${count} pending)` : 'Show exception queue'
      }
      title={
        hasExceptions ? `${count} pending exception${count === 1 ? '' : 's'}` : 'Exception queue'
      }
      className={`fixed right-0 top-1/2 z-30 flex -translate-y-1/2 flex-col items-center gap-1 rounded-l-md py-3 pl-2 pr-1.5 text-[11px] font-semibold uppercase tracking-wide transition-colors ${colour}`}
    >
      <ChevronLeft className="h-4 w-4 opacity-80" />
      <span className="[writing-mode:vertical-rl]">Exceptions</span>
      <span
        className={`inline-flex min-w-[1.4rem] items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums ${
          hasExceptions ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'
        }`}
      >
        {count > 99 ? '99+' : count}
      </span>
    </button>
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
