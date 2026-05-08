'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';

import { ApiError, type Member } from '../lib/api';
import { useCreateTask, useMembers } from '../lib/queries';

// Modal-ish (centered dialog with backdrop) without pulling in a UI lib.
// `useEffect` traps `Escape` and clicks on the backdrop close. The form
// posts via useCreateTask which invalidates the task list cache so the
// Kanban + Dashboard see the new task immediately.

export function CreateTaskDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createTask = useCreateTask();
  const { data: members } = useMembers();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<number>(3);
  const [assigneeId, setAssigneeId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);

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
      });
      // Reset and close.
      setTitle('');
      setDescription('');
      setPriority(3);
      setAssigneeId('');
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
          hint="Optional. Markdown not yet rendered."
        >
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
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
