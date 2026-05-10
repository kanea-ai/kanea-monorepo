'use client';

import { useEffect, useState } from 'react';

import { CreateTaskDialog } from '../../components/CreateTaskDialog';
import { ExceptionQueue } from '../../components/ExceptionQueue';
import { KanbanBoard } from '../../components/KanbanBoard';

// Persist the user's preference across reloads. SessionStorage is
// per-tab; localStorage is what the user actually expects ("I closed
// the rail yesterday, leave it closed").
const COLLAPSE_KEY = 'kanea_exception_queue_collapsed';

export default function BoardPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [queueCollapsed, setQueueCollapsed] = useState(false);
  // The board renders before localStorage hydrates, so initial paint
  // is "expanded". The effect rehydrates on mount; SSR doesn't have
  // localStorage so this is the cleanest split.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = window.localStorage.getItem(COLLAPSE_KEY);
    if (stored === '1') setQueueCollapsed(true);
  }, []);
  const toggleQueue = () => {
    setQueueCollapsed((v) => {
      const next = !v;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0');
      } catch {
        // localStorage is best-effort — Safari private mode etc.
      }
      return next;
    });
  };

  return (
    <div className="flex h-[calc(100vh-3.25rem)] flex-col lg:h-screen lg:flex-row">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Board</h1>
            <p className="text-xs text-slate-500">
              Drag cards across columns to update status. Blocked tasks live in the Exception Queue.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            New task
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto">
          <KanbanBoard />
        </div>
      </section>
      <ExceptionQueue collapsed={queueCollapsed} onToggle={toggleQueue} />
      <CreateTaskDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
