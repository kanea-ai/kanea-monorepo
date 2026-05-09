'use client';

import Link from 'next/link';
import { useMemo, useState, type FormEvent } from 'react';

import { ApiError, type RelationItem, type RelationType, type Task } from '../lib/api';
import { useCreateRelation, useDeleteRelation, useTaskRelations, useTasks } from '../lib/queries';

// One panel that owns the seven relation buckets + the add-relation
// form. The detail page just slots this in next to the comment thread.

const RELATION_OPTIONS: { value: RelationType; label: string }[] = [
  { value: 'BLOCKS', label: 'Blocks' },
  { value: 'MITIGATES', label: 'Mitigates' },
  { value: 'DUPLICATES', label: 'Is duplicate of' },
  { value: 'RELATES_TO', label: 'Relates to' },
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
  const { data: relations, isLoading, isError, error } = useTaskRelations(taskId);

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Relations</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Link this task to other tasks in the workspace. Links update both sides.
        </p>
      </header>

      <div className="space-y-3 px-4 py-3">
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading relations…</p>
        ) : isError ? (
          <p className="text-sm text-red-600">
            Failed to load relations: {(error as Error).message}
          </p>
        ) : relations ? (
          <RelationGroups taskId={taskId} relations={relations} />
        ) : null}
      </div>

      <AddRelationForm taskId={taskId} />
    </section>
  );
}

function RelationGroups({ taskId, relations }: { taskId: string; relations: BucketMap }) {
  const empty = useMemo(
    () => GROUP_LABELS.every(({ key }) => relations[key].length === 0),
    [relations],
  );

  if (empty) {
    return <p className="text-sm italic text-slate-400">No relations yet.</p>;
  }

  return (
    <div className="space-y-3">
      {GROUP_LABELS.map(({ key, label, tone }) => {
        const items = relations[key];
        if (items.length === 0) return null;
        return (
          <div key={key}>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {label}
            </p>
            <ul className="mt-1 space-y-1">
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
    <li className={`flex items-center gap-2 rounded-md border px-2 py-1.5 ${toneClasses}`}>
      <Link href={`/tasks/${item.task_id}`} className="min-w-0 flex-1">
        <p className="font-mono text-[10px] uppercase tracking-wide text-slate-400">
          {item.public_id}
        </p>
        <p className="truncate text-sm text-slate-800 hover:text-indigo-700">{item.title}</p>
      </Link>
      <StatusChip status={item.status} isBlocked={item.is_blocked} />
      <button
        type="button"
        onClick={onRemove}
        disabled={remove.isPending}
        title="Remove relation"
        className="shrink-0 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-60"
      >
        ×
      </button>
    </li>
  );
}

function StatusChip({ status, isBlocked }: { status: string; isBlocked: boolean }) {
  if (isBlocked) {
    return (
      <span className="shrink-0 rounded bg-red-100 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-red-800">
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
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide ${cls}`}
    >
      {status.replace('_', ' ')}
    </span>
  );
}

function AddRelationForm({ taskId }: { taskId: string }) {
  const create = useCreateRelation(taskId);
  const { data: tasks } = useTasks();
  const [open, setOpen] = useState(false);
  const [relationType, setRelationType] = useState<RelationType>('BLOCKS');
  const [query, setQuery] = useState('');
  const [target, setTarget] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Quick autocomplete: filter the workspace task list client-side.
  // Excludes the current task — self-links would 400 anyway.
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
    try {
      await create.mutateAsync({ relation_type: relationType, target_task_id: target.id });
      setOpen(false);
      setTarget(null);
      setQuery('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create relation');
    }
  };

  if (!open) {
    return (
      <div className="border-t border-slate-100 px-4 py-3">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          + Add relation
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-2 border-t border-slate-100 px-4 py-3">
      <div className="grid gap-2 sm:grid-cols-[160px_1fr]">
        <select
          value={relationType}
          onChange={(e) => setRelationType(e.target.value as RelationType)}
          className="rounded-md border border-slate-300 px-2 py-2 text-xs"
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
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-xs"
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
                    className="flex w-full items-center gap-2 px-2 py-1.5 text-left hover:bg-slate-50"
                  >
                    <span className="font-mono text-[10px] uppercase text-slate-400">
                      {t.public_id}
                    </span>
                    <span className="truncate text-xs text-slate-800">{t.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      ) : null}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setTarget(null);
            setQuery('');
            setError(null);
          }}
          className="rounded-md border border-slate-200 px-3 py-1 text-xs text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={create.isPending || target == null}
          className="rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {create.isPending ? 'Linking…' : 'Add'}
        </button>
      </div>
    </form>
  );
}
