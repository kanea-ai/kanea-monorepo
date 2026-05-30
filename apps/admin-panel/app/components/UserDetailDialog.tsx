'use client';

// Back-office user detail modal: identity + per-workspace membership
// grid + two destructive actions:
//
// - Global Ban (red): toggles users.is_banned. Confirmation requires
//   typing the user's email — same typo-protection shape we use on
//   the workspace suspend dialog.
// - Force Password Reset (amber): one-click, but produces a simulated
//   email preview the operator can read before walking away.
//
// Closing rules: backdrop click + Cancel both close. While a mutation
// is pending we lock both so the operator can't escape mid-flight.

import { useEffect, useState } from 'react';

import { ApiError, type ForcePasswordResetResponse } from '../lib/api';
import { useAdminUser, useForcePasswordReset, useSetUserBanned } from '../lib/queries';

export function UserDetailDialog({ userId, onClose }: { userId: string; onClose: () => void }) {
  const { data: user, isLoading, isError, error } = useAdminUser(userId);
  const banMutation = useSetUserBanned();
  const resetMutation = useForcePasswordReset();
  const [confirm, setConfirm] = useState<'ban' | 'unban' | null>(null);
  const [typedEmail, setTypedEmail] = useState('');
  const [resetPreview, setResetPreview] = useState<ForcePasswordResetResponse | null>(null);
  const [opError, setOpError] = useState<string | null>(null);

  // Reset transient UI state when a different user opens.
  useEffect(() => {
    setConfirm(null);
    setTypedEmail('');
    setResetPreview(null);
    setOpError(null);
  }, [userId]);

  const pending = banMutation.isPending || resetMutation.isPending;

  const onConfirmBan = async () => {
    if (!user || !confirm) return;
    setOpError(null);
    try {
      await banMutation.mutateAsync({
        userId: user.id,
        payload: { is_banned: confirm === 'ban' },
      });
      setConfirm(null);
      setTypedEmail('');
    } catch (err) {
      setOpError(err instanceof ApiError ? err.detail : 'Action failed');
    }
  };

  const onForceReset = async () => {
    if (!user) return;
    setOpError(null);
    try {
      const out = await resetMutation.mutateAsync({ userId: user.id });
      setResetPreview(out);
    } catch (err) {
      setOpError(err instanceof ApiError ? err.detail : 'Action failed');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={() => {
        if (!pending) onClose();
      }}
    >
      <div
        className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {isLoading ? (
          <p className="p-6 text-sm text-slate-500">Loading user…</p>
        ) : isError || !user ? (
          <p className="p-6 text-sm text-red-600">
            Failed to load user: {(error as Error)?.message ?? 'unknown'}
          </p>
        ) : (
          <>
            <header className="border-b border-slate-200 px-5 py-4">
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-slate-900">{user.full_name}</h2>
                {user.is_superadmin ? (
                  <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-rose-800">
                    Superadmin
                  </span>
                ) : null}
                {user.is_banned ? (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                    Banned
                  </span>
                ) : null}
              </div>
              <p className="text-xs text-slate-500">{user.email}</p>
              <p className="mt-1 text-[11px] text-slate-500">
                User since {new Date(user.created_at).toLocaleString()}
                {user.sessions_invalidated_at
                  ? ` · sessions killed ${new Date(user.sessions_invalidated_at).toLocaleString()}`
                  : ''}
              </p>
            </header>

            <Section title="Workspaces">
              {user.memberships.length === 0 ? (
                <p className="text-xs italic text-slate-500">
                  This user has no active workspace memberships.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="text-[10px] uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="py-1 text-left">Workspace</th>
                      <th className="py-1 text-left">Slug</th>
                      <th className="py-1 text-left">Role</th>
                      <th className="py-1 text-left">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {user.memberships.map((m) => (
                      <tr key={m.member_id}>
                        <td className="truncate py-1.5 font-medium text-slate-900">
                          {m.workspace_name}
                        </td>
                        <td className="py-1.5 font-mono text-[11px] text-slate-500">
                          {m.workspace_slug}
                        </td>
                        <td className="py-1.5 text-slate-700">
                          {m.role.replace('WORKSPACE_', '')}
                        </td>
                        <td className="py-1.5">
                          {m.is_suspended ? (
                            <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                              Suspended
                            </span>
                          ) : (
                            <span className="text-[11px] text-emerald-700">Active</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Section>

            <Section title="Global ban">
              {user.is_superadmin ? (
                <p className="text-xs italic text-slate-500">
                  Superadmins cannot be banned via this surface. Revoke their flag via{' '}
                  <span className="font-mono">scripts/make_superadmin --revoke</span> first.
                </p>
              ) : confirm === null ? (
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs text-slate-600">
                    {user.is_banned
                      ? 'This user is currently banned platform-wide. Restoring re-enables access immediately.'
                      : 'Bans take effect on the next request; every workspace returns 403.'}
                  </p>
                  {user.is_banned ? (
                    <button
                      type="button"
                      onClick={() => setConfirm('unban')}
                      disabled={pending}
                      className="rounded-md border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-60"
                    >
                      Restore access
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirm('ban')}
                      disabled={pending}
                      className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                    >
                      Ban user
                    </button>
                  )}
                </div>
              ) : (
                <div className="space-y-3 rounded-md border border-red-200 bg-red-50/60 p-3">
                  {confirm === 'ban' ? (
                    <>
                      <p className="text-sm text-red-900">
                        Type <span className="font-mono">{user.email}</span> to confirm the ban.
                        This will block every authenticated request the user makes, across every
                        workspace, until restored.
                      </p>
                      <input
                        type="text"
                        value={typedEmail}
                        onChange={(e) => setTypedEmail(e.target.value)}
                        autoComplete="off"
                        autoFocus
                        className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm shadow-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
                      />
                    </>
                  ) : (
                    <p className="text-sm text-emerald-900">
                      Restoring access for <span className="font-mono">{user.email}</span> takes
                      effect on their next request. No further confirmation needed.
                    </p>
                  )}
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setConfirm(null);
                        setTypedEmail('');
                      }}
                      disabled={pending}
                      className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={onConfirmBan}
                      disabled={pending || (confirm === 'ban' && typedEmail.trim() !== user.email)}
                      className={`rounded-md px-3 py-1.5 text-xs font-semibold text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-50 ${
                        confirm === 'ban'
                          ? 'bg-red-600 hover:bg-red-700'
                          : 'bg-emerald-600 hover:bg-emerald-700'
                      }`}
                    >
                      {pending ? 'Working…' : confirm === 'ban' ? 'Ban user' : 'Restore access'}
                    </button>
                  </div>
                </div>
              )}
            </Section>

            <Section title="Force password reset">
              {resetPreview ? (
                <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <p className="font-semibold">Simulated recovery email (logged to api):</p>
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded border border-amber-200 bg-white p-2 font-mono text-[11px]">
                    {resetPreview.simulated_email}
                  </pre>
                  <p>
                    Sessions invalidated at{' '}
                    <span className="font-mono">
                      {new Date(resetPreview.sessions_invalidated_at).toLocaleString()}
                    </span>
                    . Existing JWTs now bounce with 401.
                  </p>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs text-slate-600">
                    Randomises the password hash AND invalidates every outstanding JWT — the user
                    must run the recovery flow to regain access. Email delivery is simulated in this
                    stage; we&apos;ll show you the preview below.
                  </p>
                  <button
                    type="button"
                    onClick={onForceReset}
                    disabled={pending}
                    className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-60"
                  >
                    Force reset
                  </button>
                </div>
              )}
            </Section>

            {opError ? (
              <p role="alert" className="px-5 pb-3 text-sm text-red-600">
                {opError}
              </p>
            ) : null}

            <footer className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
              <button
                type="button"
                onClick={onClose}
                disabled={pending}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                Close
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-slate-100 px-5 py-4 last:border-b-0">
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {title}
      </h3>
      {children}
    </section>
  );
}
