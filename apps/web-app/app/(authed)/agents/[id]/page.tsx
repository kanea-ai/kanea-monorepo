'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';

import { ApiError, type AgentStats } from '../../../lib/api';
import { useAgent, useDeleteAgent, useUpdateAgent } from '../../../lib/queries';

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const { data: agent, isLoading, isError, error } = useAgent(id);
  const deleteAgent = useDeleteAgent();

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (isLoading) {
    return <p className="p-6 text-sm text-slate-500">Loading agent…</p>;
  }
  if (isError) {
    return (
      <p className="p-6 text-sm text-red-600">Failed to load agent: {(error as Error).message}</p>
    );
  }
  if (!agent) return null;

  const onDelete = async () => {
    setDeleteError(null);
    try {
      await deleteAgent.mutateAsync(id);
      router.replace('/agents');
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.detail : 'Failed to delete agent');
      setConfirmDelete(false);
    }
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/agents" className="text-xs text-slate-500 hover:text-slate-700">
            ← Agents
          </Link>
          <h1 className="mt-1 text-xl font-semibold text-slate-900">{agent.name}</h1>
          <p className="text-xs text-slate-500">
            Created {new Date(agent.created_at).toLocaleString()}
          </p>
        </div>
      </header>

      <StatsGrid stats={agent.stats} />

      <EditForm
        id={id}
        initial={{ name: agent.name, priority: agent.priority, model: agent.model }}
      />

      <section className="rounded-lg border border-red-200 bg-white shadow-sm">
        <header className="border-b border-red-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-red-900">Danger zone</h2>
          <p className="mt-0.5 text-xs text-red-700/70">
            Deleting unassigns the agent from any in-flight tasks (set to unassigned). Refused if
            the agent created tasks that other members own.
          </p>
        </header>
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          {confirmDelete ? (
            <>
              <span className="text-sm text-slate-700">Delete this agent permanently?</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmDelete(false)}
                  disabled={deleteAgent.isPending}
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  Keep
                </button>
                <button
                  type="button"
                  onClick={onDelete}
                  disabled={deleteAgent.isPending}
                  className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-red-700 disabled:opacity-60"
                >
                  {deleteAgent.isPending ? 'Deleting…' : 'Delete agent'}
                </button>
              </div>
            </>
          ) : (
            <>
              <span className="text-sm text-slate-700">Permanent — no soft-delete.</span>
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
              >
                Delete agent
              </button>
            </>
          )}
        </div>
        {deleteError ? (
          <p role="alert" className="px-4 pb-3 text-sm text-red-600">
            {deleteError}
          </p>
        ) : null}
      </section>
    </div>
  );
}

function StatsGrid({ stats }: { stats: AgentStats }) {
  const tiles = [
    { label: 'Currently assigned', value: stats.assigned_count.toString() },
    { label: 'Completed', value: stats.completed_count.toString() },
    {
      label: 'Avg resolution',
      value:
        stats.avg_resolution_seconds == null ? '—' : formatDuration(stats.avg_resolution_seconds),
    },
    {
      label: 'Accuracy',
      value: stats.accuracy_percent == null ? '—' : `${stats.accuracy_percent.toFixed(0)}%`,
      tone: stats.accuracy_percent == null ? 'default' : accuracyTone(stats.accuracy_percent),
    },
    {
      label: 'Last activity',
      value: stats.last_activity_at == null ? '—' : formatRelative(stats.last_activity_at),
    },
    {
      label: 'Tokens used',
      value: stats.total_tokens_used.toLocaleString(),
    },
  ];

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {tiles.map((t) => (
        <div
          key={t.label}
          className={`rounded-lg border p-4 shadow-sm ${
            t.tone === 'good'
              ? 'border-emerald-200 bg-emerald-50'
              : t.tone === 'bad'
                ? 'border-amber-200 bg-amber-50'
                : 'border-slate-200 bg-white'
          }`}
        >
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            {t.label}
          </p>
          <p className="mt-1 text-2xl font-semibold text-slate-900">{t.value}</p>
        </div>
      ))}
    </section>
  );
}

function EditForm({
  id,
  initial,
}: {
  id: string;
  initial: { name: string; priority: number; model: string | null };
}) {
  const updateAgent = useUpdateAgent(id);
  const [name, setName] = useState(initial.name);
  const [priority, setPriority] = useState(initial.priority);
  const [model, setModel] = useState(initial.model ?? '');
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Reset form state when the underlying agent fetch swaps to a fresh
  // copy (e.g. after another tab edits it). Without this the inputs
  // would stay stuck on the first-render values.
  useEffect(() => {
    setName(initial.name);
    setPriority(initial.priority);
    setModel(initial.model ?? '');
  }, [initial.name, initial.priority, initial.model]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      // Only send fields that actually changed. `model: null` explicitly
      // clears it; an empty string is interpreted the same way.
      const payload: { name?: string; priority?: number; model?: string | null } = {};
      if (name !== initial.name) payload.name = name;
      if (priority !== initial.priority) payload.priority = priority;
      const trimmed = model.trim();
      const newModel: string | null = trimmed === '' ? null : trimmed;
      if (newModel !== initial.model) payload.model = newModel;
      if (Object.keys(payload).length === 0) return;

      await updateAgent.mutateAsync(payload);
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save');
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Profile</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          The agent <span className="font-mono">{id.slice(0, 8)}…</span> can&apos;t change. Name,
          priority, and model are editable.
        </p>
      </header>
      <form className="grid gap-3 px-4 py-4 sm:grid-cols-3" onSubmit={onSubmit}>
        <Field label="Name" htmlFor="name">
          <input
            id="name"
            type="text"
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>
        <Field label="Priority" htmlFor="priority" hint="Lower = higher rank.">
          <input
            id="priority"
            type="number"
            min={2}
            max={100}
            value={priority}
            onChange={(e) => setPriority(Number(e.target.value))}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>
        <Field label="Model" htmlFor="model" hint="Free-form. Leave blank to clear.">
          <input
            id="model"
            type="text"
            value={model}
            maxLength={120}
            placeholder="e.g. claude-opus-4-7"
            onChange={(e) => setModel(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>
        <div className="flex items-center justify-end gap-3 sm:col-span-3">
          {error ? (
            <p role="alert" className="mr-auto text-xs text-red-600">
              {error}
            </p>
          ) : null}
          {savedAt && !updateAgent.isPending && !error ? (
            <span className="mr-auto text-xs text-emerald-700">Saved</span>
          ) : null}
          <button
            type="submit"
            disabled={updateAgent.isPending}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {updateAgent.isPending ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </form>
    </section>
  );
}

function accuracyTone(percent: number): 'good' | 'bad' | 'default' {
  if (percent >= 80) return 'good';
  if (percent < 60) return 'bad';
  return 'default';
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const min = seconds / 60;
  if (min < 60) return `${Math.round(min)}m`;
  const hr = min / 60;
  if (hr < 24) return `${hr.toFixed(1)}h`;
  return `${(hr / 24).toFixed(1)}d`;
}

function formatRelative(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return iso;
  const diff = Date.now() - ts;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.round(hr / 24)}d ago`;
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
      >
        {label}
      </label>
      {children}
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
