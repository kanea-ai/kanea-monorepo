'use client';

// OAuth round-trip landing. Phase 5 batch 1: the multi-workspace
// picker has moved to /workspaces; this page now just hydrates the
// AuthContext from the api's redirect query and bounces.
//
// Possible inputs (set by the api's /oauth/{provider}/callback):
//   ?token=…                                       → single workspace
//   ?selection_token=…&workspaces=<base64-json>    → multi workspace
//   ?onboarding_token=…&suggested_workspace_name=… → brand-new SSO user,
//                                                    needs to pick a
//                                                    workspace name
//   ?error=…                                       → provider denied
//                                                    / consent failed

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

import { type WorkspaceOption } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { ONBOARDING_KEY } from '../../onboarding/workspace/page';
import { SELECTION_KEY } from '../../workspaces/page';

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
  const { setTokenFromOAuth } = useAuth();
  const [error, setError] = useState<string | null>(null);

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

    const onboardingToken = params.get('onboarding_token');
    if (onboardingToken) {
      // Brand-new SSO user — hand off to /onboarding/workspace so the
      // caller can pick a workspace name. The token isn't a usable
      // access token; the onboarding page exchanges it for a real
      // one via POST /auth/complete-oauth-onboarding.
      const suggested = params.get('suggested_workspace_name') ?? '';
      try {
        window.sessionStorage.setItem(
          ONBOARDING_KEY,
          JSON.stringify({
            onboarding_token: onboardingToken,
            suggested_workspace_name: suggested,
          }),
        );
        router.replace('/onboarding/workspace');
        return;
      } catch {
        setError('storage_unavailable');
        return;
      }
    }

    const selectionToken = params.get('selection_token');
    const workspacesB64 = params.get('workspaces');
    if (selectionToken && workspacesB64) {
      try {
        const padded = workspacesB64.replace(/-/g, '+').replace(/_/g, '/');
        const json = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
        const workspaces = JSON.parse(json) as WorkspaceOption[];
        // Hand off to /workspaces — the same picker that's reused by
        // the password-login multi-workspace branch.
        window.sessionStorage.setItem(
          SELECTION_KEY,
          JSON.stringify({ selection_token: selectionToken, workspaces }),
        );
        router.replace('/workspaces');
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

  return <Spinner />;
}

function Spinner() {
  return (
    <div className="flex flex-col items-center gap-3 text-sm text-slate-500">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-600" />
      Signing you in…
    </div>
  );
}
