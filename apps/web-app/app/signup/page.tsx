'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Suspense, useEffect, useState, type FormEvent } from 'react';

import { ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';

export default function SignupPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-slate-900">Create your Kanea workspace</h1>
          <p className="mt-1 text-sm text-slate-500">
            One account. You become the workspace owner.
          </p>
        </header>
        <Suspense fallback={<FormSkeleton />}>
          <SignupForm />
        </Suspense>
        <p className="mt-6 text-center text-sm text-slate-500">
          Already have an account?{' '}
          <Link href="/login" className="font-medium text-indigo-700 hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}

function SignupForm() {
  const { token, isReady, register } = useAuth();
  const router = useRouter();

  const [fullName, setFullName] = useState('');
  const [workspaceName, setWorkspaceName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already signed in? Bounce home so refresh-on-/signup doesn't strand.
  useEffect(() => {
    if (isReady && token) router.replace('/');
  }, [isReady, token, router]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register({
        email,
        password,
        full_name: fullName,
        workspace_name: workspaceName,
      });
      router.replace('/');
    } catch (err) {
      // 422s come back from FastAPI as a structured detail. Surface the
      // server message verbatim — it's already user-readable for the
      // common cases (duplicate email, password too short).
      setError(err instanceof ApiError ? formatError(err) : 'Sign-up failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <Field label="Full name" htmlFor="full_name">
        <input
          id="full_name"
          type="text"
          autoComplete="name"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </Field>

      <Field label="Workspace name" htmlFor="workspace_name" hint="Your team or company name.">
        <input
          id="workspace_name"
          type="text"
          autoComplete="organization"
          required
          value={workspaceName}
          onChange={(e) => setWorkspaceName(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </Field>

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

      <Field label="Password" htmlFor="password" hint="At least 8 characters.">
        <input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
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
        {submitting ? 'Creating workspace…' : 'Create workspace'}
      </button>
    </form>
  );
}

function formatError(err: ApiError): string {
  // FastAPI 422 detail is an array of validation issues — concatenate the
  // first message instead of dumping the JSON blob.
  if (err.status === 422) {
    try {
      const parsed = JSON.parse(err.detail) as Array<{ msg: string }>;
      const first = parsed[0]?.msg;
      if (first) return first;
    } catch {
      /* fall through */
    }
  }
  return err.detail;
}

function FormSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-8 animate-pulse rounded bg-slate-100" />
      ))}
      <div className="h-9 animate-pulse rounded bg-slate-100" />
    </div>
  );
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
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
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
