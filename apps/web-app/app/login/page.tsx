'use client';

// Phase 5 batch 1: the inline workspace picker has moved to
// /workspaces. /login now stays focused on the credentials step:
// single-workspace users get bounced straight to the post-login
// destination, multi-workspace users get redirected to /workspaces
// (with the selection_token + tile list stashed in sessionStorage so
// the picker page can read it).

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type FormEvent } from 'react';

import { Divider, OAuthButtons } from '../components/OAuthButtons';
import { ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { SELECTION_KEY } from '../workspaces/page';

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {/* Suspense boundary required by Next.js when reading search params on the client. */}
        <Suspense fallback={<FormSkeleton />}>
          <LoginFlow />
        </Suspense>
      </div>
    </main>
  );
}

function LoginFlow() {
  const { token, isReady, login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get('next') ?? '/';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If already logged in, bounce away so back-button doesn't strand the user
  // here after a refresh.
  useEffect(() => {
    if (isReady && token) router.replace(next);
  }, [isReady, token, next, router]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await login({ email, password });
      if (res.kind === 'token') {
        router.replace(next);
      } else {
        // Multi-workspace branch: stash selection state and route to
        // the dedicated picker page. SessionStorage scopes it to this
        // tab; the api's 5-minute selection_token TTL is the safety net.
        window.sessionStorage.setItem(
          SELECTION_KEY,
          JSON.stringify({
            selection_token: res.selectionToken,
            workspaces: res.workspaces,
          }),
        );
        router.replace('/workspaces');
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Login failed');
      setSubmitting(false);
    }
  };

  return (
    <>
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-slate-900">Sign in to Kanea</h1>
        <p className="mt-1 text-sm text-slate-500">Use your workspace credentials.</p>
      </header>
      <OAuthButtons mode="login" />
      <Divider />
      <form className="space-y-4" onSubmit={onSubmit}>
        <Field label="Email" htmlFor="email">
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>

        <Field label="Password" htmlFor="password">
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>

        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500">
        New to Kanea?{' '}
        <Link href="/signup" className="font-medium text-indigo-700 hover:underline">
          Create a workspace
        </Link>
      </p>
    </>
  );
}

function FormSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-8 animate-pulse rounded bg-slate-100" />
      <div className="h-8 animate-pulse rounded bg-slate-100" />
      <div className="h-9 animate-pulse rounded bg-slate-100" />
    </div>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
      >
        {label}
      </label>
      {children}
    </div>
  );
}
