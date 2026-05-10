'use client';

import {
  DragDropContext,
  Draggable,
  Droppable,
  type DragUpdate,
  type DropResult,
} from '@hello-pangea/dnd';
import { useRouter } from 'next/navigation';
import { useMemo, useRef, useState } from 'react';

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

  const router = useRouter();
  // Drag-vs-click guard: cards' onClick fires before dnd's onDragEnd
  // when the user actually finished dragging in some browsers, even
  // though the click is logically "the drop". The ref is set in
  // onDragStart and cleared shortly after onDragEnd; the card's
  // click handler bails if it sees a recent drag.
  const draggingRef = useRef(false);
  const onCardClick = (taskId: string) => {
    if (draggingRef.current) return;
    router.push(`/tasks/${taskId}`);
  };

  // Auto-expand columns when the drag hovers over them, and keep
  // them expanded until the drag ends — even if the user moves the
  // cursor to a different column. The earlier "hover-only" version
  // collapsed columns the moment the cursor left, which made the
  // board feel jittery during a drag. Sticky expansion gives the
  // user a stable layout to aim at.
  //
  // We snapshot the pre-drag collapsed state, accumulate every
  // collapsed column the drag visits in autoExpandedRef, and on
  // drag-end restore the snapshot — except for the column the user
  // actually dropped into, which stays expanded so they see the
  // card land.
  const initialCollapsedRef = useRef<Record<TaskStatus, boolean> | null>(null);
  const autoExpandedRef = useRef<Set<TaskStatus>>(new Set());

  const onDragStart = () => {
    draggingRef.current = true;
    initialCollapsedRef.current = { ...collapsed };
    autoExpandedRef.current = new Set();
  };

  const onDragUpdate = (update: DragUpdate) => {
    const initial = initialCollapsedRef.current;
    if (!initial) return;
    const destId = update.destination?.droppableId as TaskStatus | undefined;
    if (!destId) return;
    // Only auto-expand columns that were originally collapsed. If
    // it was already expanded by the user, leave it alone — and
    // don't track it for collapse on drag-end.
    if (!initial[destId]) return;
    if (autoExpandedRef.current.has(destId)) return;
    autoExpandedRef.current.add(destId);
    setCollapsed((prev) => (prev[destId] ? { ...prev, [destId]: false } : prev));
    // Once layout has settled (one rAF after the React state flush),
    // nudge dnd to recompute every droppable's bounds. The lib's
    // ResizeObserver only watches each droppable individually, so
    // a sibling expansion (which shifts other columns sideways but
    // doesn't change THEIR sizes) wouldn't otherwise be picked up
    // and the cursor-to-droppable hit test stays anchored to the
    // pre-expand layout.
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
  };

  const onDragEnd = (result: DropResult) => {
    // The drop completes synchronously; defer the click-suppression
    // release one tick so the synthetic click that follows the drop
    // sees draggingRef=true and bails.
    setTimeout(() => {
      draggingRef.current = false;
    }, 0);

    const expanded = autoExpandedRef.current;
    initialCollapsedRef.current = null;
    autoExpandedRef.current = new Set();
    const { destination, source, draggableId } = result;
    const droppedInto = destination?.droppableId as TaskStatus | undefined;

    // Re-collapse every column we auto-expanded — except the one
    // that received the drop. Keeping the destination open means
    // the user sees the moved card land in its new column.
    if (expanded.size > 0) {
      setCollapsed((prev) => {
        const next = { ...prev };
        let changed = false;
        for (const id of expanded) {
          if (id === droppedInto) continue;
          if (!next[id]) {
            next[id] = true;
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }

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
      <DragDropContext onDragStart={onDragStart} onDragUpdate={onDragUpdate} onDragEnd={onDragEnd}>
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
              onCardClick={onCardClick}
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

  const active =
    filters.teamId ||
    filters.projectId ||
    filters.assigneeId ||
    filters.blockedOnly ||
    filters.priorityMin != null ||
    filters.priorityMax != null;

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

      <span className="ml-2 inline-flex items-center gap-1 text-[11px] text-slate-700">
        <span className="text-slate-500">Priority</span>
        <select
          value={filters.priorityMin ?? ''}
          onChange={(e) =>
            set('priorityMin', e.target.value === '' ? undefined : Number(e.target.value))
          }
          className="rounded border border-slate-300 px-1 py-0.5 text-[11px]"
        >
          <option value="">≥ any</option>
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              ≥ P{n}
            </option>
          ))}
        </select>
        <select
          value={filters.priorityMax ?? ''}
          onChange={(e) =>
            set('priorityMax', e.target.value === '' ? undefined : Number(e.target.value))
          }
          className="rounded border border-slate-300 px-1 py-0.5 text-[11px]"
        >
          <option value="">≤ any</option>
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              ≤ P{n}
            </option>
          ))}
        </select>
      </span>

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
  onCardClick,
}: {
  id: TaskStatus;
  label: string;
  tasks: Task[];
  isCollapsed: boolean;
  onToggle: () => void;
  onCardClick: (taskId: string) => void;
}) {
  // Collapsed columns are a 5-rem rail (was 3rem). Wider gives the
  // user a bigger drop target when aiming a dragged card at a
  // collapsed column.
  //
  // Width changes are NOT transitioned — @hello-pangea/dnd
  // measures droppable positions at drag-start and re-measures via
  // ResizeObserver. A smooth width transition fires the observer
  // dozens of times during the animation but the drag's
  // hit-testing reads the cached positions in between, which is
  // how the cursor ends up offset from the highlighted column.
  // Snapping the width keeps the lib's measurements aligned with
  // what the user sees. The bg / ring highlight still fades
  // smoothly because those are color transitions only.
  const widthClass = isCollapsed ? 'w-20 md:w-20 shrink-0' : 'w-72 shrink-0 md:w-72 md:flex-1';
  return (
    <div
      className={`flex min-h-0 snap-start flex-col rounded-lg bg-slate-100 p-2 transition-colors duration-200 ease-out ${widthClass}`}
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
      {/* The Droppable always mounts — dnd needs it in the tree to
          fire onDragUpdate when the user hovers a collapsed column,
          which is what triggers the auto-expand-on-hover behaviour
          in the parent. When collapsed, the inner area shrinks to
          a tiny strip but still accepts the drop. */}
      <Droppable droppableId={id}>
        {(provided, snapshot) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className={`flex flex-1 flex-col gap-1.5 rounded-md transition-all duration-200 ease-out ${
              isCollapsed ? 'min-h-[80px] p-0.5' : 'min-h-[200px] p-1'
            } ${
              snapshot.isDraggingOver
                ? 'bg-indigo-100/80 ring-2 ring-indigo-400 ring-offset-1 ring-offset-slate-100'
                : ''
            }`}
          >
            {/* When collapsed, hide the cards but keep the
                  Droppable space so the drop target is still reach-
                  able. The card list re-renders the moment the
                  parent toggles isCollapsed false. */}
            {isCollapsed
              ? null
              : tasks.map((task, index) => (
                  <Draggable key={task.id} draggableId={task.id} index={index}>
                    {(p, s) => (
                      // Whole card is clickable. dnd treats mousedown as
                      // a press that becomes a drag only after movement;
                      // a pure click leaves dragHandleProps' onMouseUp
                      // unchanged and our onClick fires. After a real
                      // drag, the parent's draggingRef is true so the
                      // click-handler bails — see KanbanBoard.onCardClick.
                      <article
                        ref={p.innerRef}
                        {...p.draggableProps}
                        {...p.dragHandleProps}
                        role="button"
                        tabIndex={0}
                        onClick={() => onCardClick(task.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onCardClick(task.id);
                          }
                        }}
                        className={`cursor-pointer rounded-md border bg-white px-2 py-1.5 text-xs shadow-sm transition-shadow hover:border-indigo-300 hover:shadow ${
                          task.is_blocked
                            ? 'border-red-300 bg-red-50/50 ring-1 ring-red-200'
                            : 'border-slate-200'
                        } ${s.isDragging ? 'cursor-grabbing shadow-md ring-2 ring-indigo-300' : ''}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <p className="font-mono text-[9px] font-medium uppercase tracking-wide text-slate-400">
                              {task.public_id}
                            </p>
                            <h3 className="truncate text-[13px] font-medium leading-snug text-slate-900">
                              {task.title}
                            </h3>
                          </div>
                          <span className="shrink-0 rounded bg-slate-100 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide text-slate-600">
                            P{task.priority}
                          </span>
                        </div>
                        {task.is_blocked ? (
                          <p className="mt-1 inline-flex items-center gap-1 rounded-full border border-red-300 bg-red-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-red-800">
                            <span className="h-1 w-1 rounded-full bg-red-500" />
                            Blocked
                          </p>
                        ) : null}
                        {task.description ? (
                          <p className="mt-0.5 line-clamp-1 text-[11px] text-slate-500">
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
    </div>
  );
}
