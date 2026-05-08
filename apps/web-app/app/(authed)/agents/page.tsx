'use client';

import { useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useMemo, useState, type FormEvent } from 'react';

import { Field, HealthPill } from '../../components/AgentUI';
import { ApiError, type Agent, type CreateAgentResponse, type HealthStatus } from '../../lib/api';
import { agentKeys, useAgents, useCreateAgent } from '../../lib/queries';

// One-time secret display: when an agent is provisioned the api returns
// the plaintext key in the response, hashed on persist. The created
// response is held in component state and surfaced inline; refreshing
// the page erases it. Same pattern as invite tokens on /team.

type StatusFilter = 'ALL' | HealthStatus;

export default function AgentsPage() {
  const { data: agents, isLoading, isError, error } = useAgents();
  const qc = useQueryClient();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [pingingAll, setPingingAll] = useState(false);

  const filtered = useMemo(() => {
    if (!agents) return [];
    const q = search.trim().toLowerCase();
    return agents.filter((a) => {
      if (statusFilter !== 'ALL' && a.health_status !== statusFilter) return false;
      if (q === '') return true;
      return (
        a.name.toLowerCase().includes(q) ||
        (a.model ?? '').toLowerCase().includes(q) ||
        a.id.toLowerCase().includes(q)
      );
    });
  }, [agents, search, statusFilter]);

  const onPingAll = async () => {
    // Refetches the list query (and any hot detail queries). The actual
    // last_seen_at stamping only happens when an agent itself reconnects
    // — this just pulls the freshest server-side view.
    setPingingAll(true);
    try {
      await qc.refetchQueries({ queryKey: agentKeys.all });
    } finally {
      setPingingAll(false);
    }
  };

  const counts = useMemo(() => {
    const base = { ALL: agents?.length ?? 0, ONLINE: 0, IDLE: 0, STALE: 0 };
    for (const a of agents ?? []) base[a.health_status] += 1;
    return base;
  }, [agents]);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Agents</h1>
        <p className="text-sm text-slate-500">
          AI agents that operate inside this workspace. Each one has an API key it uses to exchange
          for a JWT at <code className="text-slate-700">/api/v1/auth/agent-token</code>.
        </p>
      </header>

      <CreateAgentSection />

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <header className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="mr-auto text-sm font-semibold text-slate-900">Active agents</h2>
          <button
            type="button"
            onClick={onPingAll}
            disabled={pingingAll || !agents || agents.length === 0}
            className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full bg-white ${pingingAll ? 'animate-ping' : ''}`}
              aria-hidden
            />
            {pingingAll ? 'Pinging…' : 'Ping all'}
          </button>
        </header>

        <div className="grid gap-2 border-b border-slate-100 px-4 py-3 sm:grid-cols-[1fr_auto]">
          <input
            type="search"
            placeholder="Search by name, model, or ID…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <StatusTabs current={statusFilter} counts={counts} onChange={setStatusFilter} />
        </div>

        <div className="p-1">
          {isError ? (
            <p className="px-3 py-6 text-sm text-red-600">
              Failed to load agents: {(error as Error).message}
            </p>
          ) : isLoading ? (
            <SkeletonRows count={2} />
          ) : !agents || agents.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-slate-500">
              No agents yet. Create one above to get started.
            </p>
          ) : filtered.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-slate-500">
              No agents match the current filters.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {filtered.map((a) => (
                <AgentRow key={a.id} agent={a} />
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function StatusTabs({
  current,
  counts,
  onChange,
}: {
  current: StatusFilter;
  counts: Record<StatusFilter, number>;
  onChange: (s: StatusFilter) => void;
}) {
  const tabs: StatusFilter[] = ['ALL', 'ONLINE', 'IDLE', 'STALE'];
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-slate-300 text-xs">
      {tabs.map((t, i) => {
        const active = current === t;
        const dot =
          t === 'ONLINE'
            ? 'bg-emerald-500'
            : t === 'IDLE'
              ? 'bg-amber-500'
              : t === 'STALE'
                ? 'bg-slate-400'
                : null;
        return (
          <button
            key={t}
            type="button"
            onClick={() => onChange(t)}
            className={`flex items-center gap-1.5 px-3 py-1.5 font-medium ${i > 0 ? 'border-l border-slate-300' : ''} ${
              active ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            {dot ? <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden /> : null}
            {t === 'ALL' ? 'All' : t.charAt(0) + t.slice(1).toLowerCase()}
            <span
              className={`rounded-full px-1.5 text-[10px] ${
                active ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'
              }`}
            >
              {counts[t]}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function CreateAgentSection() {
  const createAgent = useCreateAgent();
  const [name, setName] = useState('');
  const [priority, setPriority] = useState<number>(5);
  const [model, setModel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [lastCreated, setLastCreated] = useState<CreateAgentResponse | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const trimmed = model.trim();
      const created = await createAgent.mutateAsync({
        name,
        priority,
        model: trimmed === '' ? null : trimmed,
      });
      setLastCreated(created);
      setName('');
      setPriority(5);
      setModel('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create agent');
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Provision an agent</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Generates a 256-bit API key. The key is shown <span className="font-medium">once</span> —
          the api stores only a bcrypt hash and can&apos;t recover it. Copy it now or rotate.
        </p>
      </header>

      <form
        className="grid gap-3 px-4 py-4 sm:grid-cols-[1fr_1fr_120px_auto] sm:items-end"
        onSubmit={onSubmit}
      >
        <Field label="Name" htmlFor="agent_name">
          <input
            id="agent_name"
            type="text"
            required
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            placeholder="researcher-bot"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>
        <Field
          label="Model"
          htmlFor="agent_model"
          hint="Free-form model identifier, e.g. claude-opus-4-7. Optional."
        >
          <input
            id="agent_model"
            type="text"
            value={model}
            maxLength={120}
            onChange={(e) => setModel(e.target.value)}
            placeholder="claude-opus-4-7"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>
        <Field
          label="Priority"
          htmlFor="agent_priority"
          hint="Numeric rank, 2-100. Lower = higher priority. Workspace owner is 1."
        >
          <input
            id="agent_priority"
            type="number"
            min={2}
            max={100}
            value={priority}
            onChange={(e) => setPriority(Number(e.target.value))}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>
        <button
          type="submit"
          disabled={createAgent.isPending}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {createAgent.isPending ? 'Creating…' : 'Create agent'}
        </button>
      </form>

      {error ? (
        <p role="alert" className="px-4 pb-4 text-sm text-red-600">
          {error}
        </p>
      ) : null}

      {lastCreated ? <ApiKeyReveal agent={lastCreated} /> : null}
    </section>
  );
}

function ApiKeyReveal({ agent }: { agent: CreateAgentResponse }) {
  const [copied, setCopied] = useState<'id' | 'key' | null>(null);

  const onCopy = async (kind: 'id' | 'key', value: string) => {
    await navigator.clipboard.writeText(value);
    setCopied(kind);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <div className="border-t border-slate-100 bg-emerald-50/50 px-4 py-3">
      <p className="text-xs font-medium text-emerald-900">
        Agent <span className="font-semibold">{agent.name}</span> created. Copy both fields now —
        the API key won&apos;t be shown again.
      </p>

      <KeyRow
        label="Agent ID"
        value={agent.id}
        copied={copied === 'id'}
        onCopy={() => onCopy('id', agent.id)}
      />
      <KeyRow
        label="API key"
        value={agent.api_key}
        copied={copied === 'key'}
        onCopy={() => onCopy('key', agent.api_key)}
      />

      <p className="mt-2 text-[11px] text-emerald-900/80">
        The agent posts these to <code className="font-mono">POST /api/v1/auth/agent-token</code> as{' '}
        <code className="font-mono">{`{ agent_id, secret }`}</code> to get a short-lived JWT.
      </p>
    </div>
  );
}

function KeyRow({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="mt-2 flex items-center gap-2">
      <span className="w-20 shrink-0 text-[10px] font-semibold uppercase tracking-wide text-emerald-900">
        {label}
      </span>
      <code className="flex-1 truncate rounded border border-emerald-200 bg-white px-2 py-1.5 font-mono text-xs text-slate-800">
        {value}
      </code>
      <button
        type="button"
        onClick={onCopy}
        className="shrink-0 rounded-md border border-emerald-300 bg-white px-3 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-100"
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}

function AgentRow({ agent }: { agent: Agent }) {
  const qc = useQueryClient();
  const [pinging, setPinging] = useState(false);

  const onPing = async (e: React.MouseEvent) => {
    // Stop the click from bubbling into the row's Link.
    e.preventDefault();
    e.stopPropagation();
    setPinging(true);
    try {
      // Refresh both the list (so this row's pill updates) and any
      // open detail cache for this agent.
      await Promise.all([
        qc.refetchQueries({ queryKey: agentKeys.all }),
        qc.refetchQueries({ queryKey: agentKeys.detail(agent.id) }),
      ]);
    } finally {
      setPinging(false);
    }
  };

  return (
    <li className="hover:bg-slate-50">
      <div className="flex items-center gap-3 px-3 py-2.5">
        <Link href={`/agents/${agent.id}`} className="flex min-w-0 flex-1 items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-900">{agent.name}</p>
            <p className="mt-0.5 truncate text-xs text-slate-500">
              {agent.model ?? <span className="italic">No model set</span>}
            </p>
          </div>
        </Link>
        <HealthPill status={agent.health_status} lastSeenAt={agent.last_seen_at} size="sm" />
        <span className="shrink-0 rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-violet-800">
          P{agent.priority}
        </span>
        <button
          type="button"
          onClick={onPing}
          disabled={pinging}
          className="shrink-0 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pinging ? 'Pinging…' : 'Ping'}
        </button>
      </div>
    </li>
  );
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <ul className="divide-y divide-slate-100">
      {Array.from({ length: count }).map((_, i) => (
        <li key={i} className="px-3 py-3">
          <div className="h-3 w-1/3 animate-pulse rounded bg-slate-100" />
          <div className="mt-2 h-3 w-1/2 animate-pulse rounded bg-slate-100" />
        </li>
      ))}
    </ul>
  );
}
