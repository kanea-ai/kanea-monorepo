'use client';

import type { Task } from '../lib/api';
import { useBlockedTasks, useUpdateTaskStatus } from '../lib/queries';

export function ExceptionQueue() {
  const { data, isLoading, isError, error } = useBlockedTasks();
  const updateStatus = useUpdateTaskStatus();
  const tasks = data ?? [];

  const handleResolve = (taskId: string) => {
    updateStatus.mutate({
      id: taskId,
      payload: { status: 'IN_PROGRESS' },
    });
  };

  return (
    <aside className="flex h-72 shrink-0 flex-col border-t border-slate-200 bg-white lg:h-full lg:w-96 lg:border-l lg:border-t-0">
      <header className="border-b border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
            Exception Queue
          </h2>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              tasks.length > 0 ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600'
            }`}
          >
            {tasks.length}
          </span>
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
              <ExceptionCard
                key={task.id}
                task={task}
                onResolve={handleResolve}
                isResolving={updateStatus.isPending && updateStatus.variables?.id === task.id}
              />
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}

function ExceptionCard({
  task,
  onResolve,
  isResolving,
}: {
  task: Task;
  onResolve: (id: string) => void;
  isResolving: boolean;
}) {
  return (
    <li className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium text-slate-900">{task.title}</h3>
        <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-800">
          Blocked
        </span>
      </div>

      {task.blocked_reason ? (
        <div className="mt-2 rounded border border-amber-200 bg-white p-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Agent reported
          </p>
          <p className="mt-0.5 whitespace-pre-wrap break-words text-xs text-slate-800">
            {task.blocked_reason}
          </p>
        </div>
      ) : (
        <p className="mt-2 text-xs italic text-slate-500">No reason provided by the agent.</p>
      )}

      <button
        type="button"
        onClick={() => onResolve(task.id)}
        disabled={isResolving}
        className="mt-3 w-full rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isResolving ? 'Resolving…' : 'Resolve → In Progress'}
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
