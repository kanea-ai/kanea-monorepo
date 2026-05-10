'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, type FormEvent } from 'react';

import { Modal } from '../../components/Modal';
import { ApiError } from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import { useCreateProject, useProjects } from '../../lib/queries';

// Projects list view. A project is a workspace-scoped goal that groups
// tasks across teams. Archived projects are hidden by default.

const PAGE_SIZE = 20;

export default function ProjectsPage() {
  const principal = useCurrentPrincipal();
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';
  const [includeArchived, setIncludeArchived] = useState(false);
  const { data: projects, isLoading, isError, error } = useProjects(includeArchived);

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return projects ?? [];
    return (projects ?? []).filter(
      (p) => p.name.toLowerCase().includes(q) || (p.description ?? '').toLowerCase().includes(q),
    );
  }, [projects, search]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

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
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
            />
            Show archived
          </label>
          {isAdmin ? (
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
            >
              Create project
            </button>
          ) : null}
        </div>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <header className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Projects</h2>
        </header>

        <div className="border-b border-slate-100 px-4 py-2">
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search projects by name or description…"
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        <div className="p-1">
          {isError ? (
            <p className="px-3 py-6 text-sm text-red-600">
              Failed to load projects: {(error as Error).message}
            </p>
          ) : isLoading ? (
            <p className="px-3 py-6 text-sm text-slate-500">Loading…</p>
          ) : filtered.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-slate-500">
              {search
                ? 'No projects match your search.'
                : isAdmin
                  ? 'No projects yet. Click "Create project" above to bundle tasks toward a goal.'
                  : 'No projects yet.'}
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {visible.map((p) => (
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

        {filtered.length > 0 ? (
          <Paginator
            page={safePage}
            pageCount={pageCount}
            total={filtered.length}
            onChange={setPage}
          />
        ) : null}
      </section>

      <CreateProjectDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}

function CreateProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateProject();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
      setError(null);
    }
  }, [open]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({
        name: name.trim(),
        description: description.trim() === '' ? null : description.trim(),
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create project');
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      pending={create.isPending}
      title="Create project"
      subtitle="Group related tasks under a single objective."
      footer={
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
            form="create-project-form"
            disabled={create.isPending || name.trim() === ''}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {create.isPending ? 'Creating…' : 'Create project'}
          </button>
        </>
      }
    >
      <form id="create-project-form" onSubmit={onSubmit} className="space-y-3">
        <div>
          <label
            htmlFor="proj_name"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Name
          </label>
          <input
            id="proj_name"
            type="text"
            required
            value={name}
            maxLength={200}
            placeholder="Launch website"
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label
            htmlFor="proj_desc"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Description
          </label>
          <textarea
            id="proj_desc"
            rows={3}
            value={description}
            placeholder="Optional"
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}

function Paginator({
  page,
  pageCount,
  total,
  onChange,
}: {
  page: number;
  pageCount: number;
  total: number;
  onChange: (next: number) => void;
}) {
  if (pageCount <= 1) {
    return (
      <div className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
        {total} match{total === 1 ? '' : 'es'}
      </div>
    );
  }
  const start = (page - 1) * PAGE_SIZE + 1;
  const end = Math.min(page * PAGE_SIZE, total);
  return (
    <div className="flex items-center justify-between gap-2 border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
      <span>
        Showing {start}–{end} of {total}
      </span>
      <nav className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="rounded border border-slate-200 px-2 py-0.5 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          ‹
        </button>
        {Array.from({ length: pageCount }).map((_, i) => {
          const n = i + 1;
          const isCurrent = n === page;
          return (
            <button
              key={n}
              type="button"
              onClick={() => onChange(n)}
              className={`rounded px-2 py-0.5 ${
                isCurrent
                  ? 'bg-indigo-600 text-white'
                  : 'border border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {n}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => onChange(Math.min(pageCount, page + 1))}
          disabled={page === pageCount}
          className="rounded border border-slate-200 px-2 py-0.5 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          ›
        </button>
      </nav>
    </div>
  );
}
