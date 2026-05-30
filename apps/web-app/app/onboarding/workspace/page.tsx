'use client';

// /onboarding/workspace — second leg of the SSO signup flow.
//
// Inputs: an onboarding state object (onboarding_token + suggested
// workspace name) stashed in sessionStorage by /auth/callback when
// the OAuth round-trip returned `?onboarding_token=…`. The api has
// NOT created any User / Workspace / Member rows yet — they're
// provisioned when the user submits this form.
//
// The token has a short TTL (10 minutes on the api). If the user
// abandons the screen the token expires and they need to re-OAuth.

import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';

import { ApiError, authApi } from '../../lib/api';
import { useAuth } from '../../lib/auth';

export const ONBOARDING_KEY = 'kanea_onboarding';

interface OnboardingState {
  onboarding_token: string;
  suggested_workspace_name: string;
}

export default function OnboardingWorkspacePage() {
  const router = useRouter();
  const { isReady, setTokenFromOAuth } = useAuth();

  const [state, setState] = useState<OnboardingState | null>(null);
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stateChecked, setStateChecked] = useState(false);

  // Hydrate the onboarding state from sessionStorage exactly once.
  // No state → kick the user back to /login.
  useEffect(() => {
    if (!isReady) return;
    if (typeof window === 'undefined') return;
    const raw = window.sessionStorage.getItem(ONBOARDING_KEY);
    if (!raw) {
      router.replace('/login');
      return;
    }
    try {
      const parsed = JSON.parse(raw) as OnboardingState;
      setState(parsed);
      setName(parsed.suggested_workspace_name || '');
    } catch {
      window.sessionStorage.removeItem(ONBOARDING_KEY);
      router.replace('/login');
      return;
    }
    setStateChecked(true);
  }, [isReady, router]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!state) return;
    const trimmed = name.trim();
    if (trimmed === '') return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await authApi.completeOnboarding({
        onboarding_token: state.onboarding_token,
        workspace_name: trimmed,
      });
      // Consume the onboarding state, install the real access token,
      // land the user on the dashboard. Hard reload so React Query's
      // cache starts clean for the brand-new workspace.
      window.sessionStorage.removeItem(ONBOARDING_KEY);
      setTokenFromOAuth(res.access_token);
      window.location.assign('/');
    } catch (err) {
      setSubmitting(false);
      if (err instanceof ApiError && err.status === 409) {
        setError('This workspace name is already taken. Try another.');
        return;
      }
      if (err instanceof ApiError && err.status === 401) {
        // Onboarding token expired — kick back to /login so they can
        // re-OAuth and get a fresh one.
        window.sessionStorage.removeItem(ONBOARDING_KEY);
        setError('Your sign-in window has expired. Please sign in again to continue.');
        return;
      }
      setError(err instanceof ApiError ? err.detail : 'Failed to complete signup');
    }
  };

  if (!isReady || !stateChecked) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        <div className="flex items-center gap-3">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
          Loading…
        </div>
      </main>
    );
  }

  if (!state) {
    // Effect will have redirected, but render nothing in the gap.
    return null;
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <header className="mb-6">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-700">
            Complete setup
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
            What do you want to call your workspace?
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            This is the name your team will see across Kanea. You can rename it later from the
            workspaces page.
          </p>
        </header>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="workspace_name"
              className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
            >
              Workspace name
            </label>
            <input
              id="workspace_name"
              type="text"
              required
              maxLength={120}
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={state.suggested_workspace_name || 'Acme Corp'}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {error ? (
            <p
              role="alert"
              className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={submitting || name.trim() === ''}
            className="w-full rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? 'Creating workspace…' : 'Create workspace'}
          </button>
        </form>
      </div>
    </main>
  );
}
