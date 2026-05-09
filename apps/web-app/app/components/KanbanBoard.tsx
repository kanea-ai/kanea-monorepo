'use client';

import { DragDropContext, Draggable, Droppable, type DropResult } from '@hello-pangea/dnd';
import Link from 'next/link';
import { useMemo, useState } from 'react';

import type { Task, TaskStatus } from '../lib/api';
import { useCurrentPrincipal } from '../lib/auth';
import {
  useMembers,
  useProjects,
  useTasks,
  useTeams,
  useUpdateTaskStatus,
  type TaskListFilters,
} from '../lib/queries';
import { Combobox } from './Combobox';

// Status is the lifecycle column; being blocked is orthogonal and shown
// as a red border on the card regardless of which column it sits in.
// `defaultCollapsed` ships DONE / CANCELLED in the collapsed state on
// first paint — they pile up over time and would otherwise eat half
// the screen.
const COLUMNS: { id: TaskStatus; label: string; defaultCollapsed?: boolean }[] = [
  { id: 'PENDING', label: 'Pending' },
  { id: 'IN_PROGRESS', label: 'In Progress' },
  { id: 'IN_REVIEW', label: 'In Review' },
  { id: 'DONE', label: 'Done', defaultCollapsed: true },
  { id: 'CANCELLED', label: 'Cancelled', defaultCollapsed: true },
];

export function KanbanBoard() {
  const principal = useCurrentPrincipal();
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';

  // Section 2: only admins get the filter bar. Non-admins see only
  // their own tasks regardless of any filter the api would accept —
  // the server enforces the same rule defensively.
  const [filters, setFilters] = useState<TaskListFilters>({});
  const { data, isLoading, isError, error } = useTasks(isAdmin ? filters : {});
  const updateStatus = useUpdateTaskStatus();

  const grouped = useMemo(() => {
    const buckets: Record<TaskStatus, Task[]> = {
      PENDING: [],
      IN_PROGRESS: [],
      IN_REVIEW: [],
      DONE: [],
      CANCELLED: [],
    };
    for (const task of data ?? []) buckets[task.status].push(task);
    return buckets;
  }, [data]);

  // Collapsed-state lives at the board level so dragging a card into
  // a collapsed column auto-expands it (next render reads the new
  // state). DONE / CANCELLED start collapsed per COLUMNS config.
  const [collapsed, setCollapsed] = useState<Record<TaskStatus, boolean>>(() => {
    const init = {} as Record<TaskStatus, boolean>;
    for (const col of COLUMNS) init[col.id] = !!col.defaultCollapsed;
    return init;
  });
  const toggleColumn = (id: TaskStatus) => setCollapsed((prev) => ({ ...prev, [id]: !prev[id] }));

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
    <div className="flex h-full flex-col">
      {isAdmin ? (
        <FilterBar filters={filters} onChange={setFilters} />
      ) : (
        <div className="border-b border-slate-200 bg-white px-4 py-2 text-[11px] text-slate-500">
          Showing your tasks. Workspace admins see the full board.
        </div>
      )}
      <DragDropContext onDragEnd={onDragEnd}>
        {/* Columns flex-wise rather than equal-grid. Active columns
            stretch; collapsed ones shrink to a 12-rem rail so they
            stay usable. Below md they scroll horizontally. */}
        <div className="flex h-full snap-x snap-mandatory items-start gap-3 overflow-x-auto p-3 sm:p-4 md:snap-none md:overflow-visible md:p-6">
          {COLUMNS.map((col) => (
            <Column
              key={col.id}
              id={col.id}
              label={col.label}
              tasks={grouped[col.id]}
              isCollapsed={collapsed[col.id]}
              onToggle={() => toggleColumn(col.id)}
            />
          ))}
        </div>
      </DragDropContext>
    </div>
  );
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: TaskListFilters;
  onChange: (next: TaskListFilters) => void;
}) {
  const { data: teams } = useTeams();
  const { data: projects } = useProjects();
  const { data: members } = useMembers();
  const principal = useCurrentPrincipal();

  const set = <K extends keyof TaskListFilters>(key: K, value: TaskListFilters[K]) => {
    onChange({ ...filters, [key]: value === '' ? undefined : value });
  };

  // "Assigned to me" pins the assignee filter to the principal's
  // member_id. We treat the checkbox as a derived view of the filter:
  // checked iff assigneeId == me. Toggling it on overwrites whatever
  // the combobox had; toggling off clears the filter.
  const me = principal?.member_id ?? null;
  const isAssignedToMe = me != null && filters.assigneeId === me;
  const toggleAssignedToMe = (next: boolean) => {
    if (next && me) set('assigneeId', me);
    else set('assigneeId', undefined);
  };

  const teamOptions = useMemo(
    () => (teams ?? []).map((t) => ({ value: t.id, label: t.name })),
    [teams],
  );
  const projectOptions = useMemo(
    () => (projects ?? []).map((p) => ({ value: p.id, label: p.name })),
    [projects],
  );
  const memberOptions = useMemo(
    () =>
      (members ?? []).map((m) => ({
        value: m.id,
        label: m.name,
        hint: m.type === 'AGENT' ? '(agent)' : undefined,
      })),
    [members],
  );

  const active = filters.teamId || filters.projectId || filters.assigneeId || filters.blockedOnly;

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-4 py-2 text-xs">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        Filter
      </span>

      <Combobox
        ariaLabel="Team"
        placeholder="All teams"
        options={teamOptions}
        value={filters.teamId ?? null}
        onChange={(v) => set('teamId', v ?? undefined)}
        className="w-44"
      />
      <Combobox
        ariaLabel="Project"
        placeholder="All projects"
        options={projectOptions}
        value={filters.projectId ?? null}
        onChange={(v) => set('projectId', v ?? undefined)}
        className="w-44"
      />
      <Combobox
        ariaLabel="Assignee"
        placeholder="Any assignee"
        options={memberOptions}
        value={filters.assigneeId ?? null}
        onChange={(v) => set('assigneeId', v ?? undefined)}
        className="w-48"
        disabled={isAssignedToMe}
      />
      <label className="inline-flex items-center gap-1 text-[11px] text-slate-700">
        <input
          type="checkbox"
          checked={isAssignedToMe}
          disabled={me == null}
          onChange={(e) => toggleAssignedToMe(e.target.checked)}
        />
        Assigned to me
      </label>

      <label className="ml-1 inline-flex items-center gap-1 text-[11px] text-slate-700">
        <input
          type="checkbox"
          checked={!!filters.blockedOnly}
          onChange={(e) => set('blockedOnly', e.target.checked || undefined)}
        />
        Blocked only
      </label>

      {active ? (
        <button
          type="button"
          onClick={() => onChange({})}
          className="ml-auto rounded border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
        >
          Clear
        </button>
      ) : null}
    </div>
  );
}

function Column({
  id,
  label,
  tasks,
  isCollapsed,
  onToggle,
}: {
  id: TaskStatus;
  label: string;
  tasks: Task[];
  isCollapsed: boolean;
  onToggle: () => void;
}) {
  // Collapsed columns shrink to a thin rail (just header + count).
  // The Droppable still mounts so dnd can drop into a collapsed
  // column — but we render it with min-height: 0 to keep the rail
  // tight.
  const widthClass = isCollapsed ? 'w-12 md:w-12 shrink-0' : 'w-72 shrink-0 md:w-72 md:flex-1';
  return (
    <div
      className={`flex min-h-0 snap-start flex-col rounded-lg bg-slate-100 p-2 transition-all ${widthClass}`}
    >
      <button
        type="button"
        onClick={onToggle}
        title={isCollapsed ? 'Expand column' : 'Collapse column'}
        className={`mb-2 flex items-center gap-2 rounded px-1 py-1 text-left hover:bg-slate-200/60 ${
          isCollapsed ? 'flex-col gap-1' : 'justify-between'
        }`}
      >
        <span
          aria-hidden
          className={`text-[10px] text-slate-500 transition-transform ${
            isCollapsed ? '' : 'rotate-90'
          }`}
        >
          ▶
        </span>
        <h2
          className={`whitespace-nowrap text-sm font-semibold uppercase tracking-wide text-slate-600 ${
            isCollapsed ? 'rotate-180 [writing-mode:vertical-rl]' : ''
          }`}
        >
          {label}
        </h2>
        <span
          className={`rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700 ${
            isCollapsed ? '' : 'ml-auto'
          }`}
        >
          {tasks.length}
        </span>
      </button>
      {isCollapsed ? null : (
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
                        <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                          {task.description}
                        </p>
                      ) : null}
                    </article>
                  )}
                </Draggable>
              ))}
              {provided.placeholder}
            </div>
          )}
        </Droppable>
      )}
    </div>
  );
}
