'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';

import { ApiError, type Member } from '../lib/api';
import { useCurrentPrincipal } from '../lib/auth';
import { useCreateTask, useMe, useMembers, useProjects, useTeams } from '../lib/queries';
import { MentionTextarea } from './MentionTextarea';

// Modal-ish (centered dialog with backdrop) without pulling in a UI lib.
// `useEffect` traps `Escape` and clicks on the backdrop close. The form
// posts via useCreateTask which invalidates the task list cache so the
// Kanban + Dashboard see the new task immediately.

export function CreateTaskDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createTask = useCreateTask();
  const principal = useCurrentPrincipal();
  const { data: me } = useMe();
  const { data: members } = useMembers();
  const { data: projects } = useProjects();
  const { data: teams } = useTeams();

  // Non-admin users can only create tasks on their own team. The api
  // already enforces this via CrossTeamForbiddenError; the UI mirrors
  // it by pre-filling and locking the team field. Admins / owners
  // pick freely. ``null`` for the principal happens during the auth
  // hydration window — treat that conservatively (locked) until the
  // role lands.
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';
  const lockedTeamId = !isAdmin ? (me?.team_id ?? '') : null;

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<number>(3);
  const [assigneeId, setAssigneeId] = useState<string>('');
  const [projectId, setProjectId] = useState<string>('');
  const [teamId, setTeamId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  // When the dialog opens for a non-admin, sync the team field with
  // their assigned team. The reset block below also clears it on
  // close, so this keeps the locked value fresh across re-opens
  // (e.g. after an admin reassigns them via the directory).
  useEffect(() => {
    if (open && lockedTeamId !== null) {
      setTeamId(lockedTeamId);
    }
  }, [open, lockedTeamId]);

  useEffect(() => {
    if (!open) return;
    titleRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await createTask.mutateAsync({
        title,
        description: description || null,
        priority,
        assignee_id: assigneeId || null,
        project_id: projectId || null,
        team_id: teamId || null,
      });
      // Reset and close. Non-admins keep their locked team across
      // submissions so they don't have to re-select on the next open.
      setTitle('');
      setDescription('');
      setPriority(3);
      setAssigneeId('');
      setProjectId('');
      setTeamId(lockedTeamId ?? '');
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create task');
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4"
      onClick={onClose}
    >
      <form
        onSubmit={onSubmit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-lg"
      >
        <header>
          <h2 className="text-base font-semibold text-slate-900">New task</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Tasks land in <span className="font-medium">Pending</span> and can be moved across the
            board with drag-and-drop.
          </p>
        </header>

        <Field label="Title" htmlFor="title">
          <input
            id="title"
            ref={titleRef}
            type="text"
            required
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>

        <Field
          label="Description"
          htmlFor="description"
          hint="Optional. Type @ to mention a teammate."
        >
          <MentionTextarea
            value={description}
            onChange={setDescription}
            members={members ?? []}
            rows={3}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Priority" htmlFor="priority">
            <input
              id="priority"
              type="number"
              min={0}
              max={1000}
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </Field>

          <Field label="Assignee" htmlFor="assignee">
            <select
              id="assignee"
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">Unassigned</option>
              {(members ?? []).map((m: Member) => (
                <option key={m.id} value={m.id}>
                  {m.name} {m.type === 'AGENT' ? '(agent)' : ''}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Project" htmlFor="project">
            <select
              id="project"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">Backlog (no project)</option>
              {(projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Team"
            htmlFor="team"
            hint={
              lockedTeamId !== null
                ? 'Locked to your team — admins can target other teams.'
                : undefined
            }
          >
            <select
              id="team"
              value={teamId}
              disabled={lockedTeamId !== null}
              onChange={(e) => setTeamId(e.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
            >
              {lockedTeamId !== null && lockedTeamId === '' ? (
                <option value="">No team — ask an admin to file you under one</option>
              ) : (
                <option value="">No team</option>
              )}
              {(teams ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}

        <footer className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={createTask.isPending}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={createTask.isPending}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {createTask.isPending ? 'Creating…' : 'Create task'}
          </button>
        </footer>
      </form>
    </div>
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
