'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';

import type { Task } from '../../lib/api';
import { useBlockedTasks, useUpdateTaskStatus } from '../../lib/queries';

export default function BlockedPage() {
  const { data, isLoading, isError, error } = useBlockedTasks();
  const tasks = data ?? [];

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Blocked tasks</h1>
          <p className="text-sm text-slate-500">
            Work flagged as blocked by an agent or teammate. Review the reason and either unblock or
            cancel.
          </p>
        </div>
        <Link
          href="/board"
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        >
          ← Back to board
        </Link>
      </header>

      {isError ? (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Failed to load blocked tasks: {(error as Error).message}
        </p>
      ) : isLoading ? (
        <SkeletonList />
      ) : tasks.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="space-y-3">
          {tasks.map((t) => (
            <BlockedTaskCard key={t.id} task={t} />
          ))}
        </ul>
      )}
    </div>
  );
}

function BlockedTaskCard({ task }: { task: Task }) {
  const updateStatus = useUpdateTaskStatus();
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  const isUpdating = updateStatus.isPending && updateStatus.variables?.id === task.id;

  const onResume = (e: FormEvent) => {
    e.preventDefault();
    updateStatus.mutate({ id: task.id, payload: { status: 'IN_PROGRESS' } });
  };

  const onCancel = () => {
    updateStatus.mutate({ id: task.id, payload: { status: 'CANCELLED' } });
    setConfirmingCancel(false);
  };

  return (
    <li className="rounded-lg border border-amber-200 bg-white shadow-sm">
      {/* Title + reason are wrapped in a Link so the user can click
          almost anywhere on the row to open the task. The action
          footer below is intentionally outside the Link so the
          Resume / Cancel buttons don't double-fire navigation. */}
      <Link href={`/tasks/${task.id}`} className="block transition-colors hover:bg-slate-50">
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <div className="min-w-0">
            <p className="font-mono text-[10px] font-medium uppercase text-slate-400">
              {task.public_id}
            </p>
            <h2 className="truncate text-base font-semibold text-slate-900 hover:text-indigo-700">
              {task.title}
            </h2>
            {task.description ? (
              <p className="mt-1 line-clamp-2 text-sm text-slate-600">{task.description}</p>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-800">
              Blocked
            </span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-600">
              P{task.priority}
            </span>
          </div>
        </header>

        <div className="px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Reason</p>
          {task.blocked_reason ? (
            <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-800">
              {task.blocked_reason}
            </p>
          ) : (
            <p className="mt-1 text-sm italic text-slate-500">
              No reason provided. Consider asking before unblocking.
            </p>
          )}
        </div>
      </Link>

      <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 px-4 py-3">
        {confirmingCancel ? (
          <>
            <span className="mr-auto text-xs text-slate-600">Cancel this task — are you sure?</span>
            <button
              type="button"
              onClick={() => setConfirmingCancel(false)}
              disabled={isUpdating}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              Keep
            </button>
            <button
              type="button"
              onClick={onCancel}
              disabled={isUpdating}
              className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-red-700 disabled:opacity-60"
            >
              Cancel task
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setConfirmingCancel(true)}
              disabled={isUpdating}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              Cancel task
            </button>
            <button
              type="submit"
              onClick={onResume}
              disabled={isUpdating}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
            >
              {isUpdating ? 'Updating…' : 'Resume → In Progress'}
            </button>
          </>
        )}
      </footer>
    </li>
  );
}

function SkeletonList() {
  return (
    <ul className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <li key={i} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
          <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-slate-100" />
          <div className="mt-3 h-12 animate-pulse rounded bg-slate-50" />
        </li>
      ))}
    </ul>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-white p-10 text-center">
      <p className="text-sm font-medium text-slate-700">All clear.</p>
      <p className="mt-1 text-xs text-slate-500">
        No tasks are currently blocked. Agents will surface them here when they need help.
      </p>
    </div>
  );
}
