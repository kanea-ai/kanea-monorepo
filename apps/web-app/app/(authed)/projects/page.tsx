'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';

import { ApiError } from '../../lib/api';
import { useCreateProject, useProjects } from '../../lib/queries';

// Projects list view. A project is a workspace-scoped goal that groups
// tasks across teams. Archived projects are hidden by default.

export default function ProjectsPage() {
  const [includeArchived, setIncludeArchived] = useState(false);
  const { data: projects, isLoading, isError, error } = useProjects(includeArchived);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Projects</h1>
          <p className="text-sm text-slate-500">
            Workspace-level goals. A project bundles tasks toward a single objective; tasks under it
            can sit on different teams.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          Show archived
        </label>
      </header>

      <CreateProjectSection />

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <header className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Active projects</h2>
        </header>
        <div className="p-1">
          {isError ? (
            <p className="px-3 py-6 text-sm text-red-600">
              Failed to load projects: {(error as Error).message}
            </p>
          ) : isLoading ? (
            <p className="px-3 py-6 text-sm text-slate-500">Loading…</p>
          ) : !projects || projects.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-slate-500">
              No projects yet. Create one above to bundle tasks toward a goal.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {projects.map((p) => (
                <li key={p.id} className="hover:bg-slate-50">
                  <Link
                    href={`/projects/${p.id}`}
                    className="flex items-center justify-between gap-3 px-3 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">{p.name}</p>
                      {p.description ? (
                        <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">
                          {p.description}
                        </p>
                      ) : (
                        <p className="mt-0.5 text-xs italic text-slate-400">No description.</p>
                      )}
                    </div>
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                        p.status === 'ACTIVE'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {p.status}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function CreateProjectSection() {
  const create = useCreateProject();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({
        name: name.trim(),
        description: description.trim() === '' ? null : description.trim(),
      });
      setName('');
      setDescription('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create project');
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">New project</h2>
      </header>
      <form
        className="grid gap-3 px-4 py-4 sm:grid-cols-[1fr_2fr_auto] sm:items-end"
        onSubmit={onSubmit}
      >
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600">
            Name
          </label>
          <input
            type="text"
            required
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
            placeholder="Launch website"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600">
            Description
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <button
          type="submit"
          disabled={create.isPending || name.trim() === ''}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {create.isPending ? 'Creating…' : 'Create project'}
        </button>
      </form>
      {error ? (
        <p role="alert" className="px-4 pb-4 text-sm text-red-600">
          {error}
        </p>
      ) : null}
    </section>
  );
}
