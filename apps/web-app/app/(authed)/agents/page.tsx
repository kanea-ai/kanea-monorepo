'use client';

import { useState, type FormEvent } from 'react';

import { ApiError, type Agent, type CreateAgentResponse } from '../../lib/api';
import { useAgents, useCreateAgent } from '../../lib/queries';

// One-time secret display: when an agent is provisioned the api returns
// the plaintext key in the response, hashed on persist. The created
// response is held in component state and surfaced inline; refreshing
// the page erases it. Same pattern as invite tokens on /team.

export default function AgentsPage() {
  const { data: agents, isLoading, isError, error } = useAgents();

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
        <header className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Active agents</h2>
        </header>
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
          ) : (
            <ul className="divide-y divide-slate-100">
              {agents.map((a) => (
                <AgentRow key={a.id} agent={a} />
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function CreateAgentSection() {
  const createAgent = useCreateAgent();
  const [name, setName] = useState('');
  const [priority, setPriority] = useState<number>(5);
  const [error, setError] = useState<string | null>(null);
  const [lastCreated, setLastCreated] = useState<CreateAgentResponse | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const created = await createAgent.mutateAsync({ name, priority });
      setLastCreated(created);
      setName('');
      setPriority(5);
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
        className="grid gap-3 px-4 py-4 sm:grid-cols-[1fr_120px_auto] sm:items-end"
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
        <Field label="Priority" htmlFor="agent_priority" hint="Lower = higher rank.">
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
  return (
    <li className="flex items-center justify-between gap-3 px-3 py-2.5">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-slate-900">{agent.name}</p>
        <p className="mt-0.5 truncate text-xs text-slate-500">
          ID: <code className="font-mono">{agent.id}</code>
        </p>
      </div>
      <span className="shrink-0 rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-violet-800">
        P{agent.priority}
      </span>
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
