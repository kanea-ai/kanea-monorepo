'use client';

// Phase 5 batch 2: agent provisioning lives on the unified directory.
// Mirrors the field set from the previous /agents create form, just
// inside our standard <Modal>. Two-stage flow: form → API key reveal.

import { useEffect, useState, type FormEvent } from 'react';

import { ApiError, type CreateAgentResponse } from '../lib/api';
import { useCreateAgent } from '../lib/queries';
import { Modal } from './Modal';

export function CreateAgentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateAgent();
  const [name, setName] = useState('');
  const [priority, setPriority] = useState(5);
  const [model, setModel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreateAgentResponse | null>(null);
  const [copied, setCopied] = useState<'id' | 'key' | null>(null);

  useEffect(() => {
    if (open) {
      setName('');
      setPriority(5);
      setModel('');
      setError(null);
      setCreated(null);
      setCopied(null);
    }
  }, [open]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const out = await create.mutateAsync({
        name,
        priority,
        model: model.trim() === '' ? null : model.trim(),
      });
      setCreated(out);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create agent');
    }
  };

  const onCopy = async (kind: 'id' | 'key', value: string) => {
    await navigator.clipboard.writeText(value);
    setCopied(kind);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      pending={create.isPending}
      title="Create agent"
      subtitle={
        created
          ? 'API key shown once — copy it now. The api stores only a bcrypt hash.'
          : 'Provision an automated agent with its own credentials.'
      }
      size="lg"
      footer={
        created ? (
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            Done
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={onClose}
              disabled={create.isPending}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              form="create-agent-form"
              disabled={create.isPending || name.trim() === ''}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {create.isPending ? 'Creating…' : 'Create agent'}
            </button>
          </>
        )
      }
    >
      {created ? (
        <div className="space-y-3">
          <KeyRow
            label="Agent ID"
            value={created.id}
            copied={copied === 'id'}
            onCopy={() => onCopy('id', created.id)}
          />
          <KeyRow
            label="API key"
            value={created.api_key}
            copied={copied === 'key'}
            onCopy={() => onCopy('key', created.api_key)}
            sensitive
          />
          <p className="text-xs text-slate-500">
            Store the key in your secret manager. We can&apos;t show it again — you can rotate from
            the agent&apos;s detail page.
          </p>
        </div>
      ) : (
        <form id="create-agent-form" onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label htmlFor="agent_name">Name</Label>
            <input
              id="agent_name"
              type="text"
              required
              value={name}
              maxLength={120}
              placeholder="researcher-bot"
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="agent_model">Model (optional)</Label>
            <input
              id="agent_model"
              type="text"
              value={model}
              maxLength={120}
              placeholder="claude-opus-4-7"
              onChange={(e) => setModel(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <Label htmlFor="agent_priority">Priority (2–100)</Label>
            <input
              id="agent_priority"
              type="number"
              min={2}
              max={100}
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          {error ? (
            <p role="alert" className="text-sm text-red-600 sm:col-span-2">
              {error}
            </p>
          ) : null}
        </form>
      )}
    </Modal>
  );
}

function KeyRow({
  label,
  value,
  copied,
  onCopy,
  sensitive = false,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
  sensitive?: boolean;
}) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-600">{label}</p>
      <div className="flex items-center gap-2">
        <code
          className={`flex-1 truncate rounded border border-slate-200 bg-slate-50 px-2 py-1.5 font-mono text-xs text-slate-800 ${
            sensitive ? 'tracking-tight' : ''
          }`}
        >
          {value}
        </code>
        <button
          type="button"
          onClick={onCopy}
          className="shrink-0 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}

function Label({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label
      htmlFor={htmlFor}
      className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
    >
      {children}
    </label>
  );
}
