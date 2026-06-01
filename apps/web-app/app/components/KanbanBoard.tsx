'use client';

import {
  DragDropContext,
  Draggable,
  Droppable,
  type DragUpdate,
  type DropResult,
} from '@hello-pangea/dnd';
import { useRouter } from 'next/navigation';
import { useCallback, useMemo, useRef, useState } from 'react';

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

  // Auto-expand + custom hit-test layer.
  //
  // Why custom hit-test: @hello-pangea/dnd snapshots droppable
  // bounding rects at drag-start and only re-measures via per-
  // droppable ResizeObservers. When a column auto-expands during
  // a drag the EXPANDED column's bounds update, but siblings
  // pushed sideways by the expansion DON'T (their own size didn't
  // change, only their position), so the lib's hit-test is anchored
  // to the pre-expand layout. Dispatching a window resize event to
  // force a full re-measure aborts the drag — the lib treats
  // resize-during-drag as a layout invalidation.
  //
  // So we ignore the lib's destination entirely and run our own
  // hit-test on each pointer move using live getBoundingClientRect()
  // values. The dragged card's *centre* is the hit point ("more than
  // half over the column" → centre is inside it). activeColumn drives
  // both the visual highlight and the eventual drop routing —
  // result.destination from the lib is never read.
  const initialCollapsedRef = useRef<Record<TaskStatus, boolean> | null>(null);
  const autoExpandedRef = useRef<Set<TaskStatus>>(new Set());
  const columnElsRef = useRef<Map<TaskStatus, HTMLElement>>(new Map());
  const draggedCardRef = useRef<HTMLElement | null>(null);
  const activeColumnRef = useRef<TaskStatus | null>(null);
  const [activeColumn, setActiveColumn] = useState<TaskStatus | null>(null);

  const setColumnEl = useCallback(
    (id: TaskStatus) => (el: HTMLElement | null) => {
      if (el) columnElsRef.current.set(id, el);
      else columnElsRef.current.delete(id);
    },
    [],
  );

  const recomputeActiveColumn = useCallback(() => {
    const card = draggedCardRef.current;
    if (!card) return;
    const r = card.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    let next: TaskStatus | null = null;
    for (const [id, el] of columnElsRef.current) {
      const cr = el.getBoundingClientRect();
      if (cx >= cr.left && cx < cr.right && cy >= cr.top && cy < cr.bottom) {
        next = id;
        break;
      }
    }
    if (next === activeColumnRef.current) return;
    activeColumnRef.current = next;
    setActiveColumn(next);

    // Auto-expand the newly-active column if it was originally
    // collapsed. Sticky: once expanded, stays open for the drag —
    // matches the rest of the column's behaviour.
    const initial = initialCollapsedRef.current;
    if (next && initial && initial[next] && !autoExpandedRef.current.has(next)) {
      autoExpandedRef.current.add(next);
      setCollapsed((prev) => (prev[next] ? { ...prev, [next]: false } : prev));
    }
  }, []);

  const moveListenerRef = useRef<(() => void) | null>(null);

  const onDragStart = (start: { draggableId: string }) => {
    draggingRef.current = true;
    initialCollapsedRef.current = { ...collapsed };
    autoExpandedRef.current = new Set();
    activeColumnRef.current = null;
    setActiveColumn(null);
    // The lib applies position:fixed + transform to the dragged
    // article. Find it once after the lib has wired up the clone.
    requestAnimationFrame(() => {
      draggedCardRef.current = document.querySelector<HTMLElement>(
        `[data-rfd-draggable-id="${start.draggableId}"]`,
      );
      recomputeActiveColumn();
    });
    // The lib's onDragUpdate doesn't always fire when the cursor
    // moves but no destination changes (its destination is stale).
    // Listen on the document so we get every mouse / touch move.
    const onMove = () => recomputeActiveColumn();
    document.addEventListener('mousemove', onMove, true);
    document.addEventListener('touchmove', onMove, { capture: true, passive: true });
    moveListenerRef.current = () => {
      document.removeEventListener('mousemove', onMove, true);
      document.removeEventListener('touchmove', onMove, true);
    };
  };

  const onDragUpdate = (_update: DragUpdate) => {
    // The lib's onDragUpdate fires on cursor move and column shift.
    // We piggy-back to refresh our own hit-test against current rects.
    recomputeActiveColumn();
  };

  const onDragEnd = (result: DropResult) => {
    // The drop completes synchronously; defer the click-suppression
    // release one tick so the synthetic click that follows the drop
    // sees draggingRef=true and bails.
    setTimeout(() => {
      draggingRef.current = false;
    }, 0);

    // Tear down the document-level move listeners.
    moveListenerRef.current?.();
    moveListenerRef.current = null;

    const expanded = autoExpandedRef.current;
    const ourDest = activeColumnRef.current;
    initialCollapsedRef.current = null;
    autoExpandedRef.current = new Set();
    activeColumnRef.current = null;
    setActiveColumn(null);
    draggedCardRef.current = null;
    const { source, draggableId } = result;
    const droppedInto = ourDest;

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

    if (!ourDest) return;
    if (ourDest === source.droppableId) return;

    updateStatus.mutate({ id: draggableId, payload: { status: ourDest } });
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
        {/* Fit-to-screen accordion. No horizontal scroll, no rigid
            pixel widths on the columns — expanded columns are pure
            ``flex-1`` and so split the available width evenly. As the
            user expands or collapses columns the others fluidly
            squeeze / grow within the same row. Collapsed columns are
            a narrow rail just wide enough for the rotated title +
            chevron + count badge.

            Notes:
            - ``w-full`` (no ``overflow-x-auto``) is the contract: the
              row must never push past its parent. Cards inside use
              ``min-w-0`` + ``truncate`` so they degrade gracefully
              when a column gets very narrow.
            - ``min-h-0`` on the row lets it shrink to its parent's
              height so the (per-column) vertical scroll lives inside
              the parent's ``overflow-auto`` wrapper. */}
        <div className="flex h-full min-h-0 w-full items-start gap-3 p-3 sm:p-4 md:p-6">
          {COLUMNS.map((col) => (
            <Column
              key={col.id}
              id={col.id}
              label={col.label}
              tasks={grouped[col.id]}
              isCollapsed={collapsed[col.id]}
              onToggle={() => toggleColumn(col.id)}
              onCardClick={onCardClick}
              isActiveDropTarget={activeColumn === col.id}
              setOuterRef={setColumnEl(col.id)}
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
  const { data: teamsPage } = useTeams();
  const teams = teamsPage?.items ?? [];
  const { data: projectsPage } = useProjects();
  const projects = projectsPage?.items ?? [];
  const { data: membersPage } = useMembers();
  const members = membersPage?.items ?? [];
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

  const teamOptions = useMemo(() => teams.map((t) => ({ value: t.id, label: t.name })), [teams]);
  const projectOptions = useMemo(
    () => projects.map((p) => ({ value: p.id, label: p.name })),
    [projects],
  );
  const memberOptions = useMemo(
    () =>
      members.map((m) => ({
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
  isActiveDropTarget,
  setOuterRef,
}: {
  id: TaskStatus;
  label: string;
  tasks: Task[];
  isCollapsed: boolean;
  onToggle: () => void;
  onCardClick: (taskId: string) => void;
  isActiveDropTarget: boolean;
  setOuterRef: (el: HTMLElement | null) => void;
}) {
  // Fit-to-screen accordion layout:
  //
  //   - Collapsed columns hold a fixed 3-rem rail (48px). ``shrink-0``
  //     keeps them from being absorbed by the ``flex-1`` neighbours.
  //   - Expanded columns are pure ``flex-1 min-w-[150px]``. They have
  //     no fixed width; instead they split the parent row's remaining
  //     space evenly. Expand a fourth column and the existing three
  //     squeeze from 33% → 25% each. ``min-w-[150px]`` is the floor
  //     so cards stay readable down to 13" laptop widths.
  //
  // No horizontal scroll, no off-screen columns — the cost is that
  // very narrow viewports (under ~800px content area) will clip the
  // rightmost column. That's an intentional trade — see the comment
  // on the row wrapper for the design rationale.
  //
  // The active-drop-target highlight is driven by the parent's
  // custom hit-test (KanbanBoard.activeColumn), NOT by the dnd
  // lib's snapshot.isDraggingOver — see the long-form note in
  // KanbanBoard for the rationale. The lib's snapshot is read for
  // the placeholder slot only; everything user-visible follows our
  // own hit-test.
  const widthClass = isCollapsed ? 'w-12 shrink-0' : 'min-w-[150px] flex-1';
  return (
    <Droppable droppableId={id}>
      {(provided) => (
        <div
          ref={setOuterRef}
          className={`flex min-h-0 min-w-0 flex-col rounded-lg p-2 transition-all duration-300 ease-out ${widthClass} ${
            isActiveDropTarget
              ? 'bg-indigo-100 ring-2 ring-indigo-500 ring-offset-2 ring-offset-slate-50'
              : 'bg-slate-100'
          }`}
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
              className={`text-[10px] text-slate-500 transition-transform duration-300 ${
                isCollapsed ? '' : 'rotate-90'
              }`}
            >
              ▶
            </span>
            <h2
              className={`text-sm font-semibold uppercase tracking-wide ${
                isActiveDropTarget ? 'text-indigo-700' : 'text-slate-600'
              } ${
                isCollapsed
                  ? 'rotate-180 whitespace-nowrap [writing-mode:vertical-rl]'
                  : 'min-w-0 flex-1 truncate'
              }`}
            >
              {label}
            </h2>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                isActiveDropTarget ? 'bg-indigo-200 text-indigo-800' : 'bg-slate-200 text-slate-700'
              } ${isCollapsed ? '' : 'ml-auto'}`}
            >
              {tasks.length}
            </span>
          </button>
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className={`flex flex-1 flex-col gap-1.5 rounded-md transition-all duration-300 ease-out ${
              isCollapsed ? 'min-h-[80px] p-0.5' : 'min-h-[200px] p-1'
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
                        {task.cross_team_origin ? (
                          <p className="mt-1 inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-indigo-700">
                            ↗ from {task.cross_team_origin.source_task_public_id}
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
            {/* The lib's placeholder is hidden because its destination
                may disagree with our hit-test (siblings shift on
                expand). Keep it mounted so the lib's invariants hold,
                but render zero visual footprint. */}
            <div className="hidden">{provided.placeholder}</div>
          </div>
        </div>
      )}
    </Droppable>
  );
}
