'use client';

import { useState, type FormEvent } from 'react';

import { ApiError, type TaskRequest } from '../lib/api';
import { useCreateTaskRequest, useTaskRequests, useTeams } from '../lib/queries';

// Section 3 — task detail panel. Lets a member file a cross-team
// request anchored to *this* task (their own team's leadership picks
// it up via the inbox on /teams). Also lists prior requests on this
// task so everyone can see the audit trail.

export function CrossTeamRequestsPanel({ taskId }: { taskId: string }) {
  const { data: requests, isLoading, isError, error } = useTaskRequests(taskId);
  const count = requests?.length ?? 0;

  return (
    <details
      className="group rounded-lg border border-slate-200 bg-white shadow-sm [&_summary::-webkit-details-marker]:hidden"
      open={count > 0}
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
            Cross-team requests
          </h2>
          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
            {count}
          </span>
        </div>
      </summary>

      <div className="space-y-2 px-3 py-2">
        {isLoading ? (
          <p className="text-xs text-slate-500">Loading…</p>
        ) : isError ? (
          <p className="text-xs text-red-600">
            Failed to load requests: {(error as Error).message}
          </p>
        ) : count === 0 ? (
          <p className="text-xs italic text-slate-400">No cross-team requests on this task yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {requests!.map((r) => (
              <RequestRow key={r.id} request={r} />
            ))}
          </ul>
        )}
      </div>

      <RequestForm taskId={taskId} />
    </details>
  );
}

function RequestRow({ request }: { request: TaskRequest }) {
  const tone =
    request.status === 'PENDING'
      ? 'border-amber-200 bg-amber-50/50'
      : request.status === 'FULFILLED'
        ? 'border-emerald-200 bg-emerald-50/50'
        : 'border-slate-200 bg-slate-50/60';
  return (
    <li className={`rounded-md border p-2 text-xs ${tone}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 truncate font-medium text-slate-800">
          {request.suggested_title}
        </p>
        <span className="shrink-0 rounded bg-white px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-700">
          {request.status}
        </span>
      </div>
      {request.justification ? (
        <p className="mt-1 whitespace-pre-wrap text-[11px] text-slate-600">
          {request.justification}
        </p>
      ) : null}
      <p className="mt-1 text-[10px] text-slate-500">
        {request.requester_name ?? 'unknown'} · {new Date(request.created_at).toLocaleString()}
        {request.resolver_name ? ` · resolved by ${request.resolver_name}` : ''}
      </p>
      {request.reject_reason ? (
        <p className="mt-1 text-[11px] italic text-red-700">Rejected — {request.reject_reason}</p>
      ) : null}
    </li>
  );
}

function RequestForm({ taskId }: { taskId: string }) {
  const { data: teamsPage } = useTeams();
  const teams = teamsPage?.items ?? [];
  const create = useCreateTaskRequest(taskId);
  const [open, setOpen] = useState(false);
  const [teamId, setTeamId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [justification, setJustification] = useState('');
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!teamId) return;
    setError(null);
    try {
      await create.mutateAsync({
        requested_team_id: teamId,
        suggested_title: title.trim(),
        suggested_description: description.trim() || null,
        justification: justification.trim() || null,
      });
      setTeamId('');
      setTitle('');
      setDescription('');
      setJustification('');
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create request');
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
          + Request from another team
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-2 border-t border-slate-100 px-3 py-2">
      <p className="text-[11px] text-slate-500">
        Your team&apos;s leadership (HEAD / MANAGER / LEAD) will review and either fulfill the
        request — minting a task on the target team and linking it as a blocker — or reject it.
      </p>
      <div className="grid gap-2 sm:grid-cols-[180px_1fr]">
        <select
          value={teamId}
          required
          onChange={(e) => setTeamId(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-[11px]"
        >
          <option value="" disabled>
            Target team…
          </option>
          {teams.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={title}
          required
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Suggested title for the new task"
          className="rounded-md border border-slate-300 px-2 py-1 text-[11px]"
        />
      </div>
      <textarea
        rows={2}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Suggested description (what should the other team do?)"
        className="w-full rounded-md border border-slate-300 px-2 py-1 text-[11px]"
      />
      <textarea
        rows={2}
        value={justification}
        onChange={(e) => setJustification(e.target.value)}
        placeholder="Why is this needed for your task? (helps your leadership decide)"
        className="w-full rounded-md border border-slate-300 px-2 py-1 text-[11px]"
      />
      {error ? (
        <p role="alert" className="text-[11px] text-red-600">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
          className="rounded-md border border-slate-200 px-2 py-0.5 text-[11px] text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={create.isPending || !teamId || title.trim() === ''}
          className="rounded-md bg-indigo-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {create.isPending ? 'Filing…' : 'File request'}
        </button>
      </div>
    </form>
  );
}
