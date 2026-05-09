'use client';

import { DragDropContext, Draggable, Droppable, type DropResult } from '@hello-pangea/dnd';
import Link from 'next/link';
import { useMemo } from 'react';

import type { Task, TaskStatus } from '../lib/api';
import { useTasks, useUpdateTaskStatus } from '../lib/queries';

// Status is the lifecycle column; being blocked is orthogonal and shown
// as a red border on the card regardless of which column it sits in.
const COLUMNS: { id: TaskStatus; label: string }[] = [
  { id: 'PENDING', label: 'Pending' },
  { id: 'IN_PROGRESS', label: 'In Progress' },
  { id: 'DONE', label: 'Done' },
  { id: 'CANCELLED', label: 'Cancelled' },
];

export function KanbanBoard() {
  const { data, isLoading, isError, error } = useTasks();
  const updateStatus = useUpdateTaskStatus();

  const grouped = useMemo(() => {
    const buckets: Record<TaskStatus, Task[]> = {
      PENDING: [],
      IN_PROGRESS: [],
      DONE: [],
      CANCELLED: [],
    };
    for (const task of data ?? []) buckets[task.status].push(task);
    return buckets;
  }, [data]);

  const onDragEnd = (result: DropResult) => {
    const { destination, source, draggableId } = result;
    if (!destination) return;
    if (destination.droppableId === source.droppableId) return;

    const nextStatus = destination.droppableId as TaskStatus;
    updateStatus.mutate({ id: draggableId, payload: { status: nextStatus } });
  };

  if (isLoading) {
    return <div className="p-6 text-sm text-slate-500">Loading board…</div>;
  }
  if (isError) {
    return (
      <div className="p-6 text-sm text-red-600">
        Failed to load tasks: {(error as Error).message}
      </div>
    );
  }

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      {/* Below md, columns scroll horizontally so each one stays usable
          (a 4-col grid would crush them at phone widths). At md+ we
          go back to an even grid. */}
      <div className="flex h-full snap-x snap-mandatory gap-3 overflow-x-auto p-3 sm:p-4 md:grid md:snap-none md:grid-cols-4 md:gap-4 md:overflow-visible md:p-6">
        {COLUMNS.map((col) => (
          <Column key={col.id} id={col.id} label={col.label} tasks={grouped[col.id]} />
        ))}
      </div>
    </DragDropContext>
  );
}

function Column({ id, label, tasks }: { id: TaskStatus; label: string; tasks: Task[] }) {
  return (
    <div className="flex min-h-0 w-72 shrink-0 snap-start flex-col rounded-lg bg-slate-100 p-3 md:w-auto md:shrink">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">{label}</h2>
        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700">
          {tasks.length}
        </span>
      </div>
      <Droppable droppableId={id}>
        {(provided, snapshot) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className={`flex min-h-[200px] flex-1 flex-col gap-2 rounded-md p-1 transition-colors ${
              snapshot.isDraggingOver ? 'bg-slate-200/70' : ''
            }`}
          >
            {tasks.map((task, index) => (
              <Draggable key={task.id} draggableId={task.id} index={index}>
                {(p, s) => (
                  <article
                    ref={p.innerRef}
                    {...p.draggableProps}
                    {...p.dragHandleProps}
                    className={`rounded-md border bg-white p-3 text-sm shadow-sm transition-shadow ${
                      task.is_blocked
                        ? 'border-red-300 bg-red-50/50 ring-1 ring-red-200'
                        : 'border-slate-200'
                    } ${s.isDragging ? 'shadow-md ring-2 ring-indigo-300' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={`/tasks/${task.id}`}
                        // Stop drag handler from claiming the click — the
                        // dnd library calls preventDefault on parent click
                        // events, so we explicitly stopPropagation here.
                        onClick={(e) => e.stopPropagation()}
                        className="min-w-0 flex-1"
                      >
                        <p className="font-mono text-[10px] font-medium uppercase text-slate-400">
                          {task.public_id}
                        </p>
                        <h3 className="truncate font-medium text-slate-900 hover:text-indigo-700">
                          {task.title}
                        </h3>
                      </Link>
                      <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-600">
                        P{task.priority}
                      </span>
                    </div>
                    {task.is_blocked ? (
                      <p className="mt-1 inline-flex items-center gap-1 rounded-full border border-red-300 bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                        <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
                        Blocked{task.blocked_reason ? ` — ${task.blocked_reason}` : ''}
                      </p>
                    ) : null}
                    {task.description ? (
                      <p className="mt-1 line-clamp-2 text-xs text-slate-500">{task.description}</p>
                    ) : null}
                  </article>
                )}
              </Draggable>
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </div>
  );
}
