'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type FormEvent } from 'react';

import { Divider, OAuthButtons } from '../components/OAuthButtons';
import { ApiError, type WorkspaceOption } from '../lib/api';
import { useAuth } from '../lib/auth';

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

// Two-stage flow: credentials -> (single-workspace) token, or
// credentials -> selection -> token. Both stages live in this one
// component so the user's email/password don't have to round-trip
// through state we'd otherwise prop-drill.
function LoginFlow() {
  const { token, isReady, login, selectWorkspace } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get('next') ?? '/';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // After a multi-workspace login response, this holds the picker state.
  // Null while we're still on the credentials screen.
  const [selection, setSelection] = useState<{
    selectionToken: string;
    workspaces: WorkspaceOption[];
  } | null>(null);

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
        setSelection({ selectionToken: res.selectionToken, workspaces: res.workspaces });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  const onPick = async (workspaceId: string) => {
    if (!selection) return;
    setSubmitting(true);
    setError(null);
    try {
      await selectWorkspace({
        selection_token: selection.selectionToken,
        workspace_id: workspaceId,
      });
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Workspace selection failed');
      setSubmitting(false);
    }
  };

  if (selection) {
    return (
      <WorkspacePicker
        workspaces={selection.workspaces}
        onPick={onPick}
        onCancel={() => {
          setSelection(null);
          setPassword('');
        }}
        submitting={submitting}
        error={error}
      />
    );
  }

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

function WorkspacePicker({
  workspaces,
  onPick,
  onCancel,
  submitting,
  error,
}: {
  workspaces: WorkspaceOption[];
  onPick: (workspaceId: string) => void | Promise<void>;
  onCancel: () => void;
  submitting: boolean;
  error: string | null;
}) {
  return (
    <>
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-slate-900">Choose a workspace</h1>
        <p className="mt-1 text-sm text-slate-500">
          You belong to more than one — pick the one you want to use.
        </p>
      </header>

      {error ? (
        <p role="alert" className="mb-4 text-sm text-red-600">
          {error}
        </p>
      ) : null}

      <ul className="space-y-2">
        {workspaces.map((ws) => (
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

      <button
        type="button"
        onClick={onCancel}
        disabled={submitting}
        className="mt-6 w-full text-center text-sm text-slate-500 hover:text-slate-700 disabled:opacity-60"
      >
        ← Back to sign in
      </button>
    </>
  );
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
