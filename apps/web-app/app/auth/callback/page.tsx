'use client';

// Landing page for the OAuth round-trip. The api's /oauth/{provider}/callback
// handler 302s here with one of:
//   ?token=…                                  (single-workspace user)
//   ?selection_token=…&workspaces=…           (multi-workspace user)
//   ?error=…                                  (provider denied / consent failed)
// Multi-workspace lands here, not /login, so the post-login redirect target
// stays consistent across both flows.

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

import { ApiError, type WorkspaceOption } from '../../lib/api';
import { useAuth } from '../../lib/auth';

export default function AuthCallbackPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <Suspense fallback={<Spinner />}>
        <CallbackHandler />
      </Suspense>
    </main>
  );
}

function CallbackHandler() {
  const params = useSearchParams();
  const router = useRouter();
  const { setTokenFromOAuth, selectWorkspace } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [picker, setPicker] = useState<{
    selectionToken: string;
    workspaces: WorkspaceOption[];
  } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const providerError = params.get('error');
    if (providerError) {
      setError(providerError);
      return;
    }

    const token = params.get('token');
    if (token) {
      setTokenFromOAuth(token);
      router.replace('/');
      return;
    }

    const selectionToken = params.get('selection_token');
    const workspacesB64 = params.get('workspaces');
    if (selectionToken && workspacesB64) {
      try {
        const padded = workspacesB64.replace(/-/g, '+').replace(/_/g, '/');
        const json = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
        const workspaces = JSON.parse(json) as WorkspaceOption[];
        setPicker({ selectionToken, workspaces });
        return;
      } catch {
        setError('invalid_workspaces_payload');
        return;
      }
    }

    setError('missing_token');
  }, [params, router, setTokenFromOAuth]);

  if (error) {
    return (
      <div className="w-full max-w-sm rounded-xl border border-red-200 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">Sign-in failed</h1>
        <p className="mt-2 text-sm text-slate-600">
          The sign-in flow returned an error: <code className="text-red-600">{error}</code>.
        </p>
        <a
          href="/login"
          className="mt-4 inline-block rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Try again
        </a>
      </div>
    );
  }

  if (picker) {
    const onPick = async (workspaceId: string) => {
      setSubmitting(true);
      try {
        await selectWorkspace({
          selection_token: picker.selectionToken,
          workspace_id: workspaceId,
        });
        router.replace('/');
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : 'workspace_selection_failed');
        setSubmitting(false);
      }
    };
    return (
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">Choose a workspace</h1>
        <p className="mb-4 mt-1 text-sm text-slate-500">
          You belong to more than one — pick the one you want to use.
        </p>
        <ul className="space-y-2">
          {picker.workspaces.map((ws) => (
            <li key={ws.workspace_id}>
              <button
                type="button"
                onClick={() => onPick(ws.workspace_id)}
                disabled={submitting}
                className="flex w-full items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-3 text-left text-sm shadow-sm transition-colors hover:border-indigo-300 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="font-medium text-slate-900">{ws.name}</span>
                <span className="text-xs uppercase tracking-wide text-slate-500">
                  {roleLabel(ws.role)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return <Spinner />;
}

function roleLabel(role: WorkspaceOption['role']): string {
  switch (role) {
    case 'WORKSPACE_OWNER':
      return 'Owner';
    case 'WORKSPACE_ADMIN':
      return 'Admin';
    case 'WORKSPACE_MEMBER':
      return 'Member';
  }
}

function Spinner() {
  return (
    <div className="flex flex-col items-center gap-3 text-sm text-slate-500">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-600" />
      Signing you in…
    </div>
  );
}
