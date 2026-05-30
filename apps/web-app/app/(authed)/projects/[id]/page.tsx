'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { ConfirmDialog } from '../../../components/ConfirmDialog';
import { EditToolbar } from '../../../components/EditToolbar';
import { ApiError, type Task } from '../../../lib/api';
import { useCurrentPrincipal } from '../../../lib/auth';
import { canEditProject } from '../../../lib/permissions';
import {
  useDeleteProject,
  useProject,
  useProjectTasks,
  useUpdateProject,
} from '../../../lib/queries';

// Project detail: header + edit form, status chip, scoped task list.
// Status flips between ACTIVE and ARCHIVED; ARCHIVED hides from default
// project list views without removing data.

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const principal = useCurrentPrincipal();
  const canEdit = canEditProject(principal);
  const { data: project, isLoading, isError, error } = useProject(id);
  const { data: tasks } = useProjectTasks(id);
  const update = useUpdateProject(id);
  const remove = useDeleteProject();

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  // Reset form when fetch swaps in fresh data.
  useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description ?? '');
      setEditing(false);
    }
  }, [project]);

  if (isLoading) return <p className="p-6 text-sm text-slate-500">Loading…</p>;
  if (isError) {
    return (
      <p className="p-6 text-sm text-red-600">Failed to load project: {(error as Error).message}</p>
    );
  }
  if (!project) return null;

  const trimmedDesc = description.trim();
  const newDesc = trimmedDesc === '' ? null : trimmedDesc;
  const nameChanged = name !== project.name && name.trim() !== '';
  const descChanged = newDesc !== project.description;
  const dirty = nameChanged || descChanged;

  const onSave = async () => {
    setEditError(null);
    if (!dirty) {
      setEditing(false);
      return;
    }
    try {
      const payload: { name?: string; description?: string | null } = {};
      if (nameChanged) payload.name = name;
      if (descChanged) payload.description = newDesc;
      await update.mutateAsync(payload);
      setSavedAt(Date.now());
      setEditing(false);
    } catch (err) {
      setEditError(err instanceof ApiError ? err.detail : 'Failed to save');
    }
  };

  const onCancelEdit = () => {
    setName(project.name);
    setDescription(project.description ?? '');
    setEditError(null);
    setEditing(false);
  };

  const editTooltip = 'You do not have permission to edit this. Please ask a workspace admin.';

  const onToggleArchive = async () => {
    setEditError(null);
    try {
      await update.mutateAsync({
        status: project.status === 'ACTIVE' ? 'ARCHIVED' : 'ACTIVE',
      });
    } catch (err) {
      setEditError(err instanceof ApiError ? err.detail : 'Failed to update status');
    }
  };

  const onDelete = async () => {
    try {
      await remove.mutateAsync(id);
      router.replace('/projects');
    } catch (err) {
      setEditError(err instanceof ApiError ? err.detail : 'Failed to delete');
      setConfirmOpen(false);
    }
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/projects" className="text-xs text-slate-500 hover:text-slate-700">
            ← Projects
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-slate-900">{project.name}</h1>
            <span
              className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                project.status === 'ACTIVE'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-slate-100 text-slate-500'
              }`}
            >
              {project.status}
            </span>
          </div>
          <p className="text-xs text-slate-500">
            Created {new Date(project.created_at).toLocaleString()}
          </p>
        </div>
        <Link
          href={`/projects/${id}/history`}
          className="rounded-md border border-indigo-300 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
        >
          AI history & analysis →
        </Link>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Profile</h2>
          {/* Read-only by default. Edit toggles in the form below;
              Archive/Restore stays as a separate action (a status flip
              isn't a profile edit). */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onToggleArchive}
              disabled={update.isPending || !canEdit}
              title={canEdit ? undefined : editTooltip}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {project.status === 'ACTIVE' ? 'Archive' : 'Restore'}
            </button>
            <EditToolbar
              editing={editing}
              canEdit={canEdit}
              disabledReason={editTooltip}
              onEdit={() => setEditing(true)}
              onCancel={onCancelEdit}
              onSave={onSave}
              dirty={dirty}
              saving={update.isPending}
              saveLabel="Save changes"
            />
          </div>
        </header>
        <div className="space-y-3 px-4 py-4">
          {editing ? (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600">
                  Name
                </label>
                <input
                  type="text"
                  value={name}
                  maxLength={200}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600">
                  Description
                </label>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What does success look like for this project?"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </>
          ) : (
            <dl className="grid gap-2 text-xs sm:grid-cols-[8rem_1fr]">
              <dt className="text-slate-500">Name</dt>
              <dd className="text-sm text-slate-800">{project.name}</dd>
              <dt className="text-slate-500">Description</dt>
              <dd className="text-sm text-slate-800">
                {project.description ? (
                  project.description
                ) : (
                  <span className="italic text-slate-500">No description.</span>
                )}
              </dd>
            </dl>
          )}
          {editError ? (
            <p role="alert" className="text-xs text-red-600">
              {editError}
            </p>
          ) : null}
          {savedAt && !update.isPending && !editError && !editing ? (
            <p className="text-xs text-emerald-700">Saved</p>
          ) : null}
        </div>
      </section>

      <ProjectTasksList tasks={tasks ?? []} />

      <section className="rounded-lg border border-red-200 bg-white shadow-sm">
        <header className="border-b border-red-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-red-900">Danger zone</h2>
          <p className="mt-0.5 text-xs text-red-700/70">
            Deleting unlinks tasks from the project (their project_id is set to null) but does not
            delete the tasks themselves.
          </p>
        </header>
        <div className="flex flex-wrap items-center justify-end px-4 py-3">
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            disabled={!canEdit}
            title={canEdit ? undefined : editTooltip}
            className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Delete project
          </button>
        </div>
      </section>

      <ConfirmDialog
        open={confirmOpen}
        title="Delete this project?"
        message={`"${project.name}" will be removed. Linked tasks survive — their project link is cleared. This cannot be undone.`}
        confirmLabel="Delete project"
        pending={remove.isPending}
        onConfirm={onDelete}
        onCancel={() => setConfirmOpen(false)}
        tone="danger"
      />
    </div>
  );
}

function ProjectTasksList({ tasks }: { tasks: Task[] }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Tasks in this project</h2>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
          {tasks.length}
        </span>
      </header>
      {tasks.length === 0 ? (
        <p className="px-3 py-6 text-center text-sm italic text-slate-500">
          No tasks linked to this project yet.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {tasks.map((t) => (
            <li key={t.id} className="hover:bg-slate-50">
              <Link
                href={`/tasks/${t.id}`}
                className="flex items-center justify-between gap-3 px-3 py-2.5"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="font-mono text-[10px] uppercase text-slate-400">
                    {t.public_id}
                  </span>
                  <span className="truncate text-sm text-slate-800">{t.title}</span>
                </div>
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                    t.is_blocked
                      ? 'bg-red-100 text-red-800'
                      : t.status === 'DONE'
                        ? 'bg-emerald-100 text-emerald-800'
                        : t.status === 'IN_PROGRESS'
                          ? 'bg-blue-100 text-blue-800'
                          : 'bg-slate-100 text-slate-700'
                  }`}
                >
                  {t.is_blocked ? 'Blocked' : t.status.replace('_', ' ')}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
