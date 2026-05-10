'use client';

// /workspaces — single tile picker that handles both modes:
//
// 1. Post-login (pre-token): the login form / OAuth callback stashes
//    the selection_token + workspaces list under SELECTION_KEY in
//    sessionStorage and redirects here. We render the tiles, exchange
//    the chosen tile's id via /auth/select-workspace, and route in.
//
// 2. Authenticated (sidebar "manage workspaces" link): the page reads
//    /me/workspaces, renders tiles, and uses /auth/switch-workspace
//    when a tile is clicked. The current workspace gets a "Current"
//    badge.
//
// Either way the URL stays /workspaces — no special routes per mode.

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { Modal } from '../components/Modal';
import { ApiError, authApi, type WorkspaceOption } from '../lib/api';
import { useAuth } from '../lib/auth';
import { useCreateMyWorkspace, useMyWorkspaces, useSwitchWorkspace } from '../lib/queries';

// Where the login flow stashes the post-login selection state. Under
// session storage so a closed tab clears it; the selection token's
// 5-minute TTL on the api side is the secondary safety net.
export const SELECTION_KEY = 'kanea_selection';

interface SelectionState {
  selection_token: string;
  workspaces: WorkspaceOption[];
}

export default function WorkspacesPage() {
  const router = useRouter();
  const { token, isReady, setTokenFromOAuth, logout } = useAuth();

  const [mode, setMode] = useState<'selection' | 'authenticated' | 'unknown'>('unknown');
  const [selection, setSelection] = useState<SelectionState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  // Pick the mode once auth state is hydrated. Selection state in
  // sessionStorage wins — it implies "you just logged in and we still
  // need you to pick" even if there's a stale token lying around.
  useEffect(() => {
    if (!isReady) return;
    if (typeof window === 'undefined') return;
    const raw = window.sessionStorage.getItem(SELECTION_KEY);
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as SelectionState;
        setSelection(parsed);
        setMode('selection');
        return;
      } catch {
        window.sessionStorage.removeItem(SELECTION_KEY);
      }
    }
    if (token) {
      setMode('authenticated');
    } else {
      router.replace('/login');
    }
  }, [isReady, token, router]);

  // Authenticated mode pulls from the api.
  const { data: workspaces, isLoading: meLoading } = useMyWorkspaces();
  const switchWs = useSwitchWorkspace();

  const tiles = useMemo(() => {
    if (mode === 'selection') {
      return (selection?.workspaces ?? []).map((w) => ({
        workspace_id: w.workspace_id,
        name: w.name,
        role: w.role,
        is_current: false,
      }));
    }
    if (mode === 'authenticated') {
      return (workspaces ?? []).map((w) => ({
        workspace_id: w.workspace_id,
        name: w.name,
        role: w.role,
        is_current: w.is_current,
      }));
    }
    return [];
  }, [mode, selection, workspaces]);

  const onPickSelection = async (workspaceId: string) => {
    if (!selection) return;
    setSubmittingId(workspaceId);
    setError(null);
    try {
      const res = await authApi.selectWorkspace({
        selection_token: selection.selection_token,
        workspace_id: workspaceId,
      });
      window.sessionStorage.removeItem(SELECTION_KEY);
      setTokenFromOAuth(res.access_token);
      router.replace('/');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Workspace selection failed');
      setSubmittingId(null);
    }
  };

  const onPickAuthenticated = async (workspaceId: string, isCurrent: boolean) => {
    if (isCurrent) {
      router.replace('/');
      return;
    }
    setSubmittingId(workspaceId);
    setError(null);
    try {
      const res = await switchWs.mutateAsync({ workspace_id: workspaceId });
      setTokenFromOAuth(res.access_token);
      // Hard reload so React Query's per-workspace cache resets cleanly.
      window.location.assign('/');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Switch failed');
      setSubmittingId(null);
    }
  };

  if (mode === 'unknown' || (mode === 'authenticated' && meLoading)) {
    return <Spinner label="Loading workspaces…" />;
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8 flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">
              {mode === 'selection' ? 'Choose a workspace' : 'Your workspaces'}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {mode === 'selection'
                ? 'You belong to more than one — pick the workspace you want to enter.'
                : 'Switch to another workspace, or create a new one. The active one is marked.'}
            </p>
          </div>
          {mode === 'authenticated' ? (
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
              >
                Create new
              </button>
              <button
                type="button"
                onClick={logout}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Sign out
              </button>
            </div>
          ) : null}
        </header>

        {error ? (
          <p
            role="alert"
            className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {error}
          </p>
        ) : null}

        {tiles.length === 0 ? (
          <p className="rounded-md border border-slate-200 bg-white px-4 py-6 text-center text-sm text-slate-500">
            No workspaces yet.
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {tiles.map((t) => (
              <li key={t.workspace_id}>
                <button
                  type="button"
                  disabled={submittingId !== null}
                  onClick={() =>
                    mode === 'selection'
                      ? onPickSelection(t.workspace_id)
                      : onPickAuthenticated(t.workspace_id, t.is_current)
                  }
                  className="group flex w-full items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-5 py-5 text-left shadow-sm transition-all hover:border-indigo-300 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold text-slate-900">{t.name}</p>
                    <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">
                      {roleLabel(t.role)}
                    </p>
                  </div>
                  {t.is_current ? (
                    <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
                      Current
                    </span>
                  ) : (
                    <span className="shrink-0 text-slate-400 group-hover:text-indigo-600">→</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}

        {mode === 'authenticated' ? (
          <CreateWorkspaceDialog
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            onCreated={(token) => {
              setTokenFromOAuth(token);
              window.location.assign('/');
            }}
          />
        ) : null}
      </div>
    </main>
  );
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
      subtitle="You'll be the owner. You can rename later."
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
            form="create-ws-form"
            disabled={create.isPending || name.trim() === ''}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {create.isPending ? 'Creating…' : 'Create'}
          </button>
        </>
      }
    >
      <form id="create-ws-form" onSubmit={onSubmit} className="space-y-3">
        <div>
          <label
            htmlFor="ws_name"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Workspace name
          </label>
          <input
            id="ws_name"
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

function roleLabel(role: WorkspaceOption['role']): string {
  switch (role) {
    case 'WORKSPACE_OWNER':
      return 'Owner';
    case 'WORKSPACE_ADMIN':
      return 'Admin';
    case 'WORKSPACE_USER':
      return 'Member';
  }
}

function Spinner({ label }: { label: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
      <div className="flex items-center gap-3">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
        {label}
      </div>
    </main>
  );
}
