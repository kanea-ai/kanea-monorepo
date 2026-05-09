'use client';

import { useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useMemo, useState, type FormEvent } from 'react';

import { ApiError, tasksApi, type RelationItem, type RelationType, type Task } from '../lib/api';
import { taskKeys, useDeleteRelation, useTask, useTasks } from '../lib/queries';

// Linked work items panel. Reads relations from the embedded payload
// of GET /tasks/{id} (the same fetch that hydrates the detail page),
// so there's no second round-trip per task.

// Each option carries the relation type to store and a `swap` flag.
// "Inverse" options describe a relation whose canonical row is
// stored in the *opposite* direction — when the user picks one, we
// swap source/target on the POST so the row lands in the right form.
//
// Concretely: "Is blocked by [B]" on task A means "B blocks A" on the
// wire — so we POST to /tasks/B/relations with target=A, type=BLOCKS.
type RelationOption = {
  value: string;
  label: string;
  type: RelationType;
  swap: boolean;
};

const RELATION_OPTIONS: RelationOption[] = [
  { value: 'BLOCKS', label: 'Blocks', type: 'BLOCKS', swap: false },
  { value: 'BLOCKED_BY', label: 'Is blocked by', type: 'BLOCKS', swap: true },
  { value: 'MITIGATES', label: 'Mitigates', type: 'MITIGATES', swap: false },
  { value: 'MITIGATED_BY', label: 'Is mitigated by', type: 'MITIGATES', swap: true },
  { value: 'DUPLICATES', label: 'Is duplicate of', type: 'DUPLICATES', swap: false },
  { value: 'DUPLICATED_BY', label: 'Is duplicated by', type: 'DUPLICATES', swap: true },
  { value: 'RELATES_TO', label: 'Relates to', type: 'RELATES_TO', swap: false },
];

const GROUP_LABELS: { key: keyof BucketMap; label: string; tone: Tone }[] = [
  { key: 'blocked_by', label: 'Blocked by', tone: 'warn' },
  { key: 'blocks', label: 'Blocks', tone: 'warn' },
  { key: 'mitigated_by', label: 'Mitigated by', tone: 'info' },
  { key: 'mitigates', label: 'Mitigates', tone: 'info' },
  { key: 'duplicates', label: 'Duplicate of', tone: 'muted' },
  { key: 'duplicated_by', label: 'Duplicated by', tone: 'muted' },
  { key: 'relates_to', label: 'Relates to', tone: 'default' },
];

type Tone = 'default' | 'info' | 'warn' | 'muted';

type BucketMap = {
  blocks: RelationItem[];
  blocked_by: RelationItem[];
  mitigates: RelationItem[];
  mitigated_by: RelationItem[];
  duplicates: RelationItem[];
  duplicated_by: RelationItem[];
  relates_to: RelationItem[];
};

export function TaskRelationsPanel({ taskId }: { taskId: string }) {
  // Read relations from the detail cache — same fetch that the rest
  // of the page already triggered, no second round-trip.
  const { data: task, isLoading, isError, error } = useTask(taskId);
  const relations = task?.relations;

  const totalCount = useMemo(() => {
    if (!relations) return 0;
    return GROUP_LABELS.reduce((sum, { key }) => sum + relations[key].length, 0);
  }, [relations]);

  return (
    <details
      open
      className="group rounded-lg border border-slate-200 bg-white shadow-sm [&_summary::-webkit-details-marker]:hidden"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="text-[10px] text-slate-400 transition-transform group-open:rotate-90"
          >
            ▶
          </span>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-700">
            Linked work items
          </h2>
          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
            {totalCount}
          </span>
        </div>
      </summary>

      <div className="px-3 py-2">
        {isLoading ? (
          <p className="text-xs text-slate-500">Loading…</p>
        ) : isError ? (
          <p className="text-xs text-red-600">
            Failed to load relations: {(error as Error).message}
          </p>
        ) : relations ? (
          <RelationGroups taskId={taskId} relations={relations} />
        ) : null}
      </div>

      <AddRelationForm taskId={taskId} />
    </details>
  );
}

function RelationGroups({ taskId, relations }: { taskId: string; relations: BucketMap }) {
  const empty = useMemo(
    () => GROUP_LABELS.every(({ key }) => relations[key].length === 0),
    [relations],
  );

  if (empty) {
    return <p className="text-xs italic text-slate-400">No links yet.</p>;
  }

  return (
    <div className="space-y-2">
      {GROUP_LABELS.map(({ key, label, tone }) => {
        const items = relations[key];
        if (items.length === 0) return null;
        return (
          <div key={key}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              {label}
            </p>
            <ul className="mt-0.5 space-y-0.5">
              {items.map((item) => (
                <RelationRow key={item.relation_id} taskId={taskId} item={item} tone={tone} />
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function RelationRow({ taskId, item, tone }: { taskId: string; item: RelationItem; tone: Tone }) {
  const remove = useDeleteRelation(taskId);
  const onRemove = () => {
    remove.mutate({ relationId: item.relation_id, counterpartTaskId: item.task_id });
  };

  const toneClasses =
    tone === 'warn'
      ? 'border-red-200 bg-red-50/40'
      : tone === 'info'
        ? 'border-emerald-200 bg-emerald-50/40'
        : tone === 'muted'
          ? 'border-slate-200 bg-slate-50/60'
          : 'border-slate-200 bg-white';

  return (
    <li className={`flex items-center gap-1.5 rounded-md border px-1.5 py-1 ${toneClasses}`}>
      <Link href={`/tasks/${item.task_id}`} className="flex min-w-0 flex-1 items-center gap-1.5">
        <span className="shrink-0 font-mono text-[9px] uppercase text-slate-400">
          {item.public_id}
        </span>
        <span className="truncate text-xs text-slate-800 hover:text-indigo-700">{item.title}</span>
      </Link>
      <StatusChip status={item.status} isBlocked={item.is_blocked} />
      <button
        type="button"
        onClick={onRemove}
        disabled={remove.isPending}
        title="Remove relation"
        className="shrink-0 rounded border border-slate-200 bg-white px-1.5 text-[10px] font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-60"
      >
        ×
      </button>
    </li>
  );
}

function StatusChip({ status, isBlocked }: { status: string; isBlocked: boolean }) {
  if (isBlocked) {
    return (
      <span className="shrink-0 rounded bg-red-100 px-1 py-0.5 text-[8px] font-medium uppercase text-red-800">
        Blocked
      </span>
    );
  }
  const cls =
    status === 'DONE'
      ? 'bg-emerald-100 text-emerald-800'
      : status === 'IN_PROGRESS'
        ? 'bg-blue-100 text-blue-800'
        : status === 'CANCELLED'
          ? 'bg-slate-100 text-slate-500'
          : 'bg-slate-100 text-slate-700';
  return (
    <span className={`shrink-0 rounded px-1 py-0.5 text-[8px] font-medium uppercase ${cls}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

function AddRelationForm({ taskId }: { taskId: string }) {
  // For inverse options we POST to the *counterpart* task with this
  // task as the target, so the row stores in canonical source->target
  // form. We always invalidate both detail/relations caches at the
  // end so the UI on either side picks up the new link.
  const qc = useQueryClient();
  const { data: tasks } = useTasks();
  const [open, setOpen] = useState(false);
  const [optionValue, setOptionValue] = useState<string>('BLOCKS');
  const [query, setQuery] = useState('');
  const [target, setTarget] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q === '') return [];
    return (tasks ?? [])
      .filter((t) => t.id !== taskId)
      .filter((t) => t.title.toLowerCase().includes(q) || t.public_id.toLowerCase().includes(q))
      .slice(0, 6);
  }, [tasks, taskId, query]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    setError(null);
    const option = RELATION_OPTIONS.find((o) => o.value === optionValue);
    if (!option) return;

    // Forward (no swap): POST to this task with target as target.
    // Inverse (swap):    POST to target with this task as target.
    const sourceId = option.swap ? target.id : taskId;
    const targetId = option.swap ? taskId : target.id;

    setSubmitting(true);
    try {
      await tasksApi.createRelation(sourceId, {
        relation_type: option.type,
        target_task_id: targetId,
      });
      // Bust both ends of the link in every cache that surfaces it.
      qc.invalidateQueries({ queryKey: taskKeys.detail(taskId) });
      qc.invalidateQueries({ queryKey: taskKeys.detail(target.id) });
      qc.invalidateQueries({ queryKey: taskKeys.relations(taskId) });
      qc.invalidateQueries({ queryKey: taskKeys.relations(target.id) });
      setOpen(false);
      setTarget(null);
      setQuery('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create relation');
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) {
    return (
      <div className="border-t border-slate-100 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
        >
          + Add link
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-1.5 border-t border-slate-100 px-3 py-2">
      <div className="grid gap-1.5 sm:grid-cols-[150px_1fr]">
        <select
          value={optionValue}
          onChange={(e) => setOptionValue(e.target.value)}
          className="rounded-md border border-slate-300 px-1.5 py-1 text-[11px]"
        >
          {RELATION_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <div className="relative">
          <input
            type="text"
            value={target ? `${target.public_id}  ${target.title}` : query}
            placeholder="Search by ID or title…"
            onChange={(e) => {
              setTarget(null);
              setQuery(e.target.value);
            }}
            className="w-full rounded-md border border-slate-300 px-2 py-1 text-[11px]"
          />
          {target == null && filtered.length > 0 ? (
            <ul className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow-lg">
              {filtered.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setTarget(t);
                      setQuery('');
                    }}
                    className="flex w-full items-center gap-1.5 px-2 py-1 text-left hover:bg-slate-50"
                  >
                    <span className="font-mono text-[9px] uppercase text-slate-400">
                      {t.public_id}
                    </span>
                    <span className="truncate text-[11px] text-slate-800">{t.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-[11px] text-red-600">
          {error}
        </p>
      ) : null}

      <div className="flex justify-end gap-1.5">
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setTarget(null);
            setQuery('');
            setError(null);
          }}
          className="rounded-md border border-slate-200 px-2 py-0.5 text-[11px] text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting || target == null}
          className="rounded-md bg-indigo-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Linking…' : 'Add'}
        </button>
      </div>
    </form>
  );
}
