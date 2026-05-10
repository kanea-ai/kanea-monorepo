'use client';

// Sidebar workspace switcher. Phase 5 batch 1.
//
// Top of the sidebar shows the current workspace name + role. Click
// opens a small floating menu with the user's other workspaces (each
// instant-switches via /auth/switch-workspace) and a "Create new
// workspace" item that opens the same modal /workspaces uses.

import Link from 'next/link';
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { useCreateMyWorkspace, useMe, useMyWorkspaces, useSwitchWorkspace } from '../lib/queries';
import { Modal } from './Modal';

export function WorkspaceSwitcher() {
  const [open, setOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const { setTokenFromOAuth } = useAuth();
  const { data: me } = useMe();
  const { data: workspaces } = useMyWorkspaces();
  const switchWs = useSwitchWorkspace();
  const [error, setError] = useState<string | null>(null);

  // Click outside closes the menu.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const others = (workspaces ?? []).filter((w) => !w.is_current);

  const onSwitch = async (workspaceId: string) => {
    setError(null);
    try {
      const res = await switchWs.mutateAsync({ workspace_id: workspaceId });
      setTokenFromOAuth(res.access_token);
      // Hard reload so React Query's caches reset cleanly to the new
      // workspace's data — many queries are workspace-scoped and a
      // soft route would let stale rows leak across.
      window.location.assign('/');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Switch failed');
    }
  };

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-sm shadow-sm hover:bg-slate-50"
      >
        <span className="min-w-0">
          <span className="block truncate text-xs uppercase tracking-wide text-slate-500">
            Workspace
          </span>
          <span className="block truncate font-semibold text-slate-900">
            {me?.workspace_name ?? '—'}
          </span>
        </span>
        <Caret open={open} />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute left-0 right-0 z-30 mt-1 rounded-md border border-slate-200 bg-white shadow-lg"
        >
          {others.length > 0 ? (
            <>
              <p className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Switch to
              </p>
              <ul className="py-1">
                {others.map((w) => (
                  <li key={w.workspace_id}>
                    <button
                      type="button"
                      role="menuitem"
                      disabled={switchWs.isPending}
                      onClick={() => onSwitch(w.workspace_id)}
                      className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm text-slate-800 hover:bg-slate-100 disabled:opacity-60"
                    >
                      <span className="truncate">{w.name}</span>
                      <span className="shrink-0 text-[10px] uppercase tracking-wide text-slate-400">
                        {roleLabel(w.role)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <Divider />
            </>
          ) : null}

          <Item
            onClick={() => {
              setOpen(false);
              setCreateOpen(true);
            }}
          >
            + Create new workspace
          </Item>
          <Item asLink href="/workspaces" onClick={() => setOpen(false)}>
            Manage workspaces
          </Item>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="mt-1 text-[11px] text-red-600">
          {error}
        </p>
      ) : null}

      <CreateWorkspaceDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(token) => {
          setTokenFromOAuth(token);
          window.location.assign('/');
        }}
      />
    </div>
  );
}

function Item({
  children,
  onClick,
  asLink = false,
  href,
}: {
  children: ReactNode;
  onClick?: () => void;
  asLink?: boolean;
  href?: string;
}) {
  if (asLink && href) {
    return (
      <Link
        href={href}
        onClick={onClick}
        role="menuitem"
        className="flex w-full px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
      >
        {children}
      </Link>
    );
  }
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="flex w-full px-3 py-1.5 text-left text-sm text-indigo-700 hover:bg-indigo-50"
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="my-1 h-px bg-slate-100" />;
}

function Caret({ open }: { open: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      className={`shrink-0 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function roleLabel(role: 'WORKSPACE_OWNER' | 'WORKSPACE_ADMIN' | 'WORKSPACE_USER'): string {
  const tail = role.slice('WORKSPACE_'.length);
  return tail.charAt(0) + tail.slice(1).toLowerCase();
}

function CreateWorkspaceDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (accessToken: string) => void;
}) {
  const create = useCreateMyWorkspace();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName('');
      setError(null);
    }
  }, [open]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const res = await create.mutateAsync({ name: name.trim() });
      onCreated(res.access_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create workspace');
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      pending={create.isPending}
      title="Create workspace"
      subtitle="You'll be the owner. Switching is instant."
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
            form="create-ws-sidebar-form"
            disabled={create.isPending || name.trim() === ''}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {create.isPending ? 'Creating…' : 'Create'}
          </button>
        </>
      }
    >
      <form id="create-ws-sidebar-form" onSubmit={onSubmit} className="space-y-3">
        <div>
          <label
            htmlFor="ws_name_sidebar"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Workspace name
          </label>
          <input
            id="ws_name_sidebar"
            type="text"
            required
            maxLength={200}
            value={name}
            placeholder="Acme Corp"
            onChange={(e) => setName(e.target.value)}
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
