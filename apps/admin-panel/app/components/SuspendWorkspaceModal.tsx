'use client';

// Slug-confirm modal for suspending or restoring a workspace.
//
// Suspend path: the operator must re-type the workspace's slug to
// confirm — typo-protection for a destructive action that hits every
// member of the tenant. Heavy red styling makes the irreversible
// shape of the action visually obvious.
//
// Restore path: a single confirmation. Restore is safe — it just
// clears the suspended_at column — so we don't require the slug.

import { useEffect, useState } from 'react';

import { ApiError, type AdminWorkspaceRow } from '../lib/api';
import { useSetWorkspaceSuspended } from '../lib/queries';

export function SuspendWorkspaceModal({
  workspace,
  intent,
  onClose,
}: {
  workspace: AdminWorkspaceRow;
  intent: 'suspend' | 'restore';
  onClose: () => void;
}) {
  const mutation = useSetWorkspaceSuspended();
  const [typed, setTyped] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTyped('');
    setError(null);
  }, [workspace.id, intent]);

  const requireSlugMatch = intent === 'suspend';
  const canSubmit = !requireSlugMatch || typed.trim() === workspace.slug;

  const onSubmit = async () => {
    setError(null);
    try {
      await mutation.mutateAsync({
        workspaceId: workspace.id,
        payload: { is_suspended: intent === 'suspend' },
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Action failed');
    }
  };

  const isSuspend = intent === 'suspend';
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={() => {
        if (!mutation.isPending) onClose();
      }}
    >
      <div
        className={`w-full max-w-md rounded-lg border-2 bg-white shadow-2xl ${
          isSuspend ? 'border-red-500' : 'border-slate-200'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <header
          className={`rounded-t-lg px-5 py-3 ${
            isSuspend ? 'bg-red-50 text-red-900' : 'bg-slate-50 text-slate-900'
          }`}
        >
          <p className="text-[10px] font-bold uppercase tracking-widest">
            {isSuspend ? 'Suspension — destructive' : 'Restore workspace'}
          </p>
          <h2 className="mt-0.5 text-base font-semibold">
            {isSuspend ? `Suspend "${workspace.name}"` : `Restore "${workspace.name}"`}
          </h2>
        </header>
        <div className="space-y-3 px-5 py-4 text-sm text-slate-700">
          {isSuspend ? (
            <>
              <p>
                This will block every user in <span className="font-mono">{workspace.slug}</span>{' '}
                from reaching the workspace API (403 Forbidden) until restored. Data is{' '}
                <span className="font-semibold">not</span> deleted — this is a soft suspension you
                can reverse from this same dialog.
              </p>
              <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-900">
                Affects {workspace.metrics.total_users} user(s), {workspace.metrics.total_tasks}{' '}
                task(s).
              </p>
              <div>
                <label
                  htmlFor="slug-confirm"
                  className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
                >
                  Type <span className="font-mono text-red-700">{workspace.slug}</span> to confirm
                </label>
                <input
                  id="slug-confirm"
                  type="text"
                  value={typed}
                  autoFocus
                  autoComplete="off"
                  onChange={(e) => setTyped(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm shadow-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
                />
              </div>
            </>
          ) : (
            <p>
              Restoring re-enables workspace API access for every active member. Single click — no
              slug confirmation needed for the safe direction.
            </p>
          )}
          {error ? (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          ) : null}
        </div>
        <footer className="flex justify-end gap-2 rounded-b-lg border-t border-slate-100 bg-slate-50 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={mutation.isPending || !canSubmit}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-50 ${
              isSuspend ? 'bg-red-600 hover:bg-red-700' : 'bg-emerald-600 hover:bg-emerald-700'
            }`}
          >
            {mutation.isPending
              ? 'Working…'
              : isSuspend
                ? 'Suspend workspace'
                : 'Restore workspace'}
          </button>
        </footer>
      </div>
    </div>
  );
}
