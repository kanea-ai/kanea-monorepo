'use client';

import { DragDropContext, Draggable, Droppable, type DropResult } from '@hello-pangea/dnd';
import { useMemo } from 'react';

import type { Task, TaskStatus } from '../lib/api';
import { useTasks, useUpdateTaskStatus } from '../lib/queries';

// Columns are the non-BLOCKED workflow states. BLOCKED is surfaced
// in the Exception Queue side panel only — it's an out-of-band state.
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
      BLOCKED: [],
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
                    className={`rounded-md border border-slate-200 bg-white p-3 text-sm shadow-sm transition-shadow ${
                      s.isDragging ? 'shadow-md ring-2 ring-indigo-300' : ''
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="font-medium text-slate-900">{task.title}</h3>
                      <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-600">
                        P{task.priority}
                      </span>
                    </div>
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
