'use client';

import { useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';

import { Field, formatRelative, HealthPill } from '../../../components/AgentUI';
import { ConfirmDialog } from '../../../components/ConfirmDialog';
import { ApiError, type AgentStats } from '../../../lib/api';
import { agentKeys, useAgent, useDeleteAgent, useUpdateAgent } from '../../../lib/queries';

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const qc = useQueryClient();
  const { data: agent, isLoading, isError, error } = useAgent(id);
  const deleteAgent = useDeleteAgent();

  const [pinging, setPinging] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState(false);

  if (isLoading) {
    return <p className="p-6 text-sm text-slate-500">Loading agent…</p>;
  }
  if (isError) {
    return (
      <p className="p-6 text-sm text-red-600">Failed to load agent: {(error as Error).message}</p>
    );
  }
  if (!agent) return null;

  const onPing = async () => {
    // Explicit refetch (rather than just invalidate) so the pending
    // state is deterministic — invalidate alone returns immediately
    // when the cache is fresh, and the button would flicker.
    setPinging(true);
    try {
      await qc.refetchQueries({ queryKey: agentKeys.detail(id) });
    } finally {
      setPinging(false);
    }
  };

  const onCopyId = async () => {
    await navigator.clipboard.writeText(id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 1500);
  };

  const onDelete = async () => {
    setDeleteError(null);
    try {
      await deleteAgent.mutateAsync(id);
      setConfirmOpen(false);
      router.replace('/agents');
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.detail : 'Failed to delete agent');
      setConfirmOpen(false);
    }
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header>
        <Link href="/agents" className="text-xs text-slate-500 hover:text-slate-700">
          ← Agents
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold text-slate-900">{agent.name}</h1>
        </div>
        <p className="text-xs text-slate-500">
          Created {new Date(agent.created_at).toLocaleString()}
        </p>
      </header>

      <StatusCard
        status={agent.health_status}
        lastSeenAt={agent.last_seen_at}
        pinging={pinging}
        onPing={onPing}
      />

      <IdentityCard id={id} copied={copiedId} onCopy={onCopyId} />

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
        <div className="flex flex-wrap items-center justify-end gap-3 px-4 py-3">
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            Delete agent
          </button>
        </div>
        {deleteError ? (
          <p role="alert" className="px-4 pb-3 text-sm text-red-600">
            {deleteError}
          </p>
        ) : null}
      </section>

      <ConfirmDialog
        open={confirmOpen}
        title="Delete this agent?"
        message={`"${agent.name}" will be permanently removed. Any in-flight tasks will be unassigned. This cannot be undone.`}
        confirmLabel="Delete agent"
        cancelLabel="Cancel"
        pending={deleteAgent.isPending}
        onConfirm={onDelete}
        onCancel={() => setConfirmOpen(false)}
        tone="danger"
      />
    </div>
  );
}

function StatusCard({
  status,
  lastSeenAt,
  pinging,
  onPing,
}: {
  status: 'ONLINE' | 'IDLE' | 'STALE';
  lastSeenAt: string | null;
  pinging: boolean;
  onPing: () => void;
}) {
  const lastSeenLabel = lastSeenAt ? `Last seen ${formatRelative(lastSeenAt)}` : 'Never seen';
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col items-center gap-3 px-4 py-5 text-center">
        <HealthPill status={status} lastSeenAt={lastSeenAt} />
        <p className="text-xs text-slate-500">{lastSeenLabel}</p>
        <button
          type="button"
          onClick={onPing}
          disabled={pinging}
          className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span
            className={`h-2 w-2 rounded-full bg-white/90 ${pinging ? 'animate-ping' : ''}`}
            aria-hidden
          />
          {pinging ? 'Pinging…' : 'Ping agent'}
        </button>
        <p className="max-w-md text-[11px] text-slate-500">
          Re-checks the agent&apos;s last-seen timestamp. Agents stamp it on every JWT exchange and
          on calls to <code className="font-mono">/api/v1/agents/me/heartbeat</code>.
        </p>
      </div>
    </section>
  );
}

function IdentityCard({ id, copied, onCopy }: { id: string; copied: boolean; onCopy: () => void }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Agent ID</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Use this with the agent&apos;s API key when calling{' '}
          <code className="font-mono">POST /api/v1/auth/agent-token</code>.
        </p>
      </header>
      <div className="flex items-center gap-2 px-4 py-3">
        <code className="flex-1 truncate rounded border border-slate-200 bg-slate-50 px-2 py-1.5 font-mono text-xs text-slate-800">
          {id}
        </code>
        <button
          type="button"
          onClick={onCopy}
          className="shrink-0 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </section>
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
          Agent credentials cannot be changed after creation. You can only update the Name,
          Priority, and Model.
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
